"""Statistics panel widget."""
from typing import Any, Dict, List

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class StatsPanel(Static):
    """Panel displaying assignment statistics."""

    DEFAULT_CSS = """
    StatsPanel {
        width: 100%;
        background: $surface-darken-2;
        border: solid $panel-darken-1;
        border-radius: 1;
        padding: 1 2;
        min-height: 6;
    }

    StatsPanel .stat-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    StatsPanel .stat-section {
        margin-bottom: 1;
    }

    StatsPanel .stat-grid {
        layout: horizontal;
        column-gap: 4;
        row-gap: 1;
        flex-wrap: wrap;
    }

    StatsPanel .stat-block {
        width: auto;
    }
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize stats panel."""
        super().__init__(*args, **kwargs)
        self.assignments: List[Dict[str, Any]] = []
        self.total_ramps = 0

    def compose(self) -> ComposeResult:
        """Compose stats panel."""
        with Vertical():
            yield Static("📊 Operations snapshot", classes="stat-title")
            yield Static("", id="stats-overview", classes="stat-section")
            yield Static("", id="stats-assignments", classes="stat-section")
            yield Static("", id="stats-status", classes="stat-section")

    def update_stats(
        self,
        assignments: List[Dict[str, Any]],
        total_ramps: int = 8,
        *,
        blocked: int = 0,
        overdue: int = 0,
    ) -> None:
        """Update statistics."""
        self.assignments = assignments
        self.total_ramps = total_ramps

        # Calculate stats
        total_assignments = len(assignments)

        # Count by direction
        inbound = sum(1 for a in assignments if a.get("load", {}).get("direction") == "IB")
        outbound = total_assignments - inbound

        # Count by status
        status_counts: Dict[str, int] = {}
        for a in assignments:
            status_label = a.get("status", {}).get("label", "Unknown")
            status_counts[status_label] = status_counts.get(status_label, 0) + 1

        # Count busy ramps (unique ramps with assignments)
        busy_ramps = len(set(a.get("ramp_id") for a in assignments if a.get("ramp_id")))
        free_ramps = total_ramps - busy_ramps

        # Build stats text
        overview_lines = [
            f"[white]Total ramps[/white] {total_ramps}",
            f"[yellow]Busy[/yellow] {busy_ramps}   [green]Free[/green] {free_ramps}",
            f"[red]Blocked[/red] {blocked}   [magenta]Overdue[/magenta] {overdue}",
        ]

        assignments_lines = [
            f"[white]Assignments[/white] {total_assignments}",
            f"[cyan]Inbound[/cyan] {inbound}   [yellow]Outbound[/yellow] {outbound}",
        ]

        if status_counts:
            status_lines = ["[white]By status[/white]"]
            sorted_statuses = sorted(status_counts.items(), key=lambda x: x[1], reverse=True)
            status_lines.extend(f"• {label}: [white]{count}[/white]" for label, count in sorted_statuses)
            status_text = "\n".join(status_lines)
        else:
            status_text = "No active assignments"

        self.query_one("#stats-overview", Static).update("\n".join(overview_lines))
        self.query_one("#stats-assignments", Static).update("\n".join(assignments_lines))
        self.query_one("#stats-status", Static).update(status_text)
