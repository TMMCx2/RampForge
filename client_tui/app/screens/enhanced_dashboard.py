"""Enhanced dock dashboard with table view and info panel."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
)

from app.services import APIClient, WebSocketClient
from app.services.ramp_status import RampInfo, get_ramp_statuses

logger = logging.getLogger(__name__)


class InfoPanel(Static):
    """Right-side information panel showing dock statistics."""

    DEFAULT_CSS = """
    InfoPanel {
        width: 35;
        height: 100%;
        background: $surface-darken-2;
        border-left: solid $panel;
        padding: 1 2;
        overflow-y: auto;
    }

    InfoPanel .panel-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    InfoPanel .info-section {
        margin-bottom: 2;
        padding: 1;
        background: $surface-darken-1;
        border: solid $panel-darken-1;
    }

    InfoPanel .stat-line {
        margin: 0 0 0 0;
    }
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._content: Optional[Static] = None

    def compose(self) -> ComposeResult:
        """Compose info panel layout."""
        yield Static("📊 Dock Statistics", classes="panel-title")
        self._content = Static("Loading...", classes="info-section")
        yield self._content

    def update_stats(
        self,
        total: int = 0,
        prime_free: int = 0,
        prime_occupied: int = 0,
        buffer_free: int = 0,
        buffer_occupied: int = 0,
        ib_count: int = 0,
        ob_count: int = 0,
        urgent: int = 0,
        blocked: int = 0,
    ) -> None:
        """Update statistics display."""
        if not self._content:
            return

        lines = [
            "[bold cyan]TOTAL DOCKS[/bold cyan]",
            f"Total: [white]{total}[/white]",
            "",
            "[bold yellow]PRIME DOCKS[/bold yellow]",
            f"🟢 Free: [green]{prime_free}[/green]",
            f"🔵 Occupied: [blue]{prime_occupied}[/blue]",
            "",
            "[bold magenta]BUFFER DOCKS[/bold magenta]",
            f"🟢 Free: [green]{buffer_free}[/green]",
            f"🔵 Occupied: [blue]{buffer_occupied}[/blue]",
            "",
            "[bold white]BY DIRECTION[/bold white]",
            f"📥 Inbound: [cyan]{ib_count}[/cyan]",
            f"📤 Outbound: [yellow]{ob_count}[/yellow]",
            "",
            "[bold red]ALERTS[/bold red]",
            f"🔴 Urgent: [red]{urgent}[/red]",
            f"⚠️  Blocked: [orange_red1]{blocked}[/orange_red1]",
        ]

        self._content.update("\n".join(lines))


class EnhancedDockDashboard(Screen):
    """Enhanced dashboard with table view and statistics panel."""

    CSS = """
    EnhancedDockDashboard {
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
    }

    #user-info {
        width: 1fr;
        text-align: left;
        color: $text;
    }

    #header-title {
        width: auto;
        text-align: right;
        color: $text-muted;
    }

    #filter-bar {
        width: 100%;
        height: 3;
        padding: 0 2;
        layout: horizontal;
        align: center middle;
        background: $surface;
        border-bottom: solid $boost;
    }

    #search-input {
        width: 1fr;
        margin: 0 1;
    }

    #status-bar {
        width: 100%;
        height: 1;
        background: $panel;
        padding: 0 2;
        color: $text;
    }

    #main-container {
        width: 100%;
        height: 1fr;
        layout: horizontal;
    }

    #table-container {
        width: 1fr;
        height: 100%;
        padding: 1;
        background: $surface-darken-1;
    }

    #prime-section {
        width: 100%;
        margin-bottom: 2;
    }

    #buffer-section {
        width: 100%;
        margin-bottom: 2;
    }

    .section-title {
        width: 100%;
        height: 2;
        background: $boost;
        color: $text;
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }

    #prime-table {
        width: 100%;
        height: auto;
        margin-bottom: 2;
    }

    #buffer-table {
        width: 100%;
        height: auto;
    }

    DataTable {
        background: $surface-darken-2;
        border: solid $panel-darken-1;
        height: auto;
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
        ("escape", "quit", "Quit"),
        ("ctrl+f", "focus_search", "Search"),
        ("1", "filter_all", "All"),
        ("2", "filter_ib", "IB"),
        ("3", "filter_ob", "OB"),
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
        self.search_query: str = ""
        self.direction_filter: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Compose enhanced dashboard layout."""
        yield Header()

        # Header bar
        with Horizontal(id="header-bar"):
            yield Label(
                f"👤 {self.user_data.get('full_name', 'User')} ({self.user_data.get('role', '')})",
                id="user-info",
            )
            yield Label("🚀 DCDock Operations Dashboard", id="header-title")

        # Filter bar
        with Horizontal(id="filter-bar"):
            yield Label("🔍")
            yield Input(placeholder="Search dock, load, notes...", id="search-input")
            yield Label(f"[1]All [2]IB [3]OB")

        yield Label("🔄 Initializing...", id="status-bar")

        # Main content: Table (left) + Info Panel (right)
        with Horizontal(id="main-container"):
            with Container(id="table-container"):
                # Prime section
                with Vertical(id="prime-section"):
                    yield Static("🏭 PRIME DOCKS (Gate Area)", classes="section-title")
                    yield DataTable(id="prime-table", cursor_type="row")

                # Buffer section
                with Vertical(id="buffer-section"):
                    yield Static("📦 BUFFER DOCKS (Overflow Area)", classes="section-title")
                    yield DataTable(id="buffer-table", cursor_type="row")

            yield InfoPanel()

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize dashboard and connect WebSocket."""
        logger.info("EnhancedDockDashboard mount started")

        # Setup tables
        prime_table = self.query_one("#prime-table", DataTable)
        buffer_table = self.query_one("#buffer-table", DataTable)

        for table in [prime_table, buffer_table]:
            table.add_columns(
                "Dock",
                "Zone",
                "Status",
                "Direction",
                "Load Ref",
                "ETA Out",
                "Duration",
                "Priority",
            )

        # Connect WebSocket
        try:
            await self.ws_client.connect()
            self.ws_client.on_message("assignment_created", self._handle_ws_event)
            self.ws_client.on_message("assignment_updated", self._handle_ws_event)
            self.ws_client.on_message("assignment_deleted", self._handle_ws_event)
            self._update_status("🔗 Connected to live updates")
        except Exception as exc:
            logger.exception("WebSocket connection failed")
            self._update_status(f"⚠️ Offline mode – {exc}")

        await self.action_refresh()
        logger.info("EnhancedDockDashboard mount completed")

    async def on_unmount(self) -> None:
        """Clean up WebSocket subscriptions."""
        try:
            await self.ws_client.disconnect()
        except Exception:
            logger.exception("Failed to disconnect WebSocket")

    async def action_refresh(self) -> None:
        """Reload all data from API."""
        logger.info("Refreshing dashboard data")
        try:
            self.ramps = await self.api_client.get_ramps()
            self.assignments = await self.api_client.get_assignments()
        except Exception as exc:
            logger.exception("Failed to load data")
            self._update_status(f"❌ Error loading data: {exc}")
            return

        self.ramp_infos = get_ramp_statuses(self.ramps, self.assignments)
        self._update_tables()
        self._update_info_panel()
        self._update_status(f"✓ Loaded {len(self.ramp_infos)} docks")

    def _update_tables(self) -> None:
        """Update both prime and buffer tables with filtered data."""
        # Apply filters
        filtered = self._apply_filters(self.ramp_infos)

        # Split into prime and buffer
        # Prime: docks R1-R8 (gate area)
        # Buffer: docks R9+ (overflow area)
        prime_infos = [info for info in filtered if self._is_prime_dock(info.ramp_code)]
        buffer_infos = [info for info in filtered if not self._is_prime_dock(info.ramp_code)]

        # Update tables
        self._populate_table("#prime-table", prime_infos)
        self._populate_table("#buffer-table", buffer_infos)

    def _is_prime_dock(self, ramp_code: str) -> bool:
        """Determine if dock is prime (R1-R8) or buffer (R9+)."""
        try:
            # Extract number from ramp code (e.g., "R1" -> 1)
            if ramp_code.startswith("R"):
                num = int(ramp_code[1:])
                return num <= 8
        except (ValueError, IndexError):
            pass
        return True  # Default to prime if can't parse

    def _populate_table(self, table_id: str, infos: List[RampInfo]) -> None:
        """Populate a specific table with ramp info."""
        table = self.query_one(table_id, DataTable)
        table.clear()

        # Sort by priority
        sorted_infos = self._sort_by_priority(infos)

        for info in sorted_infos:
            priority_icon = self._get_priority_icon(info)
            status_text = self._format_status(info)

            table.add_row(
                info.ramp_code,
                info.zone or "-",
                status_text,
                info.direction_label if info.direction else "-",
                info.load_ref or "-",
                self._format_eta(info),
                self._format_duration(info),
                priority_icon,
                key=str(info.ramp_id),
            )

    def _sort_by_priority(self, infos: List[RampInfo]) -> List[RampInfo]:
        """Sort by priority: overdue > blocked > occupied > free."""
        def priority_key(info: RampInfo) -> tuple:
            if info.is_overdue:
                return (0, info.ramp_code)
            elif info.is_blocked:
                return (1, info.ramp_code)
            elif info.is_occupied:
                return (2, info.ramp_code)
            else:
                return (3, info.ramp_code)

        return sorted(infos, key=priority_key)

    def _apply_filters(self, infos: List[RampInfo]) -> List[RampInfo]:
        """Apply search and direction filters."""
        filtered = []
        query = self.search_query.lower().strip()

        for info in infos:
            # Direction filter
            if self.direction_filter == "IB" and info.direction != "IB":
                continue
            if self.direction_filter == "OB" and info.direction != "OB":
                continue

            # Search filter
            if query and not info.matches_query(query):
                continue

            filtered.append(info)

        return filtered

    def _update_info_panel(self) -> None:
        """Update statistics in right panel."""
        total = len(self.ramp_infos)

        # Split by prime/buffer
        prime_infos = [info for info in self.ramp_infos if self._is_prime_dock(info.ramp_code)]
        buffer_infos = [info for info in self.ramp_infos if not self._is_prime_dock(info.ramp_code)]

        prime_free = sum(1 for info in prime_infos if info.is_free)
        prime_occupied = len(prime_infos) - prime_free

        buffer_free = sum(1 for info in buffer_infos if info.is_free)
        buffer_occupied = len(buffer_infos) - buffer_free

        ib_count = sum(1 for info in self.ramp_infos if info.direction == "IB")
        ob_count = sum(1 for info in self.ramp_infos if info.direction == "OB")

        urgent = sum(1 for info in self.ramp_infos if info.is_overdue)
        blocked = sum(1 for info in self.ramp_infos if info.is_blocked)

        panel = self.query_one(InfoPanel)
        panel.update_stats(
            total=total,
            prime_free=prime_free,
            prime_occupied=prime_occupied,
            buffer_free=buffer_free,
            buffer_occupied=buffer_occupied,
            ib_count=ib_count,
            ob_count=ob_count,
            urgent=urgent,
            blocked=blocked,
        )

    def _get_priority_icon(self, info: RampInfo) -> str:
        """Get priority icon based on ramp state."""
        if info.is_overdue:
            return "[red]🔴 URGENT[/red]"
        elif info.is_blocked:
            return "[orange_red1]🟠 BLOCK[/orange_red1]"
        elif info.is_exception:
            return "[yellow]⚠️  WARN[/yellow]"
        elif info.is_occupied:
            return "[cyan]🟢 OK[/cyan]"
        else:
            return "[dim]⚪ FREE[/dim]"

    def _format_status(self, info: RampInfo) -> str:
        """Format status with color."""
        label = info.status_label or "FREE"
        if info.is_blocked:
            return f"[red]{label}[/red]"
        elif info.is_overdue:
            return f"[orange_red1]{label}[/orange_red1]"
        elif info.is_occupied:
            return f"[yellow]{label}[/yellow]"
        else:
            return f"[green]{label}[/green]"

    def _format_eta(self, info: RampInfo) -> str:
        """Format ETA out."""
        dt = info.eta_out_dt
        if not dt:
            return "-"
        return dt.strftime("%H:%M")

    def _format_duration(self, info: RampInfo) -> str:
        """Return human friendly duration."""
        origin = info.created_at_dt or info.updated_at_dt
        if not origin:
            return "-"
        now = datetime.now(timezone.utc)
        delta = now - origin
        minutes = int(delta.total_seconds() // 60)
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h"
        days = hours // 24
        return f"{days}d"

    async def _handle_ws_event(self, _: Dict[str, Any]) -> None:
        """React to WebSocket updates."""
        await self.action_refresh()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self.search_query = event.value or ""
            self._update_tables()

    async def action_focus_search(self) -> None:
        """Focus search input."""
        search_input = self.query_one("#search-input", Input)
        await search_input.focus()

    async def action_filter_all(self) -> None:
        """Show all docks."""
        self.direction_filter = None
        self._update_tables()
        self._update_status("Filter: All docks")

    async def action_filter_ib(self) -> None:
        """Show only inbound."""
        self.direction_filter = "IB"
        self._update_tables()
        self._update_status("Filter: Inbound only")

    async def action_filter_ob(self) -> None:
        """Show only outbound."""
        self.direction_filter = "OB"
        self._update_tables()
        self._update_status("Filter: Outbound only")

    async def action_quit(self) -> None:
        """Exit to login screen."""
        await self.app.pop_screen()

    def _update_status(self, message: str) -> None:
        """Update status bar message."""
        label = self.query_one("#status-bar", Label)
        label.update(message)
