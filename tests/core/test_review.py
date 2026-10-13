"""Tests for the review session: the queue a sort leaves, the choices made about it, and filing them."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import LinkMaker
from microfiche.core.config import MICROFICHE_DIRNAME
from microfiche.core.filer import rollback_job
from microfiche.core.ledger import Ledger
from microfiche.core.library.library import Library
from microfiche.core.models.ledger import LedgerRecord
from microfiche.core.review import AlreadyDecidedError, ReviewError, ReviewItem, ReviewSession
from microfiche.core.utils.hashing import file_hash

# region Test helpers


_MOCK_LIBRARY = Path(__file__).resolve().parents[1] / "mock_library"
_MOCK_FLAT_LIBRARY = Path(__file__).resolve().parents[1] / "mock_flat_library"

_SOLAR = "SolarConstructionNotes.md"  # names no group: unresolved, so it is always left for a decision
_PHOENIX = "PhoenixArchitectureNotes.md"  # group and category found: confident unless the threshold is raised
_PACK = "phoenix-weekly-pack"
_ARCHITECTURE = ("Project Phoenix", "02 Architecture")
_RESEARCH = ("Project Phoenix", "03 Research")


def _library(tmp_path: Path, *, with_pack: bool = False) -> Path:
    library = tmp_path / "library"
    shutil.copytree(_MOCK_LIBRARY, library)
    if not with_pack:
        shutil.rmtree(library / "_sorting" / _PACK)
    return library


def _session(root: Path, *, threshold: float | None = None, keep_folders: bool | None = None) -> ReviewSession:
    library = Library(root)
    if threshold is not None:
        library.config.classification.confidence_threshold = threshold
    if keep_folders is not None:
        library.config.sorting.keep_folders = keep_folders
    return ReviewSession.start(library)


def _same_name_twice(root: Path) -> None:
    """A second inbox file with the same name, from a sub-folder; it is its own unit when folders are not kept whole."""

    (root / "_sorting" / "other").mkdir()
    (root / "_sorting" / "other" / _SOLAR).write_text("a different document with the same name", encoding="utf-8")


def _filed_whole(path: str) -> LedgerRecord:
    return LedgerRecord(
        event="filed",
        job_id="job1",
        path=path,
        original_path="_sorting/pack",
        content_hash="hash",
        unit_type="folder",
        group="Project Phoenix",
    )


def _item(session: ReviewSession, name: str) -> ReviewItem:
    (item,) = [item for item in session.items if item.name == name]
    return item


def _snapshot(library: Path) -> dict[str, str]:
    """Every file (by content hash) and every folder in the library, ignoring microfiche's own state folder."""

    state_dir = library / MICROFICHE_DIRNAME
    return {
        path.relative_to(library).as_posix(): file_hash(path) if path.is_file() else "<folder>"
        for path in sorted(library.rglob("*"))
        if not path.is_relative_to(state_dir)
    }


# endregion


# region Public API


# region ReviewSession.start


def test_start_queue_is_what_a_preview_sort_leaves(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))

    assert [item.name for item in session.items] == [_SOLAR]  # the Phoenix note would be filed, so it is not queued


def test_start_unresolved_item_has_a_reason_and_no_suggestion(tmp_path: Path) -> None:
    item = _item(_session(_library(tmp_path)), _SOLAR)

    assert item.suggestion is None
    assert "group" in item.reason.lower()


def test_start_below_threshold_item_keeps_its_suggestion(tmp_path: Path) -> None:
    session = _session(_library(tmp_path), threshold=0.95)

    item = _item(session, _PHOENIX)

    assert item.suggestion == _ARCHITECTURE
    assert item.classification.overall_confidence < 0.95


def test_start_moves_nothing_and_writes_nothing(tmp_path: Path) -> None:
    root = _library(tmp_path, with_pack=True)
    before = _snapshot(root)

    _session(root, threshold=0.95)

    assert _snapshot(root) == before
    assert not (root / MICROFICHE_DIRNAME / "rollback").exists()
    assert not Ledger(root / MICROFICHE_DIRNAME).path.exists()


def test_start_duplicates_are_counted_but_not_queued(tmp_path: Path) -> None:
    root = _library(tmp_path)
    shutil.copyfile(root / "_sorting" / _SOLAR, root / "Project Phoenix" / "03 Research" / "older-solar.md")

    session = _session(root)

    assert session.items == []
    assert [duplicate.unit.source_path.name for duplicate in session.duplicates] == [_SOLAR]


def test_start_folder_unit_is_one_item(tmp_path: Path) -> None:
    session = _session(_library(tmp_path, with_pack=True), threshold=0.95)

    item = _item(session, _PACK)

    assert item.unit.kind == "folder"
    assert len(item.unit.documents) == 3


# endregion


# region ReviewSession.threshold


def test_threshold_is_the_librarys(tmp_path: Path) -> None:
    assert _session(_library(tmp_path)).threshold == 0.75
    assert _session(_library(tmp_path / "again"), threshold=0.9).threshold == 0.9


# endregion


# region ReviewSession.groups and categories


def test_groups_and_categories_come_from_the_folders(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))

    assert session.groups() == ["Project Phoenix"]
    assert session.categories("Project Phoenix") == ["01 Requirements", "02 Architecture", "03 Research"]
    assert session.categories("Nowhere") == []
    assert session.depth == 2


def test_groups_and_categories_include_planned_folders(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))
    session.add_folder((), "Project Atlas")
    session.add_folder(("Project Phoenix",), "04 Meeting Notes")

    assert session.groups() == ["Project Atlas", "Project Phoenix"]
    assert "04 Meeting Notes" in session.categories("Project Phoenix")
    assert session.new_folders == [("Project Atlas",), ("Project Phoenix", "04 Meeting Notes")]


# endregion


# region ReviewSession.folder_problem and add_folder


@pytest.mark.parametrize(
    ("parent", "name", "expected"),
    [
        ((), "", "needs a name"),
        ((), "   ", "needs a name"),
        ((), "a/b", "not a valid folder name"),
        ((), "a\\b", "not a valid folder name"),
        ((), "what?", "not a valid folder name"),
        ((), "..", "not a valid folder name"),
        ((), "ends.", "not a valid folder name"),
        ((), "project phoenix", "already a folder called"),  # the same name, ignoring case
        ((), "_sorting", "inbox or the state folder"),
        ((), "_SORTING", "inbox or the state folder"),  # the case of the name does not matter
        ((), ".microfiche", "inbox or the state folder"),
        ((), "CON", "reserved name on Windows"),
        ((), "nul", "reserved name on Windows"),
        ((), "aux.txt", "reserved name on Windows"),
        ((), "COM1", "reserved name on Windows"),
        ((), "x" * 256, "longer than 255"),
        (("Project Phoenix",), "02 architecture", "already a folder called"),
        (("Elsewhere",), "New", "no group called"),
    ],
)
def test_folder_problem_names_the_reason(tmp_path: Path, parent: tuple[str, ...], name: str, expected: str) -> None:
    session = _session(_library(tmp_path))

    problem = session.folder_problem(parent, name)

    assert problem is not None
    assert expected in problem


def test_folder_problem_free_name_has_none(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))

    assert session.folder_problem((), "Project Atlas") is None
    assert session.folder_problem(("Project Phoenix",), "04 Meeting Notes") is None


def test_folder_problem_name_matching_a_configured_exclusion_refused(tmp_path: Path) -> None:
    library = Library(_library(tmp_path))
    library.config.exclusions.exclude = ["[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*"]
    session = ReviewSession.start(library)

    problem = session.folder_problem(("Project Phoenix",), "20260115_review")

    assert problem is not None
    assert "[exclusions]" in problem


def test_folder_problem_something_already_on_disk_by_that_name_refused(
    tmp_path: Path, make_junction: LinkMaker
) -> None:
    root = _library(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    make_junction(root / "Linked", elsewhere)  # the taxonomy skips a link, but filing into it would land outside
    (root / "notes.md").write_text("a loose file", encoding="utf-8")
    (root / "Project Phoenix" / "pack").mkdir()  # a folder filed whole is not a category either
    Ledger(root / MICROFICHE_DIRNAME).append([_filed_whole("Project Phoenix/pack")])
    session = _session(root)

    for parent, name in (((), "Linked"), ((), "notes.md"), (("Project Phoenix",), "pack")):
        problem = session.folder_problem(parent, name)
        assert problem is not None, name
        assert "not a group or category" in problem


def test_folder_problem_a_folder_planned_twice_refused(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))
    session.add_folder((), "Project Atlas")

    assert session.folder_problem((), "project atlas") is not None


def test_add_folder_with_a_problem_raises(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))

    with pytest.raises(ReviewError):
        session.add_folder((), "a/b")


def test_add_folder_nothing_is_created_until_a_unit_is_filed(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)

    session.add_folder((), "Project Atlas")

    assert not (root / "Project Atlas").exists()


# endregion


# region ReviewSession.decide and problem


def test_decide_takes_a_choice(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))
    item = _item(session, _SOLAR)

    assert session.decide(item, _RESEARCH) is None

    assert session.decisions == [(item, _RESEARCH)]


def test_decide_same_item_twice_raises(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))
    item = _item(session, _SOLAR)
    session.decide(item, _RESEARCH)

    with pytest.raises(AlreadyDecidedError, match="has already been decided"):
        session.decide(item, _ARCHITECTURE)


@pytest.mark.parametrize(
    "folders",
    [
        ("Project Phoenix",),  # a category is missing
        ("Project Phoenix", "02 Architecture", "extra"),
        ("Elsewhere", "02 Architecture"),
        ("Project Phoenix", "99 Nope"),
        (),
    ],
)
def test_decide_not_a_place_refused(tmp_path: Path, folders: tuple[str, ...]) -> None:
    session = _session(_library(tmp_path))

    problem = session.decide(_item(session, _SOLAR), folders)

    assert problem is not None
    assert "not a place a unit can be filed" in problem
    assert session.decisions == []


def test_decide_name_already_taken_refused(tmp_path: Path) -> None:
    root = _library(tmp_path)
    (root / "Project Phoenix" / "03 Research" / _SOLAR).write_text("a different document", encoding="utf-8")
    session = _session(root)

    problem = session.decide(_item(session, _SOLAR), _RESEARCH)

    assert problem is not None
    assert f"'{_SOLAR}' already exists in Project Phoenix/03 Research" in problem
    assert session.decisions == []


def test_problem_copy_already_in_library_names_where(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)
    shutil.copyfile(root / "_sorting" / _SOLAR, root / "Project Phoenix" / "01 Requirements" / "copy.md")

    problem = session.problem(_item(session, _SOLAR), _RESEARCH)

    assert problem is not None
    assert "identical to" in problem
    assert "01 Requirements/copy.md" in problem


def test_decide_second_unit_cannot_take_a_reserved_name(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _same_name_twice(root)
    session = _session(root, keep_folders=False)
    first, second = session.items
    assert session.decide(first, _RESEARCH) is None

    problem = session.decide(second, _RESEARCH)

    assert problem is not None
    assert "another unit in this run is already going to Project Phoenix/03 Research/" in problem


def test_decide_two_identical_inbox_files_second_is_a_copy_of_the_first(tmp_path: Path) -> None:
    root = _library(tmp_path)
    shutil.copyfile(root / "_sorting" / _SOLAR, root / "_sorting" / "SolarCopy.md")
    session = _session(root)
    # Neither is being filed in the preview (both are unresolved), so both are queued.
    assert sorted(item.name for item in session.items) == sorted(["SolarCopy.md", _SOLAR])
    assert session.decide(_item(session, _SOLAR), _RESEARCH) is None

    problem = session.decide(_item(session, "SolarCopy.md"), _RESEARCH)

    assert problem is not None
    assert f"identical to '{_SOLAR}', which is being filed this run" in problem


def test_problem_does_not_reserve_the_destination(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))
    item = _item(session, _SOLAR)

    assert session.problem(item, _RESEARCH) is None
    assert session.problem(item, _RESEARCH) is None
    assert session.decisions == []


def test_problem_sees_a_destination_an_earlier_choice_reserved(tmp_path: Path) -> None:
    root = _library(tmp_path)
    _same_name_twice(root)
    session = _session(root, keep_folders=False)
    first, second = session.items
    session.decide(first, _RESEARCH)

    assert session.problem(second, _RESEARCH) is not None


def test_decide_into_a_planned_folder_is_allowed(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))
    session.add_folder((), "Project Atlas")
    session.add_folder(("Project Atlas",), "01 Plans")

    assert session.decide(_item(session, _SOLAR), ("Project Atlas", "01 Plans")) is None


# endregion


# region ReviewSession.commit


def test_commit_files_the_chosen_units_as_one_job(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root, threshold=0.95)
    session.decide(_item(session, _SOLAR), _RESEARCH)
    session.decide(_item(session, _PHOENIX), _ARCHITECTURE)

    outcome = session.commit()

    assert outcome.job is not None
    assert outcome.failed == []
    assert outcome.created == []
    assert (root / "Project Phoenix" / "03 Research" / _SOLAR).is_file()
    assert (root / "Project Phoenix" / "02 Architecture" / _PHOENIX).is_file()
    assert not (root / "_sorting" / _SOLAR).exists()
    assert sorted(move.new_path.name for move in outcome.job.moves if move.new_path) == sorted([_PHOENIX, _SOLAR])


def test_commit_records_the_choice_as_the_users(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)
    session.decide(_item(session, _SOLAR), _RESEARCH)

    session.commit()

    (record,) = Ledger(root / MICROFICHE_DIRNAME).current()
    assert record.classified_by == "user"
    assert (record.group, record.category) == _RESEARCH
    assert record.group_reason == "Chosen in review"
    assert record.confidence == 1.0


def test_commit_can_be_rolled_back(tmp_path: Path) -> None:
    root = _library(tmp_path)
    before = _snapshot(root)
    session = _session(root, threshold=0.95)
    session.decide(_item(session, _SOLAR), _RESEARCH)
    session.decide(_item(session, _PHOENIX), _ARCHITECTURE)
    outcome = session.commit()
    assert outcome.job is not None

    rollback_job(Library(root), outcome.job.job_id)

    assert _snapshot(root) == before


def test_commit_nothing_decided_files_nothing(tmp_path: Path) -> None:
    root = _library(tmp_path)
    before = _snapshot(root)

    outcome = _session(root).commit()

    assert outcome.job is None
    assert _snapshot(root) == before
    assert not (root / MICROFICHE_DIRNAME / "rollback").exists()


def test_commit_creates_a_planned_folder_by_filing_into_it(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)
    session.add_folder((), "Project Atlas")
    session.add_folder(("Project Atlas",), "01 Plans")
    session.decide(_item(session, _SOLAR), ("Project Atlas", "01 Plans"))

    outcome = session.commit()

    assert (root / "Project Atlas" / "01 Plans" / _SOLAR).is_file()
    assert outcome.created == [root / "Project Atlas", root / "Project Atlas" / "01 Plans"]


def test_commit_a_planned_folder_no_unit_was_filed_into_is_not_created(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)
    session.add_folder((), "Project Atlas")
    session.decide(_item(session, _SOLAR), _RESEARCH)

    outcome = session.commit()

    assert not (root / "Project Atlas").exists()
    assert outcome.created == []


def test_commit_a_unit_that_left_the_inbox_is_reported_and_the_rest_filed(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root, threshold=0.95)
    session.decide(_item(session, _SOLAR), _RESEARCH)
    session.decide(_item(session, _PHOENIX), _ARCHITECTURE)
    (root / "_sorting" / _SOLAR).unlink()  # taken away while the person was deciding

    outcome = session.commit()

    assert [failure.unit.source_path.name for failure in outcome.failed] == [_SOLAR]
    assert outcome.failed[0].reason == "it is no longer in the inbox"
    assert (root / "Project Phoenix" / "02 Architecture" / _PHOENIX).is_file()
    assert outcome.job is not None


def test_commit_a_name_taken_since_the_choice_is_reported_not_overwritten(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)
    session.decide(_item(session, _SOLAR), _RESEARCH)
    taken = root / "Project Phoenix" / "03 Research" / _SOLAR
    taken.write_text("someone else's document", encoding="utf-8")

    outcome = session.commit()

    assert outcome.job is None
    assert "already exists" in outcome.failed[0].reason
    assert taken.read_text(encoding="utf-8") == "someone else's document"
    assert (root / "_sorting" / _SOLAR).is_file()


def test_commit_a_copy_that_appeared_since_the_choice_is_reported(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)
    session.decide(_item(session, _SOLAR), _RESEARCH)
    shutil.copyfile(root / "_sorting" / _SOLAR, root / "Project Phoenix" / "01 Requirements" / "copy.md")

    outcome = session.commit()

    assert outcome.job is None
    assert "identical to" in outcome.failed[0].reason


def test_commit_moves_a_folder_unit_whole(tmp_path: Path) -> None:
    root = _library(tmp_path, with_pack=True)
    session = _session(root, threshold=0.95)
    session.decide(_item(session, _PACK), _RESEARCH)

    outcome = session.commit()

    assert outcome.job is not None
    assert sorted(p.name for p in (root / "Project Phoenix" / "03 Research" / _PACK).iterdir()) == [
        "architecture-decision-log.md",
        "component-diagram-notes.md",
        "research-summary.md",
    ]
    assert Ledger(root / MICROFICHE_DIRNAME).folder_units() == {f"Project Phoenix/03 Research/{_PACK}"}


# endregion


# region ReviewSession.commit: safety


def test_commit_a_file_replaced_since_the_choice_is_not_filed(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)
    session.decide(_item(session, _SOLAR), _RESEARCH)
    (root / "_sorting" / _SOLAR).write_text("a different document under the same name", encoding="utf-8")

    outcome = session.commit()

    assert outcome.job is None
    assert outcome.failed[0].reason == "it has changed since you chose where it goes"
    assert (root / "_sorting" / _SOLAR).read_text(encoding="utf-8") == "a different document under the same name"
    assert not (root / "Project Phoenix" / "03 Research" / _SOLAR).exists()


def test_commit_a_folder_unit_changed_since_the_choice_is_not_filed(tmp_path: Path) -> None:
    root = _library(tmp_path, with_pack=True)
    session = _session(root, threshold=0.95)
    session.decide(_item(session, _PACK), _RESEARCH)
    (root / "_sorting" / _PACK / "added-later.md").write_text("one more document", encoding="utf-8")

    outcome = session.commit()

    assert outcome.job is None
    assert "has changed" in outcome.failed[0].reason


def test_commit_twice_files_nothing_the_second_time(tmp_path: Path) -> None:
    root = _library(tmp_path)
    session = _session(root)
    session.decide(_item(session, _SOLAR), _RESEARCH)
    assert session.commit().job is not None

    again = session.commit()

    assert again.job is None
    assert again.failed == []
    assert session.decisions == []


def test_commit_a_failed_move_takes_back_the_folders_it_made(tmp_path: Path, hold_open: Callable[[Path], None]) -> None:
    root = _library(tmp_path)
    before = _snapshot(root)
    session = _session(root)
    session.add_folder((), "Project Atlas")
    session.add_folder(("Project Atlas",), "01 Plans")
    session.decide(_item(session, _SOLAR), ("Project Atlas", "01 Plans"))
    hold_open(root / "_sorting" / _SOLAR)  # open in another program, so the rename fails

    outcome = session.commit()

    assert outcome.job is None
    assert "open in another program" in outcome.failed[0].reason
    assert outcome.created == []
    assert not (root / "Project Atlas").exists()
    assert _snapshot(root) == before


def test_commit_partly_decided_inbox_folder_stays_until_it_is_empty(tmp_path: Path) -> None:
    root = _library(tmp_path)
    (root / "_sorting" / "batch").mkdir()
    (root / "_sorting" / "batch" / "a.md").write_text("Nothing recognisable here, first.", encoding="utf-8")
    (root / "_sorting" / "batch" / "b.md").write_text("Nothing recognisable here, second.", encoding="utf-8")
    session = _session(root, keep_folders=False)
    first = _item(session, "a.md")
    second = _item(session, "b.md")

    session.decide(first, _RESEARCH)
    session.commit()
    assert (root / "_sorting" / "batch" / "b.md").is_file()  # still there, so the folder stays

    again = _session(root, keep_folders=False)
    again.decide(_item(again, second.name), _RESEARCH)
    outcome = again.commit()

    assert outcome.job is not None
    assert not (root / "_sorting" / "batch").exists()  # emptied by the last unit, and removed as `sort` would
    assert [event.action for event in outcome.job.moves].count("remove_folder") == 1


# endregion


# region ReviewSession.waiting


def test_waiting_counts_the_units_sort_would_file(tmp_path: Path) -> None:
    session = _session(_library(tmp_path))

    assert session.waiting == 1  # the Phoenix note
    assert [item.name for item in session.items] == [_SOLAR]


# endregion


# region A flat library


def _flat(tmp_path: Path) -> Path:
    root = tmp_path / "flat"
    shutil.copytree(_MOCK_FLAT_LIBRARY, root)
    shutil.rmtree(root / "_sorting" / "mixed-pack")
    return root


def test_flat_library_a_choice_is_one_group(tmp_path: Path) -> None:
    root = _flat(tmp_path)
    session = _session(root)
    item = _item(session, "HolidayIdeas.md")

    assert session.depth == 1
    assert session.categories("Household") == []
    assert session.decide(item, ("Household",)) is None
    assert session.commit().job is not None
    assert (root / "Household" / "HolidayIdeas.md").is_file()


def test_flat_library_a_group_and_category_choice_is_not_a_place(tmp_path: Path) -> None:
    session = _session(_flat(tmp_path))

    problem = session.decide(_item(session, "HolidayIdeas.md"), ("Household", "Bills"))

    assert problem is not None
    assert "not a place" in problem


def test_flat_library_can_plan_a_group_but_not_a_category(tmp_path: Path) -> None:
    session = _session(_flat(tmp_path))

    assert session.folder_problem((), "Garden") is None
    assert "no level below" in (session.folder_problem(("Household",), "Bills") or "")


# endregion


# endregion
