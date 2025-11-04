"""Ramp detail panel widget."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from app.services.ramp_status import RampInfo


class RampDetailPanel(Static):
    """Panel that shows ramp and load details for the selected row."""

    DEFAULT_CSS = """
    RampDetailPanel {
        width: 38;
        height: 100%;
        background: $surface-darken-2;
        border-left: solid $panel-darken-1;
        padding: 1 2;
    }

    RampDetailPanel .panel-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    RampDetailPanel .section {
        margin-bottom: 1;
        line-height: 1.2;
    }
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._content_box: Optional[Static] = None
        self._current_ramp: Optional[RampInfo] = None

    def compose(self) -> ComposeResult:
        """Compose the panel layout."""
        with Vertical():
            yield Static("Ramp Details", classes="panel-title")
            content = Static("Select a ramp to view details.", classes="section")
            self._content_box = content
            yield content

    def update_detail(self, ramp_info: Optional[RampInfo]) -> None:
        """Refresh panel content."""
        self._current_ramp = ramp_info
        if not self._content_box:
            return

        if ramp_info is None:
            self._content_box.update("Select a ramp to view details.")
            return

        lines = [
            "[bold cyan]Ramp[/bold cyan]",
            f"Code: [white]{ramp_info.ramp_code}[/white]",
        ]
        if ramp_info.zone:
            lines.append(f"Zone: [white]{ramp_info.zone}[/white]")
        lines.append("")

        lines.append("[bold yellow]Load[/bold yellow]")
        lines.append(f"Status: [white]{ramp_info.status_label}[/white]")
        lines.append(f"Direction: [white]{ramp_info.direction_label}[/white]")
        load_ref = ramp_info.load_ref or "-"
        lines.append(f"Reference: [white]{load_ref}[/white]")

        eta_in = self._format_dt(ramp_info.eta_in_dt)
        eta_out = self._format_dt(ramp_info.eta_out_dt)
        lines.append(f"ETA In: [white]{eta_in}[/white]")
        lines.append(f"ETA Out: [white]{eta_out}[/white]")

        if ramp_info.notes:
            lines.append("")
            lines.append("[bold green]Notes[/bold green]")
            lines.append(ramp_info.notes.strip())

        lines.append("")
        lines.append("[bold magenta]Activity[/bold magenta]")
        updated = self._format_dt(ramp_info.updated_at_dt)
        created = self._format_dt(ramp_info.created_at_dt)
        lines.append(f"Created: [white]{created}[/white]")
        lines.append(f"Updated: [white]{updated}[/white]")
        if ramp_info.last_event_user:
            lines.append(f"By: [white]{ramp_info.last_event_user}[/white]")
        if ramp_info.version is not None:
            lines.append(f"Version: [white]{ramp_info.version}[/white]")

        self._content_box.update("\n".join(lines))

    def _format_dt(self, value: Optional[datetime]) -> str:
        """Format datetimes nicely for the sidebar."""
        if not value:
            return "-"
        return value.strftime("%Y-%m-%d %H:%M")
