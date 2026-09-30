"""Rich rendering helpers for the CLI's output."""

from __future__ import annotations

from core.config import MicroficheConfig
from core.organizer import SortReport
from core.resort import ResortProposal
from rich.console import Console
from rich.markup import escape
from rich.table import Table


def _format_value(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={_format_value(item)}" for key, item in value.items()) if value else "—"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    return str(value)


def render_config(console: Console, config: MicroficheConfig) -> None:
    table = Table(title="Library configuration")
    table.add_column("Section", style="bold cyan")
    table.add_column("Setting")
    table.add_column("Value")

    sections = list(config)
    for section_index, (section_name, section) in enumerate(sections):
        fields = list(section)
        for field_index, (field_name, value) in enumerate(fields):
            table.add_row(
                section_name if field_index == 0 else "",
                field_name,
                escape(_format_value(value)),
                end_section=field_index == len(fields) - 1 and section_index != len(sections) - 1,
            )
    console.print(table)


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
