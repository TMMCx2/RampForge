"""Ramp grid screen - main view showing all ramps."""
import logging
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

from app.services import APIClient, WebSocketClient
from app.services.ramp_status import RampInfo, get_ramp_statuses
from app.widgets.ramp_tile import RampTile

logger = logging.getLogger(__name__)


class RampGridScreen(Screen):
    """Main screen showing ramps in a grid layout."""

    CSS = """
    RampGridScreen {
        layout: vertical;
    }

    #header-bar {
        width: 100%;
        height: 3;
        background: $boost;
        padding: 0 2;
        layout: horizontal;
    }

    #user-info {
        width: 1fr;
        height: 100%;
        content-align: left middle;
        color: $text;
    }

    #filter-container {
        width: auto;
        height: 100%;
        layout: horizontal;
        align: right middle;
    }

    .filter-button {
        margin: 0 1;
    }

    #status-bar {
        width: 100%;
        height: 1;
        background: $panel;
        padding: 0 2;
    }

    #ramp-grid-container {
        width: 100%;
        height: 1fr;
        overflow: auto auto;
        padding: 1 2;
    }

    #ramp-grid {
        width: 100%;
        height: auto;
        layout: vertical;
    }

    #ramp-grid Horizontal {
        width: 100%;
        height: auto;
        align: left top;
    }

    Footer {
        background: $boost;
    }
    """

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("1", "filter_all", "All"),
        ("2", "filter_free", "Free Only"),
        ("3", "filter_occupied", "Occupied Only"),
        ("escape", "quit", "Quit"),
    ]

    def __init__(
        self,
        api_client: APIClient,
        ws_client: WebSocketClient,
        user_data: Dict[str, Any],
    ) -> None:
        """Initialize ramp grid screen."""
        super().__init__()
        self.api_client = api_client
        self.ws_client = ws_client
        self.user_data = user_data
        self.current_filter: Optional[str] = None  # None, "free", "occupied"
        self.ramps: List[Dict[str, Any]] = []
        self.assignments: List[Dict[str, Any]] = []
        self.ramp_infos: List[RampInfo] = []

    def compose(self) -> ComposeResult:
        """Compose ramp grid screen."""
        yield Header()
        with Horizontal(id="header-bar"):
            yield Label(
                f"👤 {self.user_data.get('full_name')} ({self.user_data.get('role')})",
                id="user-info",
            )
            with Horizontal(id="filter-container"):
                yield Button("All Ramps", variant="primary", id="filter-all", classes="filter-button")
                yield Button("Free Only", id="filter-free", classes="filter-button")
                yield Button("Occupied Only", id="filter-occupied", classes="filter-button")
        yield Label("🔄 Connected to real-time updates", id="status-bar")
        with ScrollableContainer(id="ramp-grid-container"):
            with Container(id="ramp-grid"):
                yield Static("Loading ramps...", id="loading-placeholder")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize and load data."""
        logger.info("RampGridScreen.on_mount() started")

        # Connect WebSocket and register callbacks
        try:
            await self.ws_client.connect()
            self.ws_client.on_message("assignment_created", self._on_assignment_changed)
            self.ws_client.on_message("assignment_updated", self._on_assignment_changed)
            self.ws_client.on_message("assignment_deleted", self._on_assignment_changed)
            self._update_status("🔄 Connected to real-time updates")
            logger.info("WebSocket connected successfully")
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}", exc_info=True)
            self._update_status(f"⚠️ WebSocket connection failed: {e}. Working in offline mode.")

        # Load initial data
        await self.action_refresh()
        logger.info("RampGridScreen.on_mount() completed")

    def _on_assignment_changed(self, data: Dict[str, Any]) -> None:
        """Handle assignment change event from WebSocket."""
        logger.info("Assignment changed via WebSocket, refreshing...")
        self.run_worker(self.action_refresh())

    def _update_status(self, message: str) -> None:
        """Update status bar."""
        status_bar = self.query_one("#status-bar", Label)
        status_bar.update(message)

    async def action_refresh(self) -> None:
        """Refresh ramps and assignments from API."""
        logger.info("Refreshing ramp grid...")
        try:
            # Load ramps and assignments in parallel
            self.ramps = await self.api_client.get_ramps()
            self.assignments = await self.api_client.get_assignments()

            logger.info(f"Loaded {len(self.ramps)} ramps and {len(self.assignments)} assignments")

            # Calculate ramp statuses
            self.ramp_infos = get_ramp_statuses(self.ramps, self.assignments)

            # Refresh grid
            self._refresh_grid()

            self._update_status(f"✓ Loaded {len(self.ramps)} ramps")
        except Exception as e:
            logger.error(f"Error loading data: {e}", exc_info=True)
            self._update_status(f"❌ Error loading data: {e}")

    def _refresh_grid(self) -> None:
        """Refresh ramp grid with current data."""
        grid = self.query_one("#ramp-grid", Container)
        grid.remove_children()

        # Filter ramp infos
        filtered = self.ramp_infos
        if self.current_filter == "free":
            filtered = [r for r in self.ramp_infos if r.is_free]
        elif self.current_filter == "occupied":
            filtered = [r for r in self.ramp_infos if r.is_occupied]

        # Add ramp tiles in rows of 4
        if filtered:
            tiles_per_row = 4
            for i in range(0, len(filtered), tiles_per_row):
                row_tiles = filtered[i:i + tiles_per_row]
                # Create tiles list first
                tiles = [RampTile(ramp_info) for ramp_info in row_tiles]
                # Mount row with all tiles at once
                row = Horizontal(*tiles)
                grid.mount(row)
        else:
            grid.mount(Static("No ramps found", id="no-ramps"))

        logger.info(f"Grid refreshed with {len(filtered)} ramps")

    async def on_ramp_tile_clicked(self, message: RampTile.Clicked) -> None:
        """Handle ramp tile click."""
        ramp_info = message.ramp_info
        logger.info(f"Ramp {ramp_info.ramp_code} clicked, status: {ramp_info.status_label}")

        if ramp_info.is_free:
            self._update_status(f"🟢 Ramp {ramp_info.ramp_code} is FREE - Click to assign load")
            # TODO: Open AssignLoadModal
        elif ramp_info.is_occupied:
            self._update_status(f"🔴 Ramp {ramp_info.ramp_code} is OCCUPIED - Click to edit/release")
            # TODO: Open EditRampModal
        elif ramp_info.is_blocked:
            self._update_status(f"⚫ Ramp {ramp_info.ramp_code} is BLOCKED - Click to unblock")
            # TODO: Open BlockRampModal

    async def action_filter_all(self) -> None:
        """Show all ramps."""
        self.current_filter = None
        self._refresh_grid()
        self._update_buttons("filter-all")

    async def action_filter_free(self) -> None:
        """Show only free ramps."""
        self.current_filter = "free"
        self._refresh_grid()
        self._update_buttons("filter-free")

    async def action_filter_occupied(self) -> None:
        """Show only occupied ramps."""
        self.current_filter = "occupied"
        self._refresh_grid()
        self._update_buttons("filter-occupied")

    def _update_buttons(self, active_id: str) -> None:
        """Update filter button variants."""
        for button_id in ["filter-all", "filter-free", "filter-occupied"]:
            button = self.query_one(f"#{button_id}", Button)
            button.variant = "primary" if button_id == active_id else "default"
