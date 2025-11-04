"""Ramp tile widget - displays a single ramp status."""
from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.widgets import Static
from textual.message import Message

from app.services.ramp_status import RampInfo, RampStatus


class RampTile(Static):
    """A tile displaying ramp status."""

    DEFAULT_CSS = """
    RampTile {
        width: 20;
        height: 6;
        border: solid white;
        background: $surface;
        margin: 1;
        padding: 1;
        text-align: center;
    }

    RampTile.free {
        border: thick green;
    }

    RampTile.occupied {
        border: thick red;
    }

    RampTile.blocked {
        border: thick yellow;
    }
    """

    class Clicked(Message):
        """Message sent when ramp tile is clicked."""
        def __init__(self, ramp_info: RampInfo) -> None:
            super().__init__()
            self.ramp_info = ramp_info

    def __init__(self, ramp_info: RampInfo) -> None:
        """Initialize ramp tile."""
        self.ramp_info = ramp_info

        # Build display text
        lines = []
        lines.append(f"[bold]{self.ramp_info.ramp_code}[/bold]")
        lines.append(self._get_status_display())

        if self.ramp_info.is_occupied:
            lines.append(f"{self.ramp_info.load_ref}")
            if self.ramp_info.eta_out:
                eta_str = self._format_eta(self.ramp_info.eta_out)
                lines.append(f"Out: {eta_str}")
        elif self.ramp_info.is_blocked:
            notes = self.ramp_info.notes or "Blocked"
            lines.append(f"{notes[:20]}")
        else:
            lines.append("Available")

        content = "\n".join(lines)
        super().__init__(content)
        self._update_classes()

    def compose(self) -> ComposeResult:
        """Compose ramp tile - return empty since content is in __init__."""
        return []

    def _update_classes(self) -> None:
        """Update CSS classes based on status."""
        self.remove_class("free", "occupied", "blocked")

        if self.ramp_info.is_free:
            self.add_class("free")
        elif self.ramp_info.is_occupied:
            self.add_class("occupied")
        elif self.ramp_info.is_blocked:
            self.add_class("blocked")

    def _get_status_display(self) -> str:
        """Get status display string."""
        if self.ramp_info.is_free:
            return "🟢 FREE"
        elif self.ramp_info.is_occupied:
            return "🔴 OCCUPIED"
        elif self.ramp_info.is_blocked:
            return "⚫ BLOCKED"
        return "❓ UNKNOWN"

    def _format_eta(self, eta: str) -> str:
        """Format ETA for display."""
        try:
            dt = datetime.fromisoformat(eta.replace('Z', '+00:00'))
            return dt.strftime("%H:%M")
        except:
            return eta[:16] if len(eta) >= 16 else eta

    def update_ramp_info(self, ramp_info: RampInfo) -> None:
        """Update ramp information and refresh display."""
        self.ramp_info = ramp_info
        self._update_classes()
        # Just refresh - don't remove/mount
        self.refresh()

    async def on_click(self) -> None:
        """Handle click on ramp tile."""
        self.post_message(self.Clicked(self.ramp_info))
