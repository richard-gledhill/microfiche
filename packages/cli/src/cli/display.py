"""Rich rendering helpers for the CLI's output."""

from __future__ import annotations

from core.organizer import SortReport
from core.resort import ResortProposal
from rich.console import Console
from rich.table import Table


def render_sort_report(console: Console, report: SortReport) -> None:
    console.print(f"[green]Filed:[/green] {len(report.filed)}")
    console.print(f"[yellow]Needs review:[/yellow] {len(report.needs_review)}")
    for unit, classification in report.filed:
        console.print(
            f"  {unit.source_path.name} -> {classification.group.name}/{classification.category.name} "
            f"(confidence {classification.overall_confidence:.2f}, via {classification.classified_by})"
        )
    for unit, classification in report.needs_review:
        console.print(f"  [yellow]{unit.source_path.name}[/yellow] — {classification.category.reason}")


def render_resort_table(console: Console, proposals: list[ResortProposal]) -> None:
    table = Table(title="Resort proposals (dry run)")
    table.add_column("Current path")
    table.add_column("Proposed group")
    table.add_column("Proposed category")
    table.add_column("Confidence")
    for proposal in proposals:
        table.add_row(
            str(proposal.current_path),
            proposal.proposed_group or "—",
            proposal.proposed_category or "—",
            f"{proposal.classification.overall_confidence:.2f}",
        )
    console.print(table)
