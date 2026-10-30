"""Working the units that ``sort`` left in the inbox: a person decides where each one goes.

``ReviewSession`` holds the queue and the choices made about it. The queue is not stored anywhere: it is what a
preview sort (``run_sort(dry_run=True)``) says needs a decision, so the inbox itself is the queue and there is
nothing to keep in step. A choice is checked the moment it is made, with the same safeguards ``sort`` uses (the
destination name is free, the content is not already in the library), and the chosen units are filed together by
``commit`` as one job that ``rollback`` can undo.

Nothing is created or moved until ``commit``. A new group or category folder is only a plan until a unit is filed
into it, so a session that is abandoned leaves the library as it was.
"""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from microfiche.core.ai.llm_classifier import LLMClassifier
from microfiche.core.config import MICROFICHE_DIRNAME
from microfiche.core.duplicates import Duplicate, DuplicateIndex
from microfiche.core.filer import DestinationClaims, FailedFiling, destination_for, file_batch
from microfiche.core.learning import LearnedHint, learn_hints
from microfiche.core.library.library import Library
from microfiche.core.models.classification import CategoryMatch, ClassificationResult, GroupMatch
from microfiche.core.models.job import Job
from microfiche.core.models.unit import SortableUnit
from microfiche.core.organizer import run_sort
from microfiche.core.utils.filesystem import is_link
from microfiche.core.utils.hashing import unit_hash

# region Constants and types

_logger = logging.getLogger(__name__)

# Characters a folder name may not contain on Windows, which is the strictest of the systems microfiche runs on.
_INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Names Windows will not make a folder of (a device name, with or without an extension) and the longest it allows.
_RESERVED_NAME = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)
_MAX_NAME_LENGTH = 255
# What a choice made here is recorded as, in the ledger's ``classified_by`` and in the reasons.
CHOSEN_BY = "user"
_CHOSEN_REASON = "Chosen in review"


@dataclass(frozen=True)
class ReviewItem:
    """One unit waiting for a decision, and what the classifier made of it.

    Attributes:
        unit: The file or folder in the inbox.
        classification: The classifier's result. It is not confident, and its reason says why the unit was left.
    """

    unit: SortableUnit
    classification: ClassificationResult

    @property
    def name(self) -> str:
        """The unit's file or folder name."""

        return self.unit.source_path.name

    @property
    def reason(self) -> str:
        """Why the unit was left for a decision."""

        return self.classification.reason

    @property
    def suggestion(self) -> tuple[str, ...] | None:
        """Where the classifier would have filed it (a complete group, and category if there are any), or ``None``."""

        return self.classification.folders


@dataclass
class ReviewOutcome:
    """What ``ReviewSession.commit`` did.

    Attributes:
        job: The job that filed the chosen units, or ``None`` if none was filed (nothing is written then).
        failed: Chosen units that were not filed and are still in the inbox, each with the reason.
        created: The group and category folders that did not exist and were created by filing into them.
        into_empty_groups: How many units were filed straight into a group because it has no category folders.
        learned: The keyword hints learned from this commit's choices (see ``microfiche.core.learning``); empty unless
            ``[learning] enabled`` is on.
    """

    job: Job | None = None
    failed: list[FailedFiling] = field(default_factory=list)
    created: list[Path] = field(default_factory=list)
    into_empty_groups: int = 0
    learned: list[LearnedHint] = field(default_factory=list)


# endregion


# region Errors


class ReviewError(ValueError):
    """Raised when a session is used wrongly: the same unit decided twice, or a folder that was not checked."""


class AlreadyDecidedError(ReviewError):
    """Raised when a unit that already has a choice is decided again."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"'{name}' has already been decided")


# endregion


# region Public API


class ReviewSession:
    """The queue of units left in the inbox and the choices made about them.

    Args:
        library: The library being worked on.
        items: The units that need a decision, in inbox order.
        duplicates: Inbox files held back because the library already has a copy. They are not part of the queue:
            a copy is not a classification question, and microfiche never deletes one.
        ai_unavailable: Why the AI fallback stopped being asked while the queue was built, or ``None``.
        waiting: How many units are confident enough for ``sort`` to file. They are not in the queue: ``review`` is for
            the rest.
    """

    def __init__(
        self,
        library: Library,
        items: list[ReviewItem],
        *,
        duplicates: list[Duplicate] | None = None,
        ai_unavailable: str | None = None,
        waiting: int = 0,
    ) -> None:
        self._library = library
        self.items = items
        self.duplicates = duplicates or []
        self.ai_unavailable = ai_unavailable
        self.waiting = waiting
        self._hashes: dict[Path, str] = {}
        self._taxonomy = library.taxonomy()
        self._new_folders: set[tuple[str, ...]] = set()
        self._decisions: dict[Path, tuple[ReviewItem, tuple[str, ...]]] = {}
        self._claims = DestinationClaims(library)
        self._duplicates = DuplicateIndex(library)

    @classmethod
    def start(
        cls,
        library: Library,
        *,
        ai_classifier: LLMClassifier | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> ReviewSession:
        """Build the queue by previewing a sort: whatever it would leave in the inbox for a decision.

        Nothing is moved, recorded or locked. Duplicates are counted but kept out of the queue.

        Args:
            library: The library whose inbox to work.
            ai_classifier: An optional AI fallback, asked as ``sort --use-ai`` would.
            progress: Told how far the classification has got, as for ``run_sort``.

        Returns:
            The session, with no choices made.
        """

        report = run_sort(library, ai_classifier=ai_classifier, dry_run=True, progress=progress)
        items = [ReviewItem(unit, classification) for unit, classification in report.needs_review]
        _logger.info("review: %d unit(s) to decide, %d duplicate(s) held", len(items), len(report.duplicates))
        return cls(
            library,
            items,
            duplicates=report.duplicates,
            ai_unavailable=report.ai_unavailable,
            waiting=len(report.filed),
        )

    @property
    def threshold(self) -> float:
        """The confidence a classification needs for ``sort`` to file a unit without asking."""

        return self._library.config.classification.confidence_threshold

    @property
    def depth(self) -> int:
        """How many levels of folders a unit is filed under: 1 for a flat library, otherwise 2."""

        return self._taxonomy.depth

    @property
    def decisions(self) -> list[tuple[ReviewItem, tuple[str, ...]]]:
        """The choices made so far, in the order they were made: each unit and the folders it will be filed under."""

        return list(self._decisions.values())

    @property
    def new_folders(self) -> list[tuple[str, ...]]:
        """The group and category folders planned but not yet created, shortest path first."""

        return sorted(self._new_folders, key=lambda folders: (len(folders), folders))

    def groups(self) -> list[str]:
        """The groups a unit can be filed under: the library's, and any planned in this session."""

        planned = {folders[0] for folders in self._new_folders}
        return sorted({*self._taxonomy.group_names, *planned}, key=str.casefold)

    def categories(self, group: str) -> list[str]:
        """The categories of ``group``: the library's, and any planned in this session. None in a flat library."""

        if self._taxonomy.is_flat:
            return []
        planned = {folders[1] for folders in self._new_folders if len(folders) == 2 and folders[0] == group}
        return sorted({*self._taxonomy.categories_for(group), *planned}, key=str.casefold)

    def item_named(self, name: str) -> ReviewItem:
        """The unit in the queue that ``name`` means: its path inside the inbox, or an absolute path to it.

        Args:
            name: The unit's name or path relative to the inbox, with either kind of slash.

        Returns:
            The queue item.

        Raises:
            ReviewError: If no unit in the queue has that name; the message says why not where it can tell (a copy of a
                document already in the library, or a unit ``sort`` would file).
        """

        wanted = self._inbox_relative(name)
        for item in self.items:
            if self._inbox_relative(item.unit.source_path) == wanted:
                return item
        for duplicate in self.duplicates:
            if self._inbox_relative(duplicate.unit.source_path) == wanted:
                message = f"'{name}' is a copy of a document already in the library: {duplicate.reason}"
                raise ReviewError(message)
        message = (
            f"'{name}' is not waiting for a decision: it is not in the inbox, or `sort` would file it "
            "(`review --list` shows what is waiting)"
        )
        raise ReviewError(message)

    def place(self, text: str) -> tuple[str, ...]:
        """The folders ``text`` names, as they are spelt on disk: ``Group/Category``, or ``Group`` where that is a place.

        Matching ignores case. A folder that does not exist is refused: units are only filed into folders that are
        there, and this never plans a new one.

        Args:
            text: The destination as a person or script wrote it, with either kind of slash.

        Returns:
            The group, and the category if the library has them, with their real names.

        Raises:
            ReviewError: If the destination is not a place a unit can be filed in this library.
        """

        parts = tuple(part for part in text.replace("\\", "/").strip("/").split("/") if part)
        if not parts or len(parts) > self.depth:
            message = f"'{text}' is not a destination: give a group" + (
                " and a category (Group/Category)" if self.depth > 1 else ""
            )
            raise ReviewError(message)
        group = _spelt(parts[0], self.groups())
        if group is None:
            message = f"there is no group called '{parts[0]}'"
            raise ReviewError(message)
        folders: tuple[str, ...] = (group,)
        if len(parts) == 2:
            category = _spelt(parts[1], self.categories(group))
            if category is None:
                message = f"there is no category called '{parts[1]}' in '{group}'"
                raise ReviewError(message)
            folders = (group, category)
        if not self._is_place(folders):
            message = f"'{text}' is not a place a unit can be filed: '{group}' also needs a category"
            raise ReviewError(message)
        return folders

    def can_file_in_group(self, group: str) -> bool:
        """Whether a unit can be filed straight into ``group``: it has no categories (existing or planned) and the
        library files into such groups (``[sorting] file_in_empty_groups``)."""

        return (
            self._library.config.sorting.file_in_empty_groups
            and not self._taxonomy.is_flat
            and group in self.groups()
            and not self.categories(group)
        )

    def folder_problem(self, parent: tuple[str, ...], name: str) -> str | None:
        """Say why a new folder called ``name`` cannot be made under ``parent``, or ``None`` if it can.

        Args:
            parent: ``()`` for a new group, or ``(group,)`` for a new category of that group.
            name: The folder name the person typed.

        Returns:
            A one-line reason, or ``None``.
        """

        if len(parent) >= self.depth:
            return "this library has no level below its groups"
        if parent and parent[0] not in self.groups():
            return f"there is no group called '{parent[0]}'"
        name = name.strip()
        problem = _name_problem(name)
        if problem is not None:
            return problem
        if not parent and name.casefold() in {
            self._library.config.library_structure.library_inbox.casefold(),
            MICROFICHE_DIRNAME.casefold(),
        }:
            return f"'{name}' is the inbox or the state folder, so it would never be used for filing"
        siblings = self.categories(parent[0]) if parent else self.groups()
        if any(sibling.casefold() == name.casefold() for sibling in siblings):
            return f"there is already a folder called '{name}' there"
        path = self._library.root.joinpath(*parent, name)
        if self._library.is_excluded(path):
            return f"'{name}' matches the inbox, the state folder or [exclusions], so it would never be used for filing"
        if path.exists() or is_link(path):
            # A link, a folder filed whole or a loose file is not a group or category, but filing into it would still land there.
            return f"'{name}' is already there as something that is not a group or category (a link, a file or a filed folder)"
        return None

    def add_folder(self, parent: tuple[str, ...], name: str) -> tuple[str, ...]:
        """Plan a new group or category folder, so units can be chosen into it. It is created when a unit is filed.

        Args:
            parent: ``()`` for a new group, or ``(group,)`` for a new category of that group.
            name: The folder name. It must pass ``folder_problem``.

        Returns:
            The folders of the new one: ``(name,)`` or ``(group, name)``.

        Raises:
            ReviewError: If the name has a problem.
        """

        problem = self.folder_problem(parent, name)
        if problem is not None:
            raise ReviewError(problem)
        folders = (*parent, name.strip())
        self._new_folders.add(folders)
        return folders

    def problem(self, item: ReviewItem, folders: tuple[str, ...]) -> str | None:
        """Say why ``item`` cannot be filed under ``folders``, or ``None`` if it could. Nothing is reserved.

        Args:
            item: A unit in the queue.
            folders: The group, and the category in a library that has them.

        Returns:
            A one-line reason: not a place a unit can be filed, the name taken there, or a copy already in the library.
        """

        return self._vet(item, folders, self._claims, self._duplicates, reserve=False)

    def decide(self, item: ReviewItem, folders: tuple[str, ...]) -> str | None:
        """Choose where ``item`` goes, unless that is not possible.

        Args:
            item: A unit in the queue that has not been decided yet.
            folders: The group, and the category in a library that has them.

        Returns:
            ``None`` if the choice was taken, otherwise the reason it was not (see ``problem``). The destination is
            then reserved, so a later choice in this session cannot take the same name.

        Raises:
            AlreadyDecidedError: If ``item`` already has a choice.
        """

        if item.unit.source_path in self._decisions:
            raise AlreadyDecidedError(item.name)
        try:
            content_hash = unit_hash(
                item.unit.source_path
            )  # before reserving: a unit that can't be read must claim nothing
        except OSError as err:
            return f"it can't be read: {err}"
        problem = self._vet(item, folders, self._claims, self._duplicates, reserve=True)
        if problem is None:
            self._hashes[item.unit.source_path] = content_hash
            self._decisions[item.unit.source_path] = (item, folders)
            _logger.debug("review: %s -> %s", item.name, "/".join(folders))
        return problem

    def commit(self) -> ReviewOutcome:
        """File every chosen unit as one job.

        The caller holds the run lock. Each choice is checked again first, because the library may have changed since
        it was made: a unit that has left the inbox, a name now taken, or a copy that has appeared stays where it is
        and is reported in ``failed``, and the rest are filed. A unit whose content has changed since it was chosen
        is not filed either. Folders that were planned are created by filing into them, so one that no unit ended up
        in is never made (or is taken back, if the move failed). The choices are used up afterwards.

        Returns:
            The job (``None`` if nothing was filed), the units that were not filed, and the folders created.
        """

        claims, duplicates = DestinationClaims(self._library), DuplicateIndex(self._library)
        outcome = ReviewOutcome()
        ready: list[tuple[SortableUnit, ClassificationResult]] = []
        for item, folders in self.decisions:
            if not item.unit.source_path.exists():
                outcome.failed.append(FailedFiling(item.unit, "it is no longer in the inbox"))
                continue
            if _changed_since(item.unit.source_path, self._hashes.get(item.unit.source_path)):
                outcome.failed.append(FailedFiling(item.unit, "it has changed since you chose where it goes"))
                continue
            problem = self._vet(item, folders, claims, duplicates, reserve=True)
            if problem is not None:
                outcome.failed.append(FailedFiling(item.unit, problem))
                continue
            ready.append((item.unit, _chosen(folders)))

        planned = {
            self._library.root.joinpath(*classification.folders[:level])
            for _, classification in ready
            if classification.folders
            for level in range(1, len(classification.folders) + 1)
        }
        missing = sorted((path for path in planned if not path.exists()), key=lambda path: len(path.parts))
        result = file_batch(self._library, ready)
        outcome.job = result.job
        outcome.failed.extend(result.failed)
        failed = {failure.unit.source_path for failure in result.failed}
        outcome.into_empty_groups = sum(
            1 for unit, c in ready if unit.source_path not in failed and len(c.folders or ()) < self.depth
        )
        if result.job is not None:
            filed_into = {
                (c.folders[0], c.folders[1])
                for unit, c in ready
                if unit.source_path not in failed and c.folders is not None and len(c.folders) == 2
            }
            outcome.learned = learn_hints(self._library, filed_into, result.job.job_id)
        # A folder made for a unit that then could not be moved is still empty: take back what was just made here.
        for path in reversed(missing):
            if path.is_dir() and not any(path.iterdir()):
                with contextlib.suppress(OSError):
                    path.rmdir()
        outcome.created = [path for path in missing if path.is_dir()]
        self._decisions.clear()  # the choices are used up: committing again files nothing twice
        self._hashes.clear()
        _logger.info(
            "review: filed %d unit(s), %d not filed, %d folder(s) created",
            len(ready) - len(result.failed),
            len(outcome.failed),
            len(outcome.created),
        )
        return outcome

    def _vet(
        self,
        item: ReviewItem,
        folders: tuple[str, ...],
        claims: DestinationClaims,
        duplicates: DuplicateIndex,
        *,
        reserve: bool,
    ) -> str | None:
        """The reason ``item`` cannot go under ``folders``, in the order ``sort`` checks: place, copy, then name."""

        if not self._is_place(folders):
            return f"'{'/'.join(folders)}' is not a place a unit can be filed in this library"
        classification = _chosen(folders)
        duplicate = duplicates.check(item.unit, classification)
        if duplicate is not None:
            return duplicate.reason
        destination = destination_for(self._library, folders, item.unit.source_path.name)
        problem = claims.claim(destination) if reserve else claims.problem(destination)
        if problem is None and reserve:
            duplicates.add(item.unit.source_path, destination)
        return problem

    def _inbox_relative(self, name: str | Path) -> str:
        """``name`` as a path inside the inbox with forward slashes; an absolute path outside it is returned as given."""

        path = Path(str(name).replace("\\", "/"))
        if path.is_absolute():
            try:
                path = path.relative_to(self._library.inbox)
            except ValueError:
                return path.as_posix()
        return path.as_posix().strip("/")

    def _is_place(self, folders: tuple[str, ...]) -> bool:
        """Whether ``folders`` is a complete place, existing or planned: a group and category for this library's depth,
        or just a group that has no categories when the library files into those."""

        if len(folders) == 1 and self.depth > 1:
            return self.can_file_in_group(folders[0])
        if len(folders) != self.depth or folders[0] not in self.groups():
            return False
        return self.depth == 1 or folders[1] in self.categories(folders[0])


# endregion


# region Helpers


def _spelt(name: str, names: list[str]) -> str | None:
    """The entry of ``names`` that is ``name`` ignoring case, as spelt there, or ``None``."""

    return next((candidate for candidate in names if candidate.casefold() == name.casefold()), None)


def _name_problem(name: str) -> str | None:
    """Say why ``name`` cannot be a folder name on any system microfiche runs on, or ``None`` if it can."""

    if not name:
        return "a folder needs a name"
    if name in {".", ".."} or _INVALID_NAME.search(name) or name.endswith("."):
        return f"'{name}' is not a valid folder name"
    if _RESERVED_NAME.match(name):
        return f"'{name}' is a reserved name on Windows"
    if len(name) > _MAX_NAME_LENGTH:
        return f"a folder name can't be longer than {_MAX_NAME_LENGTH} characters"
    return None


def _changed_since(path: Path, chosen_hash: str | None) -> bool:
    """Whether ``path`` no longer holds what was there when it was chosen (or cannot be read to tell)."""

    if chosen_hash is None:
        return False
    try:
        return unit_hash(path) != chosen_hash
    except OSError:
        return True


def _chosen(folders: tuple[str, ...]) -> ClassificationResult:
    """The classification that records a person's choice: certain, and said to be theirs."""

    group = GroupMatch(name=folders[0], confidence=1.0, reason=_CHOSEN_REASON)
    category = CategoryMatch(name=folders[1], confidence=1.0, reason=_CHOSEN_REASON) if len(folders) == 2 else None
    return ClassificationResult(
        group=group, category=category, overall_confidence=1.0, classified_by=CHOSEN_BY, confident=True
    )


# endregion
