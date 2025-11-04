"""Filter sidebar widget for dock dashboard."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Checkbox, Static


@dataclass
class SidebarSummary:
    """Simple structure with aggregate counts."""

    total: int = 0
    busy: int = 0
    blocked: int = 0
    overdue: int = 0


class FilterSidebar(Static):
    """Sidebar with quick filters and operational summary."""

    DEFAULT_CSS = """
    FilterSidebar {
        width: 28;
        height: 100%;
        background: $surface-darken-1;
        border-right: solid $panel-darken-1;
        padding: 1 1 0 1;
        layout: vertical;
        gap: 1;
    }

    FilterSidebar .sidebar-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    FilterSidebar .sidebar-summary {
        padding: 1;
        border: solid $panel;
        border-radius: 1;
        background: $surface-darken-2;
        line-height: 1.2;
    }

    FilterSidebar .sidebar-section {
        margin-bottom: 1;
    }

    FilterSidebar Checkbox {
        margin: 0 0 1 0;
    }
    """

    class FilterChanged(Message):
        """Message dispatched when sidebar filters change."""

        def __init__(self, sender: "FilterSidebar", *, overdue_only: bool, blocked_only: bool) -> None:
            super().__init__()
            self.sender = sender
            self.overdue_only = overdue_only
            self.blocked_only = blocked_only

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.overdue_only = False
        self.blocked_only = False
        self._summary_box: Optional[Static] = None

    def compose(self) -> ComposeResult:
        """Compose sidebar widgets."""
        with Vertical():
            yield Static("Filters", classes="sidebar-title")
            self._summary_box = Static("", classes="sidebar-summary")
            yield self._summary_box
            yield Static("Quick filters", classes="sidebar-section")
            yield Checkbox("Only SLA breaches", id="chk-overdue")
            yield Checkbox("Only blocked ramps", id="chk-blocked")

    def update_summary(self, summary: SidebarSummary) -> None:
        """Update sidebar aggregate data."""
        if not self._summary_box:
            return
        free = max(summary.total - summary.busy, 0)
        lines = [
            "[bold]Overview[/bold]",
            f"[white]Total[/white] {summary.total}",
            f"[yellow]Busy[/yellow] {summary.busy}   [green]Free[/green] {free}",
            f"[red]Blocked[/red] {summary.blocked}",
            f"[magenta]Overdue[/magenta] {summary.overdue}",
        ]
        self._summary_box.update("\n".join(lines))

    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:  # type: ignore[override]
        """React to checkbox toggles."""
        if event.checkbox.id == "chk-overdue":
            self.overdue_only = event.value
        elif event.checkbox.id == "chk-blocked":
            self.blocked_only = event.value

        self.post_message(
            self.FilterChanged(
                self,
                overdue_only=self.overdue_only,
                blocked_only=self.blocked_only,
            )
        )
