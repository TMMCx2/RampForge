"""Advanced dock dashboard screen."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select

from app.services import APIClient, WebSocketClient
from app.services.ramp_status import RampInfo, get_ramp_statuses
from app.widgets import FilterSidebar, RampDetailPanel, StatsPanel
from app.widgets.filter_sidebar import SidebarSummary

logger = logging.getLogger(__name__)


class DockDashboardScreen(Screen):
    """Main operational dashboard with worklist view."""

    CSS = """
    DockDashboardScreen {
        layout: vertical;
    }

    Header {
        background: $boost;
    }

    #header-bar {
        width: 100%;
        height: 3;
        background: $boost;
        padding: 0 2;
        layout: horizontal;
        align: center middle;
        column-gap: 2;
    }

    #user-info {
        width: 1fr;
        height: 100%;
        content-align: left middle;
        color: $text;
    }

    #header-title {
        width: auto;
        color: $text-muted;
        content-align: right middle;
    }

    #filter-bar {
        width: 100%;
        height: 3;
        padding: 0 2;
        layout: horizontal;
        align: center middle;
        column-gap: 1;
        background: $surface;
        border-bottom: solid $boost;
    }

    .filter-button {
        width: 18;
    }

    #status-bar {
        width: 100%;
        height: 1;
        background: $panel;
        padding: 0 2;
        content-align: left middle;
        color: $text;
    }

    #dashboard-body {
        width: 100%;
        height: 1fr;
        layout: horizontal;
        background: $surface-darken-1;
    }

    #center-pane {
        width: 1fr;
        height: 100%;
        layout: vertical;
        padding: 0 1;
        row-gap: 1;
    }

    #search-input {
        width: 30;
    }

    #stats-panel {
        width: 100%;
        margin: 1 0 0 0;
    }

    #stats-panel .stat-title {
        content-align: left middle;
    }

    #ramp-table {
        width: 100%;
        height: 1fr;
    }

    DataTable {
        background: $surface-darken-2;
        border: solid $panel-darken-1;
    }

    DataTable .datatable--header {
        text-style: bold;
    }

    Footer {
        background: $boost;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("1", "filter_all", "All"),
        ("2", "filter_inbound", "Inbound"),
        ("3", "filter_outbound", "Outbound"),
        ("4", "filter_exceptions", "Exceptions"),
        ("escape", "quit", "Quit"),
        ("ctrl+f", "focus_search", "Search"),
    ]

    def __init__(
        self,
        api_client: APIClient,
        ws_client: WebSocketClient,
        user_data: Dict[str, Any],
    ) -> None:
        super().__init__()
        self.api_client = api_client
        self.ws_client = ws_client
        self.user_data = user_data
        self.ramps: List[Dict[str, Any]] = []
        self.assignments: List[Dict[str, Any]] = []
        self.ramp_infos: List[RampInfo] = []
        self.filtered_ramps: List[RampInfo] = []
        self.direction_filter: Optional[str] = None
        self.status_filter: Optional[str] = None
        self.search_query: str = ""
        self.overdue_only = False
        self.blocked_only = False
        self.status_options: Dict[str, str] = {}

    # ------------------------------------------------------------------#
    # Layout
    # ------------------------------------------------------------------#
    def compose(self) -> ComposeResult:
        """Compose primary screen layout."""
        yield Header()
        with Horizontal(id="header-bar"):
            yield Label(
                f"👤 {self.user_data.get('full_name', 'User')} ({self.user_data.get('role', '')})",
                id="user-info",
            )
            yield Label("⏱️ Live Ops Dashboard", id="header-title")

        with Horizontal(id="filter-bar"):
            yield Button("All (0)", id="btn-all", variant="primary", classes="filter-button")
            yield Button("Inbound", id="btn-inbound", classes="filter-button")
            yield Button("Outbound", id="btn-outbound", classes="filter-button")
            yield Button("Exceptions", id="btn-exceptions", classes="filter-button")
            yield Select([], prompt="Status", id="status-select")
            yield Input(placeholder="Search ramp or load...", id="search-input")

        yield Label("🔄 Initializing...", id="status-bar")

        with Horizontal(id="dashboard-body"):
            yield FilterSidebar()
            with Vertical(id="center-pane"):
                yield StatsPanel(id="stats-panel")
                yield DataTable(id="ramp-table", cursor_type="row")
            yield RampDetailPanel()

        yield Footer()

    # ------------------------------------------------------------------#
    # Lifecycle
    # ------------------------------------------------------------------#
    async def on_mount(self) -> None:
        """Initialize widgets, set up WebSocket, and load data."""
        logger.info("DockDashboardScreen mount started")
        table = self.query_one("#ramp-table", DataTable)
        table.add_columns(
            "Ramp",
            "Zone",
            "Direction",
            "Status",
            "Load",
            "ETA Out",
            "Since",
            "Notes",
        )

        status_select = self.query_one("#status-select", Select)
        status_select.allow_blank = True

        search_input = self.query_one("#search-input", Input)
        search_input.tooltip = "Type to filter by ramp code, load reference, or notes"

        # Connect WebSocket events
        try:
            await self.ws_client.connect()
            self.ws_client.on_message("assignment_created", self._handle_assignment_event)
            self.ws_client.on_message("assignment_updated", self._handle_assignment_event)
            self.ws_client.on_message("assignment_deleted", self._handle_assignment_event)
            self._update_status("🔗 Connected to live updates")
        except Exception as exc:  # pragma: no cover - connectivity issue
            logger.exception("WebSocket connection failed")
            self._update_status(f"⚠️ Offline mode – WebSocket error: {exc}")

        await self.action_refresh()
        logger.info("DockDashboardScreen mount completed")

    async def on_unmount(self) -> None:
        """Clean up WebSocket subscriptions."""
        try:
            await self.ws_client.disconnect()
        except Exception:  # pragma: no cover
            logger.exception("Failed to disconnect WebSocket cleanly")

    # ------------------------------------------------------------------#
    # Data refresh & filtering
    # ------------------------------------------------------------------#
    async def action_refresh(self) -> None:
        """Reload ramps and assignments from API."""
        logger.info("Refreshing dashboard data")
        try:
            self.ramps = await self.api_client.get_ramps()
            self.assignments = await self.api_client.get_assignments()
        except Exception as exc:  # pragma: no cover - network failures
            logger.exception("Failed to load data")
            self._update_status(f"❌ Error loading data: {exc}")
            return

        self.ramp_infos = get_ramp_statuses(self.ramps, self.assignments)
        self._hydrate_status_options()
        self._apply_filters()
        self._update_status(f"✓ Loaded {len(self.ramp_infos)} ramps")
        self._update_summary_widgets()

    def _apply_filters(self) -> None:
        """Filter ramp info collection."""
        filtered = []
        query = self.search_query.lower().strip()

        for info in self.ramp_infos:
            if self.direction_filter == "IB" and info.direction != "IB":
                continue
            if self.direction_filter == "OB" and info.direction != "OB":
                continue
            if self.direction_filter == "EXCEPTIONS" and not info.is_exception:
                continue
            if self.status_filter and info.status_code != self.status_filter:
                continue
            if self.overdue_only and not info.is_overdue:
                continue
            if self.blocked_only and not info.is_blocked:
                continue
            if query and not info.matches_query(query):
                continue
            filtered.append(info)

        self.filtered_ramps = sorted(filtered, key=lambda item: item.ramp_code)
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Populate DataTable with filtered ramps."""
        table = self.query_one("#ramp-table", DataTable)
        table.clear()

        for info in self.filtered_ramps:
            table.add_row(
                info.ramp_code,
                info.zone or "-",
                info.direction_label,
                self._style_status(info),
                info.load_ref or "-",
                self._format_eta(info),
                self._format_since(info),
                (info.notes or "-").split("\n")[0][:40],
                key=str(info.ramp_id),
            )

        # Reset detail panel if selection out of range
        detail = self.query_one(RampDetailPanel)
        if not self.filtered_ramps:
            detail.update_detail(None)

        # Update direction button counts
        self._update_filter_buttons()

    # ------------------------------------------------------------------#
    # Widgets interactions
    # ------------------------------------------------------------------#
    def _hydrate_status_options(self) -> None:
        """Populate status select options."""
        status_map: Dict[str, str] = {}
        for info in self.ramp_infos:
            code = info.status_code or "FREE"
            status_map[code] = info.status_label
        self.status_options = dict(sorted(status_map.items(), key=lambda item: item[1]))

        select = self.query_one("#status-select", Select)
        select.set_options([(label, code) for code, label in self.status_options.items()])
        if self.status_filter and self.status_filter in self.status_options:
            select.value = self.status_filter
        else:
            select.clear()

        # Update button labels with counts
        total = len(self.ramp_infos)
        inbound = sum(1 for info in self.ramp_infos if info.direction == "IB")
        outbound = sum(1 for info in self.ramp_infos if info.direction == "OB")
        exceptions = sum(1 for info in self.ramp_infos if info.is_exception)

        self.query_one("#btn-all", Button).label = f"All ({total})"
        self.query_one("#btn-inbound", Button).label = f"Inbound ({inbound})"
        self.query_one("#btn-outbound", Button).label = f"Outbound ({outbound})"
        self.query_one("#btn-exceptions", Button).label = f"Exceptions ({exceptions})"

    def _update_filter_buttons(self) -> None:
        """Update button variants to reflect current filter."""
        mapping = {
            "btn-all": self.direction_filter is None,
            "btn-inbound": self.direction_filter == "IB",
            "btn-outbound": self.direction_filter == "OB",
            "btn-exceptions": self.direction_filter == "EXCEPTIONS",
        }
        for button_id, active in mapping.items():
            button = self.query_one(f"#{button_id}", Button)
            button.variant = "primary" if active else "default"

    def _update_summary_widgets(self) -> None:
        """Refresh summary widgets (stats panel + sidebar)."""
        total = len(self.ramp_infos)
        busy = sum(1 for info in self.ramp_infos if not info.is_free)
        blocked = sum(1 for info in self.ramp_infos if info.is_blocked)
        overdue = sum(1 for info in self.ramp_infos if info.is_overdue)

        stats_panel = self.query_one("#stats-panel", StatsPanel)
        stats_panel.update_stats(self.assignments, total_ramps=total, blocked=blocked, overdue=overdue)

        sidebar = self.query_one(FilterSidebar)
        sidebar.update_summary(SidebarSummary(total=total, busy=busy, blocked=blocked, overdue=overdue))

    # ------------------------------------------------------------------#
    # Event handlers
    # ------------------------------------------------------------------#
    async def _handle_assignment_event(self, _: Dict[str, Any]) -> None:
        """React to WebSocket updates."""
        await self.action_refresh()

    async def on_button_pressed(self, event: Button.Pressed) -> None:  # type: ignore[override]
        """Handle filter buttons."""
        button_id = event.button.id
        if button_id == "btn-all":
            self.direction_filter = None
        elif button_id == "btn-inbound":
            self.direction_filter = "IB"
        elif button_id == "btn-outbound":
            self.direction_filter = "OB"
        elif button_id == "btn-exceptions":
            self.direction_filter = "EXCEPTIONS"
        else:
            return
        self._update_filter_buttons()
        self._apply_filters()

    async def on_select_changed(self, event: Select.Changed) -> None:  # type: ignore[override]
        """Handle status select changes."""
        if event.select.id != "status-select":
            return
        self.status_filter = event.value or None
        self._apply_filters()

    async def on_input_changed(self, event: Input.Changed) -> None:  # type: ignore[override]
        """Handle search input changes."""
        if event.input.id != "search-input":
            return
        self.search_query = event.value or ""
        self._apply_filters()

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:  # type: ignore[override]
        """Update detail panel when selection changes."""
        info = self._get_ramp_info_by_key(event.row_key.value if event.row_key else None)
        detail = self.query_one(RampDetailPanel)
        detail.update_detail(info)

    async def on_filter_sidebar_filter_changed(self, message: FilterSidebar.FilterChanged) -> None:
        """Handle sidebar filter toggles."""
        self.overdue_only = message.overdue_only
        self.blocked_only = message.blocked_only
        self._apply_filters()

    # ------------------------------------------------------------------#
    # Key bindings
    # ------------------------------------------------------------------#
    async def action_filter_all(self) -> None:
        self.direction_filter = None
        self._update_filter_buttons()
        self._apply_filters()

    async def action_filter_inbound(self) -> None:
        self.direction_filter = "IB"
        self._update_filter_buttons()
        self._apply_filters()

    async def action_filter_outbound(self) -> None:
        self.direction_filter = "OB"
        self._update_filter_buttons()
        self._apply_filters()

    async def action_filter_exceptions(self) -> None:
        self.direction_filter = "EXCEPTIONS"
        self._update_filter_buttons()
        self._apply_filters()

    async def action_focus_search(self) -> None:
        """Place focus into search field."""
        search_input = self.query_one("#search-input", Input)
        await search_input.focus()

    async def action_quit(self) -> None:
        """Exit to login screen."""
        await self.app.pop_screen()

    # ------------------------------------------------------------------#
    # Formatting helpers
    # ------------------------------------------------------------------#
    def _format_eta(self, info: RampInfo) -> str:
        """Format ETA out for table display."""
        dt = info.eta_out_dt
        if not dt:
            return "-"
        return dt.strftime("%H:%M")

    def _format_since(self, info: RampInfo) -> str:
        """Return human friendly duration since assignment created."""
        origin = info.created_at_dt or info.updated_at_dt
        if not origin:
            return "-"
        now = datetime.now(timezone.utc)
        delta = now - origin
        minutes = int(delta.total_seconds() // 60)
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        remainder = minutes % 60
        if hours < 24:
            return f"{hours}h {remainder}m"
        days = hours // 24
        return f"{days}d"

    def _style_status(self, info: RampInfo) -> str:
        """Return status markup for table."""
        color = "green"
        if info.is_blocked:
            color = "red"
        elif info.is_overdue:
            color = "orange_red1"
        elif info.is_occupied:
            color = "yellow"
        return f"[{color}]{info.status_label}[/{color}]"

    def _get_ramp_info_by_key(self, key: Optional[str]) -> Optional[RampInfo]:
        """Resolve ramp info from DataTable key."""
        if key is None:
            return None
        for info in self.filtered_ramps:
            if str(info.ramp_id) == str(key):
                return info
        return None

    def _update_status(self, message: str) -> None:
        """Update status bar message."""
        label = self.query_one("#status-bar", Label)
        label.update(message)

    # ------------------------------------------------------------------#
    # Misc
    # ------------------------------------------------------------------#
    async def on_input_submitted(self, event: Input.Submitted) -> None:  # type: ignore[override]
        """Keep search focus even after pressing enter."""
        if event.input.id == "search-input":
            await event.input.focus()
