"""Rich rendering helpers for the CLI's output."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from microfiche.core.classifier import VerificationStats
from microfiche.core.config import MicroficheConfig
from microfiche.core.filer import FailedFiling
from microfiche.core.library.library_file import LIBRARY_FILENAME
from microfiche.core.library.library_sync import LibrarySync
from microfiche.core.models.job import Job
from microfiche.core.organizer import SortReport
from microfiche.core.reclassify import ReclassifyProposal
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


def render_ai_verification(console: Console, verification: VerificationStats) -> None:
    """Say how many rules answers the AI checked, confirmed and overruled. Prints nothing if it checked none."""

    if verification.checked:
        console.print(
            f"[dim]AI second opinion: {verification.checked} checked, {verification.confirmed} confirmed, "
            f"{verification.overruled} overruled (left for review).[/dim]"
        )


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
    render_ai_verification(console, report.ai_verification)
    if report.by_learned_hint:
        console.print(f"[dim]{report.by_learned_hint} filed by a hint microfiche learned from your choices.[/dim]")
    if report.into_empty_groups:
        console.print(
            f"[dim]{report.into_empty_groups} filed straight into a group because it has no category folders.[/dim]"
        )
    if report.ai_unavailable is not None:
        console.print(
            f"[yellow]The AI fallback was unavailable ({escape(report.ai_unavailable)}).[/yellow]", soft_wrap=True
        )
    _render_units(console, report)
    _render_inbox_notes(console, report)
    if report.library_sync is not None:
        render_library_sync(console, report.library_sync)
    if report.dry_run:
        if report.filed:
            console.print("Run again without --dry-run to file these.")
    elif report.job is not None:
        render_job(console, report.job)


def render_watch_batch(console: Console, report: SortReport, when: str) -> None:
    """Print one line for a batch `watch` filed: the counts, and the job that undoes it.

    Args:
        console: Where to print.
        report: The sort report of the batch.
        when: The time to show at the start of the line.
    """

    line = (
        f"{when} [green]Filed {len(report.filed)}[/green], [yellow]{len(report.needs_review)} for review[/yellow], "
        f"[cyan]{len(report.duplicates)} duplicate(s)[/cyan]"
    )
    if report.job is not None:
        line += f"; undo with `rollback --job-id {report.job.job_id}`"
    console.print(line, soft_wrap=True)
    if report.ai_unavailable is not None:
        console.print(
            f"[yellow]The AI fallback was unavailable ({escape(report.ai_unavailable)}); using the rules only.[/yellow]",
            soft_wrap=True,
        )


def render_library_sync(console: Console, sync: LibrarySync) -> None:
    """Print what a library file sync did: the file created or the folders added, and the entries with no folder.

    Prints nothing for a sync that found nothing to say.

    Args:
        console: Where to print.
        sync: The result of the sync.
    """

    if sync.write_error is not None:
        console.print(
            f"[yellow]Could not update the library file ({escape(sync.write_error)}); "
            f"{len(sync.added)} folder(s) have no entry in it yet.[/yellow]",
            soft_wrap=True,
        )
    elif sync.created:
        console.print(
            f"[dim]Created {LIBRARY_FILENAME} listing {len(sync.added)} folder(s). "
            "Add keyword hints to it to help match documents.[/dim]",
            soft_wrap=True,
        )
    else:
        for path in sync.added:
            console.print(f"  [dim]Added {escape(path)} to {LIBRARY_FILENAME}[/dim]", soft_wrap=True)
    renamed = dict(sync.possible_renames)
    for path in sync.missing:
        note = f" (renamed to {escape(renamed[path])}?)" if path in renamed else ""
        console.print(
            f"  [yellow]{escape(path)}[/yellow] is in {LIBRARY_FILENAME} but has no folder{note}", soft_wrap=True
        )
    for warning in sync.name_warnings:
        console.print(f"  [yellow]{escape(warning)}[/yellow]", soft_wrap=True)


def render_reclassify_table(
    console: Console, proposals: list[ReclassifyProposal], *, root: Path, dry_run: bool
) -> None:
    """Print one row per reclassify proposal: where it is, where it would go, and what happens.

    Args:
        console: Where to print.
        proposals: The proposals to show.
        root: The library's root; paths are shown relative to it, so the file name is not what a narrow terminal cuts off.
        dry_run: Whether the run is a preview, which is noted in the table's title.
    """

    table = Table(title="Reclassify proposals (dry run)" if dry_run else "Reclassify proposals")
    table.add_column("Current path")
    table.add_column("Proposed group")
    flat = all(proposal.classification.category is None for proposal in proposals)  # a flat library has no categories
    if not flat:
        table.add_column("Proposed category")
    table.add_column("Confidence")
    table.add_column("Action")
    for proposal in proposals:
        style = _ACTION_STYLES[proposal.action]
        cells = [escape(_shown(proposal.current_path, root)), escape(proposal.proposed_group or "—")]
        if not flat:
            cells.append(escape(proposal.proposed_category or "—"))
        table.add_row(
            *cells, f"{proposal.classification.overall_confidence:.2f}", f"[{style}]{proposal.action}[/{style}]"
        )
    console.print(table)


def render_reclassify_result(
    console: Console,
    proposals: list[ReclassifyProposal],
    *,
    root: Path,
    job: Job | None,
    dry_run: bool,
    failed: Sequence[FailedFiling] = (),
    below_depth: int = 0,
    depth: int = 2,
) -> None:
    """Summarise a reclassify run: counts by action, and either the job (applied) or how to apply.

    Args:
        console: Where to print.
        proposals: The proposals the run made.
        root: The library's root; the paths named below are shown relative to it.
        job: The job that filed the moves, or ``None`` for a dry run or if nothing moved.
        dry_run: Whether the run was a preview.
        failed: Documents that could not be moved; they stay where they were.
        below_depth: How many filed items sit in folders below the library's depth (see ``items_below_depth``).
        depth: The library's depth, named in the note about those items.
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
                f"  [yellow]{escape(_shown(proposal.current_path, root))}[/yellow] — "
                f"{escape(proposal.classification.reason)}",
                soft_wrap=True,
            )
        if proposal.action == "conflict":
            console.print(
                f"  [red]{escape(_shown(proposal.current_path, root))}[/red] — "
                f"{escape(_shown(proposal.destination, root))} is taken",
                soft_wrap=True,
            )
    for failure in failed:
        console.print(
            f"  [red]{escape(_shown(failure.unit.source_path, root))}[/red] — could not be moved: {escape(failure.reason)}",
            soft_wrap=True,
        )
    if below_depth:
        console.print(
            f"[dim]{below_depth} filed item(s) sit in folders below the library's depth ({depth}). Those folders are "
            "no longer groups or categories; an item in one stays where it is while the classifier still puts it in "
            "the group or category it is in.[/dim]",
            soft_wrap=True,
        )
    if dry_run:
        if moves:
            console.print("Re-run with --apply to move these files.")
    elif job is not None:
        render_job(console, job)


def render_job(console: Console, job: Job) -> None:
    """Print the id of the job a run filed under, and the command that undoes it.

    Args:
        console: Where to print.
        job: The job the run saved.
    """

    console.print(f"Job: {job.job_id}", soft_wrap=True)
    console.print(f"Undo with: microfiche rollback --library <your library> --job-id {job.job_id}", soft_wrap=True)


# endregion


# region Helpers


def _format_value(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={_format_value(item)}" for key, item in value.items()) if value else "—"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # the config stores 120.0; a person means 120
    return str(value)


def _shown(path: Path | None, root: Path) -> str:
    """``path`` relative to the library, with forward slashes; as it is if it lies outside, or there is none."""

    if path is None:
        return "—"
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _to_items(value: Iterable[tuple[str, Any]] | Mapping[str, Any]) -> list[tuple[str, Any]]:
    """The ``(name, value)`` pairs of a config model, or of a plain dict setting."""

    if isinstance(value, Mapping):
        return list(value.items())
    return list(value)


def _render_units(console: Console, report: SortReport) -> None:
    """One line for each unit filed, left for review, or held as a duplicate."""

    for unit, classification in report.filed:
        console.print(
            f"  {escape(unit.source_path.name)} -> {escape('/'.join(classification.folders or ()))} "
            f"(confidence {classification.overall_confidence:.2f}, via {classification.classified_by})",
            soft_wrap=True,
        )
    for unit, classification in report.needs_review:
        console.print(
            f"  [yellow]{escape(unit.source_path.name)}[/yellow] — {escape(classification.reason)}",
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


# endregion
