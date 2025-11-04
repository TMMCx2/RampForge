"""Modal for creating new assignments."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from app.services import APIClient

logger = logging.getLogger(__name__)


class CreateAssignmentModal(ModalScreen[Optional[Dict[str, Any]]]):
    """Modal screen for creating a new assignment."""

    CSS = """
    CreateAssignmentModal {
        align: center middle;
    }

    #modal-container {
        width: 80;
        height: auto;
        border: thick $primary 80%;
        background: $surface;
        padding: 1 2;
    }

    #modal-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    .field-label {
        margin-top: 1;
        margin-bottom: 0;
        color: $text;
    }

    Select {
        margin-bottom: 1;
        width: 100%;
    }

    Input {
        margin-bottom: 1;
        width: 100%;
    }

    #button-container {
        layout: horizontal;
        width: 100%;
        height: auto;
        margin-top: 1;
    }

    #button-container Button {
        width: 1fr;
        margin: 0 1;
    }

    #error-message {
        color: $error;
        text-align: center;
        margin-top: 1;
        height: auto;
    }

    #loading-message {
        color: $accent;
        text-align: center;
        margin-top: 1;
        height: auto;
    }
    """

    def __init__(self, api_client: APIClient) -> None:
        """Initialize create assignment modal."""
        super().__init__()
        self.api_client = api_client
        self.ramps: List[Dict[str, Any]] = []
        self.loads: List[Dict[str, Any]] = []
        self.statuses: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        """Compose modal."""
        with Vertical(id="modal-container"):
            yield Static("Create New Assignment", id="modal-title")

            yield Label("Ramp:", classes="field-label")
            yield Select(
                [(f"Loading...", "")],
                id="ramp-select",
                prompt="Select ramp",
            )

            yield Label("Load:", classes="field-label")
            yield Select(
                [(f"Loading...", "")],
                id="load-select",
                prompt="Select load",
            )

            yield Label("Status:", classes="field-label")
            yield Select(
                [(f"Loading...", "")],
                id="status-select",
                prompt="Select status",
            )

            yield Label("ETA In (YYYY-MM-DD HH:MM):", classes="field-label")
            yield Input(
                placeholder=self._default_eta_in(),
                id="eta-in-input",
            )

            yield Label("ETA Out (YYYY-MM-DD HH:MM):", classes="field-label")
            yield Input(
                placeholder=self._default_eta_out(),
                id="eta-out-input",
            )

            with Container(id="button-container"):
                yield Button("Create", variant="primary", id="create-button")
                yield Button("Cancel", variant="default", id="cancel-button")

            yield Static("", id="loading-message")
            yield Static("", id="error-message")

    async def on_mount(self) -> None:
        """Load data from API on mount."""
        loading_msg = self.query_one("#loading-message", Static)
        loading_msg.update("⏳ Loading data...")

        try:
            # Load ramps, loads, and statuses from API
            self.ramps = await self.api_client.get_ramps()
            self.loads = await self.api_client.get_loads()
            self.statuses = await self.api_client.get_statuses()

            # Update select widgets
            ramp_select = self.query_one("#ramp-select", Select)
            ramp_select.set_options(
                [(f"{r['code']} - {r.get('description', '')}", str(r['id'])) for r in self.ramps]
            )

            load_select = self.query_one("#load-select", Select)
            load_select.set_options(
                [(f"{l['reference']} ({l['direction']}) - {l.get('notes', '')[:30]}", str(l['id']))
                 for l in self.loads]
            )

            status_select = self.query_one("#status-select", Select)
            status_select.set_options(
                [(f"{s['label']}", str(s['id'])) for s in self.statuses]
            )

            loading_msg.update("")
            logger.info(f"Loaded {len(self.ramps)} ramps, {len(self.loads)} loads, {len(self.statuses)} statuses")

        except Exception as e:
            logger.error(f"Error loading data: {e}", exc_info=True)
            error_msg = self.query_one("#error-message", Static)
            error_msg.update(f"❌ Error loading data: {e}")
            loading_msg.update("")

    def _default_eta_in(self) -> str:
        """Get default ETA in (now + 1 hour)."""
        dt = datetime.now() + timedelta(hours=1)
        return dt.strftime("%Y-%m-%d %H:%M")

    def _default_eta_out(self) -> str:
        """Get default ETA out (now + 3 hours)."""
        dt = datetime.now() + timedelta(hours=3)
        return dt.strftime("%Y-%m-%d %H:%M")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-button":
            self.dismiss(None)
        elif event.button.id == "create-button":
            await self.create_assignment()

    async def create_assignment(self) -> None:
        """Create assignment via API."""
        error_msg = self.query_one("#error-message", Static)
        loading_msg = self.query_one("#loading-message", Static)
        create_button = self.query_one("#create-button", Button)

        error_msg.update("")

        # Get values
        ramp_select = self.query_one("#ramp-select", Select)
        load_select = self.query_one("#load-select", Select)
        status_select = self.query_one("#status-select", Select)
        eta_in_input = self.query_one("#eta-in-input", Input)
        eta_out_input = self.query_one("#eta-out-input", Input)

        ramp_id = ramp_select.value
        load_id = load_select.value
        status_id = status_select.value
        eta_in = eta_in_input.value.strip() or self._default_eta_in()
        eta_out = eta_out_input.value.strip() or self._default_eta_out()

        # Validate
        if not ramp_id or ramp_id == Select.BLANK:
            error_msg.update("❌ Please select a ramp")
            return

        if not load_id or load_id == Select.BLANK:
            error_msg.update("❌ Please select a load")
            return

        if not status_id or status_id == Select.BLANK:
            error_msg.update("❌ Please select a status")
            return

        # Disable button
        create_button.disabled = True
        loading_msg.update("⏳ Creating assignment...")

        try:
            # Parse dates
            eta_in_dt = datetime.strptime(eta_in, "%Y-%m-%d %H:%M")
            eta_out_dt = datetime.strptime(eta_out, "%Y-%m-%d %H:%M")

            # Create assignment
            data = {
                "ramp_id": int(ramp_id),
                "load_id": int(load_id),
                "status_id": int(status_id),
                "eta_in": eta_in_dt.isoformat(),
                "eta_out": eta_out_dt.isoformat(),
            }

            assignment = await self.api_client.create_assignment(data)
            logger.info(f"Created assignment: {assignment['id']}")

            # Success - close modal and return assignment
            self.dismiss(assignment)

        except ValueError as e:
            error_msg.update(f"❌ Invalid date format. Use: YYYY-MM-DD HH:MM")
            create_button.disabled = False
            loading_msg.update("")
        except Exception as e:
            logger.error(f"Error creating assignment: {e}", exc_info=True)
            error_msg.update(f"❌ Error: {str(e)[:50]}")
            create_button.disabled = False
            loading_msg.update("")
