"""Modal for editing assignments."""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from app.services import APIClient, APIError

logger = logging.getLogger(__name__)


class EditAssignmentModal(ModalScreen[Optional[Dict[str, Any]]]):
    """Modal screen for editing an existing assignment."""

    CSS = """
    EditAssignmentModal {
        align: center middle;
    }

    #modal-container {
        width: 80;
        height: auto;
        border: thick $warning 80%;
        background: $surface;
        padding: 1 2;
    }

    #modal-title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    #assignment-info {
        width: 100%;
        background: $panel;
        padding: 1;
        margin-bottom: 1;
        color: $text-muted;
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

    def __init__(self, api_client: APIClient, assignment: Dict[str, Any]) -> None:
        """Initialize edit assignment modal."""
        super().__init__()
        self.api_client = api_client
        self.assignment = assignment
        self.statuses: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        """Compose modal."""
        with Vertical(id="modal-container"):
            yield Static(f"Edit Assignment #{self.assignment['id']}", id="modal-title")

            # Show current ramp and load (read-only)
            ramp = self.assignment.get('ramp', {})
            load = self.assignment.get('load', {})
            info_text = (
                f"Ramp: {ramp.get('code', 'N/A')} - {ramp.get('description', '')}\n"
                f"Load: {load.get('reference', 'N/A')} ({load.get('direction', '')})"
            )
            yield Static(info_text, id="assignment-info")

            yield Label("Status:", classes="field-label")
            yield Select(
                [(f"Loading...", "")],
                id="status-select",
                prompt="Select status",
            )

            yield Label("ETA In (YYYY-MM-DD HH:MM):", classes="field-label")
            yield Input(
                value=self._format_datetime(self.assignment.get('eta_in')),
                id="eta-in-input",
            )

            yield Label("ETA Out (YYYY-MM-DD HH:MM):", classes="field-label")
            yield Input(
                value=self._format_datetime(self.assignment.get('eta_out')),
                id="eta-out-input",
            )

            with Container(id="button-container"):
                yield Button("Save", variant="primary", id="save-button")
                yield Button("Cancel", variant="default", id="cancel-button")

            yield Static("", id="loading-message")
            yield Static("", id="error-message")

    async def on_mount(self) -> None:
        """Load statuses from API on mount."""
        loading_msg = self.query_one("#loading-message", Static)
        loading_msg.update("⏳ Loading statuses...")

        try:
            # Load statuses from API
            self.statuses = await self.api_client.get_statuses()

            # Update select widget
            status_select = self.query_one("#status-select", Select)
            status_select.set_options(
                [(f"{s['label']}", str(s['id'])) for s in self.statuses]
            )

            # Set current status as selected
            current_status_id = str(self.assignment.get('status_id', ''))
            status_select.value = current_status_id

            loading_msg.update("")
            logger.info(f"Loaded {len(self.statuses)} statuses")

        except Exception as e:
            logger.error(f"Error loading statuses: {e}", exc_info=True)
            error_msg = self.query_one("#error-message", Static)
            error_msg.update(f"❌ Error loading data: {e}")
            loading_msg.update("")

    def _format_datetime(self, dt: Optional[str]) -> str:
        """Format datetime for input."""
        if not dt:
            return ""
        try:
            # Parse ISO format and return YYYY-MM-DD HH:MM
            parsed = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            return parsed.strftime("%Y-%m-%d %H:%M")
        except:
            return dt[:16] if len(dt) >= 16 else dt

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-button":
            self.dismiss(None)
        elif event.button.id == "save-button":
            await self.update_assignment()

    async def update_assignment(self) -> None:
        """Update assignment via API."""
        error_msg = self.query_one("#error-message", Static)
        loading_msg = self.query_one("#loading-message", Static)
        save_button = self.query_one("#save-button", Button)

        error_msg.update("")

        # Get values
        status_select = self.query_one("#status-select", Select)
        eta_in_input = self.query_one("#eta-in-input", Input)
        eta_out_input = self.query_one("#eta-out-input", Input)

        status_id = status_select.value
        eta_in = eta_in_input.value.strip()
        eta_out = eta_out_input.value.strip()

        # Validate
        if not status_id or status_id == Select.BLANK:
            error_msg.update("❌ Please select a status")
            return

        # Disable button
        save_button.disabled = True
        loading_msg.update("⏳ Updating assignment...")

        try:
            # Parse dates
            eta_in_dt = datetime.strptime(eta_in, "%Y-%m-%d %H:%M") if eta_in else None
            eta_out_dt = datetime.strptime(eta_out, "%Y-%m-%d %H:%M") if eta_out else None

            # Prepare update data with version for optimistic locking
            data = {
                "status_id": int(status_id),
                "version": self.assignment['version'],
            }

            if eta_in_dt:
                data["eta_in"] = eta_in_dt.isoformat()
            if eta_out_dt:
                data["eta_out"] = eta_out_dt.isoformat()

            # Update assignment
            assignment = await self.api_client.update_assignment(
                self.assignment['id'],
                data
            )
            logger.info(f"Updated assignment: {assignment['id']}")

            # Success - close modal and return updated assignment
            self.dismiss(assignment)

        except ValueError as e:
            error_msg.update(f"❌ Invalid date format. Use: YYYY-MM-DD HH:MM")
            save_button.disabled = False
            loading_msg.update("")
        except APIError as e:
            if e.status_code == 409:
                # Version conflict
                error_msg.update(f"⚠️ Conflict: Another user modified this assignment. Please refresh.")
            else:
                error_msg.update(f"❌ Error: {e.detail[:50]}")
            save_button.disabled = False
            loading_msg.update("")
        except Exception as e:
            logger.error(f"Error updating assignment: {e}", exc_info=True)
            error_msg.update(f"❌ Error: {str(e)[:50]}")
            save_button.disabled = False
            loading_msg.update("")
