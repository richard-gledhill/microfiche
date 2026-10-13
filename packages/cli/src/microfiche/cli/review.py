"""The interactive side of ``microfiche review``: showing a unit, asking what to do, and reporting what was chosen.

``microfiche.core.review.ReviewSession`` does the thinking (what is in the queue, whether a choice is allowed, filing it). This
module only asks and shows. Each unit is offered four ways out: accept the best guess, modify it (pick a group and a
category, or plan a new folder), skip it, or quit. Nothing is moved while asking.
"""

from __future__ import annotations

import sys

import typer
from microfiche.cli.display import render_job
from microfiche.core.review import ReviewItem, ReviewOutcome, ReviewSession
from rich.console import Console
from rich.markup import escape


def stdin_is_terminal() -> bool:
    """Whether there is a person to ask. ``review`` asks questions, so without one it does not run."""

    return sys.stdin.isatty()


def work_queue(console: Console, session: ReviewSession) -> None:
    """Go through the queue, asking about each unit until it is done or the person quits.

    The choices are made on ``session``; the caller then shows a summary and asks to file them.

    Args:
        console: Where to print.
        session: The queue and its choices.
    """

    total = len(session.items)
    for position, item in enumerate(session.items, start=1):
        _show_item(console, item, position, total, session.threshold)
        answer = _ask_what_to_do(console, session, item)
        if answer == "q":
            console.print("Stopping here.")
            return


def render_summary(console: Console, session: ReviewSession) -> None:
    """List the choices made, the folders that will be created for them, and how many units stay in the inbox.

    Args:
        console: Where to print.
        session: The queue and its choices.
    """

    decisions = session.decisions
    console.print(f"\nReady to file {len(decisions)} of {len(session.items)} unit(s):")
    for item, folders in decisions:
        console.print(f"  {escape(item.name)} -> {escape('/'.join(folders))}", soft_wrap=True)
    used = [
        folders for folders in session.new_folders if any(chosen[: len(folders)] == folders for _, chosen in decisions)
    ]
    if used:
        console.print("New folders, created when the units are filed:")
        for folders in used:
            console.print(f"  {escape('/'.join(folders))}", soft_wrap=True)
    staying = len(session.items) - len(decisions)
    if staying:
        console.print(f"{staying} unit(s) stay in the inbox.")


def render_outcome(console: Console, outcome: ReviewOutcome) -> None:
    """Report what filing did: the count, anything that was not filed and why, the new folders, and how to undo it.

    Args:
        console: Where to print.
        outcome: The result of ``ReviewSession.commit``.
    """

    filed = len(outcome.job.moves) if outcome.job is not None else 0
    console.print(f"[green]Filed:[/green] {filed}")
    for failure in outcome.failed:
        console.print(
            f"  [yellow]{escape(failure.unit.source_path.name)}[/yellow] stays in the inbox: {escape(failure.reason)}",
            soft_wrap=True,
        )
    for folder in outcome.created:
        console.print(f"  [dim]Created the folder[/dim] {escape(folder.name)}", soft_wrap=True)
    if outcome.job is not None:
        render_job(console, outcome.job)


def _show_item(console: Console, item: ReviewItem, position: int, total: int, threshold: float) -> None:
    """Say what the unit is, what the classifier made of it, and what it would have done."""

    unit = item.unit
    kind = f"folder, {len(unit.documents)} document(s)" if unit.kind == "folder" else "file"
    console.print(f"\n[bold]Item {position} of {total}: {escape(item.name)}[/bold] ({kind})", soft_wrap=True)
    console.print(f"  Classifier said: {escape(item.reason)}", soft_wrap=True)
    if item.suggestion is not None:
        confidence = item.classification.overall_confidence
        console.print(
            f"  Best guess: {escape('/'.join(item.suggestion))} "
            f"(confidence {confidence:.2f}; {threshold:.2f} is needed to file without asking)",
            soft_wrap=True,
        )


def _ask_what_to_do(console: Console, session: ReviewSession, item: ReviewItem) -> str:
    """Offer the choices for one unit until one is taken. Returns ``"q"`` to stop, otherwise anything else."""

    while True:
        options = {"m": "modify", "s": "skip", "q": "quit"}
        if item.suggestion is not None:
            blocked = session.problem(item, item.suggestion)
            if blocked is None:
                options = {"a": "accept the best guess", **options}
            else:
                console.print(f"  The best guess can't be used: {escape(blocked)}", soft_wrap=True)
        console.print("  " + "   ".join(f"({key}) {label}" for key, label in options.items()))
        answer = str(typer.prompt("What now?", default="s", show_default=True)).strip().lower()
        if answer not in options:
            console.print(f"  Please answer one of: {', '.join(options)}")
            continue
        if answer == "a" and item.suggestion is not None:
            problem = session.decide(item, item.suggestion)
            if problem is None:
                return answer
            console.print(f"  {escape(problem)}", soft_wrap=True)
            continue
        if answer == "m" and _modify(console, session, item):
            return answer
        if answer in {"s", "q"}:
            return answer


def _modify(console: Console, session: ReviewSession, item: ReviewItem) -> bool:
    """Ask for a group (and a category, if the library has them) and take the choice. ``False`` if it was not made."""

    group = _choose_folder(console, session, (), "group")
    if group is None:
        return False
    folders: tuple[str, ...] = (group,)
    if session.depth > 1:
        category = _choose_folder(console, session, (group,), "category")
        if category is None:
            return False
        folders = (group, category)
    problem = session.decide(item, folders)
    if problem is not None:
        console.print(f"  {escape(problem)}", soft_wrap=True)
        return False
    return True


def _choose_folder(console: Console, session: ReviewSession, parent: tuple[str, ...], level: str) -> str | None:
    """Pick a group or category by number, or plan a new one. ``None`` if the person goes back."""

    names = session.categories(parent[0]) if parent else session.groups()
    console.print(f"  Choose a {level}:")
    for number, name in enumerate(names, start=1):
        console.print(f"    {number}) {escape(name)}", soft_wrap=True)
    console.print(f"    n) a new {level}")
    console.print("    Enter) go back")
    while True:
        answer = str(typer.prompt(f"  {level.capitalize()}", default="", show_default=False)).strip().lower()
        if not answer:
            return None
        if answer == "n":
            created = _plan_new_folder(console, session, parent, level)
            if created is not None:
                return created
            continue
        if answer.isdecimal() and 1 <= int(answer) <= len(names):
            return names[int(answer) - 1]
        console.print(f"  Enter a number from the list, n for a new {level}, or press Enter to go back.")


def _plan_new_folder(console: Console, session: ReviewSession, parent: tuple[str, ...], level: str) -> str | None:
    """Ask for a name, check it, and have the exact path confirmed. The folder is only planned: it is made on filing."""

    while True:
        name = str(
            typer.prompt(f"  Name for the new {level} (Enter to cancel)", default="", show_default=False)
        ).strip()
        if not name:
            return None
        problem = session.folder_problem(parent, name)
        if problem is not None:
            console.print(f"  {escape(problem)}", soft_wrap=True)
            continue
        path = "/".join((*parent, name))
        if not typer.confirm(f"  Create '{path}' when the units are filed?", default=True):
            return None
        session.add_folder(parent, name)
        return name
