"""Build a sample library that exercises every path through `sort`, `review` and `reclassify`.

The tests use it (`tests/scripts/test_make_sample_library.py` sorts it and checks that each document ends up where
its label says), and so does the manual walkthrough in `docs/development/plan/archive/2026-10-mvp/plan.md` (Stage 6): run the script,
then follow `docs/how-to-use.md` against the folder it makes.

    uv run python scripts/make_sample_library.py <destination> [--shape depth2|flat]

``depth2`` is a library of project > document type folders (the shape the how-to describes first) with an inbox of
documents chosen so that one of them takes each route: filed by a group name, a fuzzy group name, a category name, a
keyword hint or a filename rule; held for review; held as a name clash or a copy; unreadable; too big; ignored. Real
``.docx``, ``.pdf`` and ``.eml`` files are written as well as Markdown and text. ``flat`` is the same idea for a
library of groups only (``depth = 1``), including the case where a short group name sits inside a longer word.

The destination must not exist yet. Every document is made up for this purpose, and nothing here is a real person's.
Each item carries its expected outcome, so a walkthrough can say "this should be filed under X" and be checked.
"""

from __future__ import annotations

import argparse
import email.message
import json
import shutil
import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import docx
import pymupdf

# region Constants and types

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "microfiche"  # the default per-library config folder, which a user copies as .microfiche/
INBOX = "_sorting"
OVERSIZE_LIMIT_MB = 1  # the sample config lowers [parsing] max_file_mb so a small file can be "too big"

Kind = Literal["md", "txt", "docx", "pdf", "eml", "bytes"]
Outcome = Literal["filed", "review", "duplicate", "ignored"]

# Every route a document can take, named once so a test can check the sample library leaves none out.
PATHS = frozenset({
    # How the group was found
    "group-exact-name",
    "group-fuzzy-name",
    "group-unresolved",
    # How the category was found
    "category-name",
    "category-hint",
    "category-filename-rule",
    "category-unresolved",
    # File formats
    "format-md",
    "format-txt",
    "format-docx",
    "format-pdf",
    "format-eml",
    # What happens to the unit
    "filed-loose-file",
    "filed-whole-folder",
    "folder-tie",
    "collision",
    "duplicate-of-library-file",
    "duplicate-within-inbox",
    "unreadable",
    "too-big",
    "ignored-name",
    "unsupported-type",
})


@dataclass(frozen=True)
class File:
    """One file to write.

    Attributes:
        path: Where it goes, relative to the inbox (or the library, for a filed document).
        kind: How to write it. ``bytes`` writes ``text`` encoded as it is, for a file that is not a real document.
        text: What it says.
    """

    path: str
    kind: Kind
    text: str


@dataclass(frozen=True)
class Item:
    """Something dropped in the inbox, and what `sort` is expected to do with it.

    Attributes:
        name: The inbox entry's name: a file, or the folder holding ``files``.
        files: The files to write for it; one for a loose file, several for a folder.
        outcome: ``filed`` (into ``destination``), ``review`` (left in the inbox to review), ``duplicate`` (left in the
            inbox, an exact copy), or ``ignored`` (never treated as a document at all).
        destination: For ``filed``: ``"<group>/<category>"`` (or just ``"<group>"`` in a flat library).
        reason: For ``review`` and ``duplicate``: text the reason must contain.
        covers: The routes (see ``PATHS``) this item takes.
        note: What the walkthrough should expect to see, in a sentence.
    """

    name: str
    files: tuple[File, ...]
    outcome: Outcome
    destination: str | None = None
    reason: str | None = None
    covers: frozenset[str] = frozenset()
    note: str = ""


@dataclass(frozen=True)
class SampleLibrary:
    """A library that has been built, and what to expect of it.

    Attributes:
        root: The library folder.
        shape: ``depth2`` or ``flat``.
        items: The inbox contents and the expected outcome of each.
        filed: Documents already in the library, as ``(path, expected reclassify action)``.
    """

    root: Path
    shape: str
    items: tuple[Item, ...]
    filed: tuple[tuple[str, str], ...]


# endregion


# region Errors


class TemplateChangedError(ValueError):
    """Raised when the config template no longer has a line this script edits, so the script needs updating."""

    def __init__(self, line: str) -> None:
        super().__init__(
            f"the template in microfiche/ no longer contains {line!r}; update scripts/make_sample_library.py"
        )


# endregion


# region Public API


def build_sample_library(destination: Path, shape: str = "depth2") -> SampleLibrary:
    """Write a sample library at ``destination`` and return what it holds.

    Args:
        destination: The new library's folder. It is created, and must not exist.
        shape: ``depth2`` (group > category) or ``flat`` (groups only).

    Returns:
        The library's inbox items with their expected outcomes, and its already-filed documents.

    Raises:
        FileExistsError: If ``destination`` already exists, so nothing is ever overwritten.
        ValueError: If ``shape`` is not one of the two.
    """

    if shape not in _SHAPES:
        raise ValueError(shape)
    if destination.exists():
        raise FileExistsError(destination)
    destination.mkdir(parents=True)
    shutil.copytree(TEMPLATE, destination / ".microfiche")
    (destination / INBOX).mkdir()
    return _SHAPES[shape](destination)


def main(argv: Sequence[str] | None = None) -> int:
    """Build the sample library named on the command line and say what to do with it."""

    parser = argparse.ArgumentParser(description="Build a sample library to try microfiche on.")
    parser.add_argument("destination", type=Path, help="The folder to create. It must not exist yet.")
    parser.add_argument("--shape", choices=sorted(_SHAPES), default="depth2", help="depth2 (default) or flat.")
    args = parser.parse_args(argv)
    try:
        library = build_sample_library(args.destination, args.shape)
    except FileExistsError:
        print(f"error: {args.destination} already exists; choose a folder that does not.")
        return 1
    print(f"Built a {library.shape} sample library at {library.root}")
    print(f"  {len(library.items)} inbox item(s) and {len(library.filed)} document(s) already filed.")
    print("Expected outcome of each inbox item:")
    for item in library.items:
        where = f" -> {item.destination}" if item.destination else ""
        print(f"  {item.outcome:<9} {item.name}{where}")
    return 0


# endregion


# region Helpers


def _write(root: Path, file: File) -> None:
    path = root / file.path
    path.parent.mkdir(parents=True, exist_ok=True)
    if file.kind in ("md", "txt"):
        path.write_text(file.text, encoding="utf-8", newline="\n")
    elif file.kind == "bytes":
        path.write_bytes(file.text.encode("utf-8"))
    elif file.kind == "docx":
        document = docx.Document()
        for paragraph in file.text.split("\n"):
            document.add_paragraph(paragraph)
        document.save(str(path))
    elif file.kind == "pdf":
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 545, 790), file.text, fontsize=11)
        pdf.save(str(path))
        pdf.close()
    else:  # eml
        message = email.message.EmailMessage()
        subject, _, body = file.text.partition("\n")
        message["Subject"] = subject
        message["From"] = "sam.example@example.invalid"
        message["To"] = "team@example.invalid"
        message.set_content(body)
        path.write_bytes(bytes(message))


def _write_items(library: Path, items: Sequence[Item]) -> None:
    for item in items:
        for file in item.files:
            _write(library / INBOX, file)


def _loose(
    name: str,
    kind: Kind,
    text: str,
    outcome: Outcome,
    *,
    destination: str | None = None,
    reason: str | None = None,
    covers: Collection[str] = (),
    note: str = "",
) -> Item:
    """An item that is a single loose file named ``name``; its format and, if filed, ``filed-loose-file`` are added."""

    routes = set(covers)
    if kind != "bytes":
        routes.add(f"format-{kind}")
    if outcome == "filed":
        routes.add("filed-loose-file")
    return Item(name, (File(name, kind, text),), outcome, destination, reason, frozenset(routes), note)


def _configure(library: Path, *, exclude: Sequence[str]) -> None:
    """Lower the size limit and add the folders to keep out, in the copied config."""

    config = library / ".microfiche" / "microfiche-config.toml"
    kept = ", ".join(json.dumps(name) for name in ["sorting*", "_sorting*", ".*", "_*", "attachments", *exclude])
    text = _replaced(config.read_text(encoding="utf-8"), "max_file_mb = 50", f"max_file_mb = {OVERSIZE_LIMIT_MB}")
    text = _replaced(text, 'exclude = ["sorting*", "_sorting*", ".*", "_*", "attachments"]', f"exclude = [{kept}]")
    config.write_text(text, encoding="utf-8", newline="\n")


def _replaced(text: str, old: str, new: str) -> str:
    """``text`` with ``old`` replaced by ``new``; it is an error for ``old`` not to be there (the template changed)."""

    if old not in text:
        raise TemplateChangedError(old)
    return text.replace(old, new)


# endregion


# region The depth-2 library (group > category)

_PHOENIX, _ATLAS = "Project Phoenix", "Project Atlas"
_CATEGORIES = ("01 Requirements", "02 Architecture", "03 Research", "04 Meeting Notes", "05 Correspondence")

_REQUIREMENTS_TEXT = (
    "Functional requirements for Project Phoenix\n\nThe portal must let a customer upload an invoice and see its "
    "status. Acceptance criteria are listed for each requirement."
)

# Documents already filed. The second item is what `reclassify` should do with it.
_FILED_DEPTH2: tuple[tuple[File, str], ...] = (
    (File(f"{_PHOENIX}/01 Requirements/functional-requirements.md", "md", _REQUIREMENTS_TEXT), "keep"),
    (
        File(
            f"{_PHOENIX}/03 Research/market-research.md",
            "md",
            "Project Phoenix market research\n\nA short article comparing three vendors, with a whitepaper reference.",
        ),
        "keep",
    ),
    (
        File(
            f"{_ATLAS}/02 Architecture/atlas-design.md",
            "md",
            "Project Atlas architecture\n\nThe design decision log for the Atlas services.",
        ),
        "keep",
    ),
    # Misfiled by hand: it is about architecture, so `reclassify` proposes moving it.
    (
        File(
            f"{_PHOENIX}/04 Meeting Notes/phoenix-component-notes.md",
            "md",
            "Project Phoenix architecture notes\n\nHow the components fit together.",
        ),
        "move",
    ),
    # Nothing here to go on, so `reclassify` leaves it for review.
    (File(f"{_ATLAS}/05 Correspondence/misc-note.md", "md", "Remember to book the room."), "review"),
    # Misfiled, but the right folder already holds a file of this name, so it is a conflict, never an overwrite.
    (
        File(
            f"{_ATLAS}/03 Research/atlas-design.md",
            "md",
            "Project Atlas architecture\n\nAn older draft of the design decision log.",
        ),
        "conflict",
    ),
    # In a folder the config excludes, so `reclassify` does not look at it.
    (
        File(f"{_ATLAS}/02 Architecture/attachments/diagram-notes.md", "md", "Project Phoenix architecture sketch."),
        "skip",
    ),
    (File("Archive/old-plan.md", "md", "Project Phoenix architecture, from an earlier year."), "skip"),
)


def _depth2_items() -> tuple[Item, ...]:
    packed = tuple(
        File(f"phoenix-weekly-pack/{name}", "md", text)
        for name, text in {
            "decision-log.md": "Project Phoenix design decision log: the architecture keeps one database.",
            "components.md": "Project Phoenix system diagram notes, with the architecture of each service.",
            "reading.md": "Project Phoenix research summary of one vendor article.",
        }.items()
    )
    mixed = (
        File("mixed-bag/kickoff.md", "md", "Project Phoenix meeting agenda for the kickoff."),
        File("mixed-bag/vendor.md", "md", "Project Phoenix research on a vendor whitepaper."),
    )
    return (
        _loose(
            "PhoenixArchitectureNotes.md",
            "md",
            "Project Phoenix architecture notes\n\nWhy the portal talks to one queue.",
            "filed",
            destination=f"{_PHOENIX}/02 Architecture",
            covers={"group-exact-name", "category-name"},
            note="The group name and the category name are both in the text.",
        ),
        _loose(
            "phoenix-kickoff.txt",
            "txt",
            "Project Phoenix kickoff\n\nNotes from the first meeting with the supplier.",
            "filed",
            destination=f"{_PHOENIX}/04 Meeting Notes",
            covers={"group-exact-name", "category-hint"},
            note="Only a keyword hint ('meeting') points at the category.",
        ),
        _loose(
            "architecture-overview.pdf",
            "pdf",
            "Project Atlas\n\nA one-page overview of how the Atlas services connect.",
            "filed",
            destination=f"{_ATLAS}/02 Architecture",
            covers={"group-exact-name", "category-filename-rule"},
            note="The file name matches the rule architecture*.pdf.",
        ),
        _loose(
            "requirements-v2.docx",
            "docx",
            "Project Phoenix\nThe second revision of the portal wording.",
            "filed",
            destination=f"{_PHOENIX}/01 Requirements",
            covers={"group-exact-name", "category-filename-rule"},
            note="The file name matches the rule requirements*.docx.",
        ),
        _loose(
            "supplier-reply.eml",
            "eml",
            "Re: delivery dates\nThanks for your email. Project Atlas can take delivery in March.",
            "filed",
            destination=f"{_ATLAS}/05 Correspondence",
            covers={"group-exact-name", "category-hint"},
            note="An email message: its Subject and body are read, and the word 'email' in the body is the hint.",
        ),
        _loose(
            "pheonix-sprint-review.md",
            "md",
            "Project Pheonix sprint review\n\nDemo of the upload page.",
            "filed",
            destination=f"{_PHOENIX}/04 Meeting Notes",
            covers={"group-fuzzy-name", "category-hint"},
            note="The group is misspelt; a close match to its name is enough.",
        ),
        _loose(
            "SolarNotes.md",
            "md",
            "Rooftop panels: a quote for the garage roof, and the order they should be fitted.",
            "review",
            reason="No known group name",
            covers={"group-unresolved"},
            note="Names no group, so it is left for review.",
        ),
        _loose(
            "phoenix-loose-ends.md",
            "md",
            "Project Phoenix\n\nThings to remember to chase up next week.",
            "review",
            covers={"group-exact-name", "category-unresolved"},
            note="The group is found but nothing says which category, so it is left for review.",
        ),
        _loose(
            "functional-requirements.md",
            "md",
            "Project Phoenix requirements\n\nA newer version of the functional requirements with more detail.",
            "review",
            reason="already exists",
            covers={"group-exact-name", "category-name", "collision"},
            note="It would be filed under a name the library already uses, so it is held and nothing is overwritten.",
        ),
        _loose(
            "functional-requirements-copy.md",
            "md",
            _REQUIREMENTS_TEXT,
            "duplicate",
            reason="identical to",
            covers={"duplicate-of-library-file"},
            note="An exact copy of a filed document, whatever its name.",
        ),
        _loose(
            "atlas-minutes-a.md",
            "md",
            "Project Atlas retrospective\n\nWhat went well this quarter.",
            "filed",
            destination=f"{_ATLAS}/04 Meeting Notes",
            covers={"group-exact-name", "category-hint"},
            note="The first of two identical files is filed.",
        ),
        _loose(
            "atlas-minutes-b.md",
            "md",
            "Project Atlas retrospective\n\nWhat went well this quarter.",
            "duplicate",
            reason="identical to",
            covers={"duplicate-within-inbox"},
            note="The second is held as a copy of the first, which is being filed in the same run.",
        ),
        _loose(
            "damaged-report.pdf",
            "bytes",
            "this is not a real PDF",
            "review",
            reason="Could not read",
            covers={"unreadable", "format-pdf"},
            note="Looks like a PDF but is not one; it is reported and the run carries on.",
        ),
        _loose(
            "huge-log.txt",
            "bytes",
            "x" * int(OVERSIZE_LIMIT_MB * 1024 * 1024 + 1024),
            "review",
            reason="over the",
            covers={"too-big"},
            note="Larger than [parsing] max_file_mb (set to 1 in this library), so it is not read.",
        ),
        _loose(
            "~$requirements-v2.docx",
            "bytes",
            "lock file",
            "ignored",
            covers={"ignored-name"},
            note="An Office lock file.",
        ),
        _loose("Thumbs.db", "bytes", "clutter", "ignored", covers={"ignored-name"}, note="Operating system clutter."),
        _loose(
            "site-photo.jpg", "bytes", "not text", "ignored", covers={"unsupported-type"}, note="A type with no parser."
        ),
        Item(
            "phoenix-weekly-pack",
            packed,
            "filed",
            destination=f"{_PHOENIX}/02 Architecture",
            covers=frozenset({"filed-whole-folder", "group-exact-name", "category-name", "format-md"}),
            note="Two of three documents say architecture, so the whole folder goes there.",
        ),
        Item(
            "mixed-bag",
            mixed,
            "review",
            reason="disagree",
            covers=frozenset({"folder-tie", "group-exact-name", "format-md"}),
            note="One document each way: the folder is not guessed, it is left for review.",
        ),
    )


def _build_depth2(root: Path) -> SampleLibrary:
    for category in _CATEGORIES:
        (root / _PHOENIX / category).mkdir(parents=True)
        (root / _ATLAS / category).mkdir(parents=True)
    (root / "Archive").mkdir()
    _configure(root, exclude=["Archive", "attachments"])
    for file, _ in _FILED_DEPTH2:
        _write(root, file)
    items = _depth2_items()
    _write_items(root, items)
    return SampleLibrary(root, "depth2", items, tuple((file.path, action) for file, action in _FILED_DEPTH2))


# endregion


# region The flat library (groups only)

_FLAT_GROUPS = ("Project Phoenix", "Project Atlas", "Household", "Car")
_FLAT_LIBRARY_FILE = {
    "groups": [
        {
            "name": "Household",
            "hints": ["invoice", "utility bill", "council tax"],
            "rules": [{"pattern": "statement-*.md"}],
        },
        {"name": "Project Atlas", "hints": ["budget"]},
    ]
}


def _flat_items() -> tuple[Item, ...]:
    return (
        _loose(
            "PhoenixDesignNotes.md",
            "md",
            "Project Phoenix design notes\n\nHow the upload page is laid out.",
            "filed",
            destination="Project Phoenix",
            covers={"group-exact-name"},
            note="A group is found by its name and the document is filed straight into it.",
        ),
        _loose(
            "electricity-march.md",
            "md",
            "Utility bill for March.\n\nAmount due by the 20th.",
            "filed",
            destination="Household",
            covers={"category-hint"},
            note="A hint on the Household group.",
        ),
        _loose(
            "statement-q1.md",
            "md",
            "Quarterly summary of balances.",
            "filed",
            destination="Household",
            covers={"category-filename-rule"},
            note="A filename rule on the Household group.",
        ),
        _loose(
            "HolidayIdeas.md",
            "md",
            "Ideas for the break: a budget for flights and the invoice for the deposit.",
            "review",
            reason="Keyword hints of several groups matched",
            covers={"group-unresolved"},
            note="Hints from two different groups (budget, invoice): microfiche does not choose, so it is left for review.",
        ),
        _loose(
            "scarf-pattern.md",
            "md",
            "A pattern for a wool scarf, with the stitches for each row.",
            "review",
            reason="No group keyword or name matched",
            covers={"group-unresolved"},
            note="The short group name 'Car' is inside 'scarf' but not a whole word, so it does not match.",
        ),
    )


def _build_flat(root: Path) -> SampleLibrary:
    for group in _FLAT_GROUPS:
        (root / group).mkdir()
    config = root / ".microfiche" / "microfiche-config.toml"
    config.write_text(
        _replaced(config.read_text(encoding="utf-8"), "depth = 2", "depth = 1"), encoding="utf-8", newline="\n"
    )
    (root / ".microfiche" / "microfiche-library.json").write_text(
        json.dumps(_FLAT_LIBRARY_FILE, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    _write(root, File("Project Phoenix/kickoff-notes.md", "md", "Project Phoenix kickoff notes."))
    _write(root, File("Household/boiler-service.md", "md", "Boiler service record for the house."))
    items = _flat_items()
    _write_items(root, items)
    return SampleLibrary(
        root,
        "flat",
        items,
        (("Project Phoenix/kickoff-notes.md", "keep"), ("Household/boiler-service.md", "keep")),
    )


_SHAPES = {"depth2": _build_depth2, "flat": _build_flat}

# endregion


if __name__ == "__main__":
    sys.exit(main())
