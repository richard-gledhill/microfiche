"""Rich rendering helpers for the CLI's output."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from core.config import MicroficheConfig
from core.filer import FailedFiling
from core.models.job import Job
from core.organizer import SortReport
from core.reclassify import ReclassifyProposal
from rich.console import Console
from rich.markup import escape
from rich.table import Table

# region Constants and types

_ACTION_STYLES = {"move": "green", "keep": "dim", "review": "yellow", "conflict": "red"}

# endregion


# region Public API


def render_config(console: Console, config: MicroficheConfig) -> None:
    """Print the library's configuration as a table, one row per setting.

    Args:
        console: Where to print.
        config: The configuration to show.
    """

    table = Table(title="Library configuration")
    table.add_column("Section", style="bold cyan")
    table.add_column("Setting")
    table.add_column("Value")

    sections = _to_items(config)
    for section_index, (section_name, section) in enumerate(sections):
        fields = _to_items(section)
        if fields:
            for field_index, (field_name, value) in enumerate(fields):
                table.add_row(
                    section_name if field_index == 0 else "",
                    field_name,
                    escape(_format_value(value)),
                    end_section=field_index == len(fields) - 1 and section_index != len(sections) - 1,
                )
        else:
            table.add_row(
                section_name,
                "",
                escape(_format_value(section)),
                end_section=section_index != len(sections) - 1,
            )
    console.print(table)


def render_sort_report(console: Console, report: SortReport) -> None:
    """Print what a sort run filed and what it left for review, then the job to undo it.

    A preview (``report.dry_run``) is labelled as one and says what *would* happen; it has no job.

    Args:
        console: Where to print.
        report: The result of the sort run.
    """

    if report.dry_run:
        console.print("[bold]Preview:[/bold] nothing was moved, and nothing was recorded.")
    console.print(f"[green]{'Would file' if report.dry_run else 'Filed'}:[/green] {len(report.filed)}")
    console.print(f"[yellow]Needs review:[/yellow] {len(report.needs_review)}")
    console.print(f"[cyan]Duplicates (left in the inbox):[/cyan] {len(report.duplicates)}")
    _render_units(console, report)
    _render_inbox_notes(console, report)
    if report.dry_run:
        if report.filed:
            console.print("Run again without --dry-run to file these.")
    elif report.job is not None:
        _render_job(console, report.job)


def render_reclassify_table(console: Console, proposals: list[ReclassifyProposal], *, dry_run: bool) -> None:
    """Print one row per reclassify proposal: where it is, where it would go, and what happens.

    Args:
        console: Where to print.
        proposals: The proposals to show.
        dry_run: Whether the run is a preview, which is noted in the table's title.
    """

    table = Table(title="Reclassify proposals (dry run)" if dry_run else "Reclassify proposals")
    table.add_column("Current path")
    table.add_column("Proposed group")
    table.add_column("Proposed category")
    table.add_column("Confidence")
    table.add_column("Action")
    for proposal in proposals:
        style = _ACTION_STYLES[proposal.action]
        table.add_row(
            escape(str(proposal.current_path)),
            escape(proposal.proposed_group or "—"),
            escape(proposal.proposed_category or "—"),
            f"{proposal.classification.overall_confidence:.2f}",
            f"[{style}]{proposal.action}[/{style}]",
        )
    console.print(table)


def render_reclassify_result(
    console: Console,
    proposals: list[ReclassifyProposal],
    *,
    job: Job | None,
    dry_run: bool,
    failed: Sequence[FailedFiling] = (),
) -> None:
    """Summarise a reclassify run: counts by action, and either the job (applied) or how to apply.

    Args:
        console: Where to print.
        proposals: The proposals the run made.
        job: The job that filed the moves, or ``None`` for a dry run or if nothing moved.
        dry_run: Whether the run was a preview.
        failed: Documents that could not be moved; they stay where they were.
    """

    counts = {action: sum(1 for proposal in proposals if proposal.action == action) for action in _ACTION_STYLES}
    moves = counts["move"]
    if dry_run:
        console.print(f"Would move: {moves}")
    else:
        console.print(f"[green]Moved:[/green] {moves - len(failed)}")
    console.print(
        f"Already in place: {counts['keep']}  Needs review (not moved): {counts['review']}  "
        f"Skipped, destination taken: {counts['conflict']}"
    )
    for proposal in proposals:
        if proposal.classification.classified_by == "unreadable":
            console.print(
                f"  [yellow]{escape(str(proposal.current_path))}[/yellow] — {escape(proposal.classification.category.reason)}",
                soft_wrap=True,
            )
        if proposal.action == "conflict":
            console.print(
                f"  [red]{escape(str(proposal.current_path))}[/red] — {escape(str(proposal.destination))} is taken",
                soft_wrap=True,
            )
    for failure in failed:
        console.print(
            f"  [red]{escape(str(failure.unit.source_path))}[/red] — could not be moved: {escape(failure.reason)}",
            soft_wrap=True,
        )
    if dry_run:
        if moves:
            console.print("Re-run with --apply to move these files.")
    elif job is not None:
        _render_job(console, job)


# endregion


# region Helpers


def _format_value(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={_format_value(item)}" for key, item in value.items()) if value else "—"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    return str(value)


def _to_items(value: Iterable[tuple[str, Any]] | Mapping[str, Any]) -> list[tuple[str, Any]]:
    """The ``(name, value)`` pairs of a config model, or of a plain dict setting."""

    if isinstance(value, Mapping):
        return list(value.items())
    return list(value)


def _render_units(console: Console, report: SortReport) -> None:
    """One line for each unit filed, left for review, or held as a duplicate."""

    for unit, classification in report.filed:
        console.print(
            f"  {unit.source_path.name} -> {classification.group.name}/{classification.category.name} "
            f"(confidence {classification.overall_confidence:.2f}, via {classification.classified_by})"
        )
    for unit, classification in report.needs_review:
        console.print(
            f"  [yellow]{escape(unit.source_path.name)}[/yellow] — {escape(classification.category.reason)}",
            soft_wrap=True,
        )
    for duplicate in report.duplicates:
        console.print(
            f"  [cyan]{escape(duplicate.unit.source_path.name)}[/cyan] — {escape(duplicate.reason)}", soft_wrap=True
        )


def _render_inbox_notes(console: Console, report: SortReport) -> None:
    """Notes about the inbox itself: links skipped, and folders removed or kept."""

    for link in report.skipped_links:
        console.print(
            f"  [dim]Skipped {escape(link.name)}: links and junctions are never followed[/dim]", soft_wrap=True
        )
    for folder in report.folders_removed:
        removal = "Would remove the emptied inbox folder" if report.dry_run else "Removed the emptied inbox folder"
        console.print(f"  [dim]{removal}[/dim] {escape(folder.name)}", soft_wrap=True)
    for folder, reason in report.folders_kept:
        console.print(f"  [yellow]{escape(folder.name)}[/yellow] stays in the inbox: {escape(reason)}", soft_wrap=True)


def _render_job(console: Console, job: Job) -> None:
    console.print(f"Job: {job.job_id}", soft_wrap=True)
    console.print(f"Undo with: microfiche rollback --library <your library> --job-id {job.job_id}", soft_wrap=True)


# endregion
