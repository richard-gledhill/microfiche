"""End-to-end tests for a flat library (``depth = 1``): groups only, documents filed straight into a group folder."""

import shutil
from collections.abc import Callable
from pathlib import Path

from core.ai.llm_classifier import LLMClassifier
from core.config import MICROFICHE_DIRNAME
from core.filer import rollback_job
from core.ledger import Ledger
from core.library.library import Library
from core.organizer import SortReport, run_sort
from core.reclassify import apply_reclassification, run_reclassify
from core.utils.hashing import file_hash

# region Test helpers


_MOCK_FLAT_LIBRARY = Path(__file__).resolve().parents[1] / "mock_flat_library"
_PACK = "mixed-pack"  # an inbox folder: two Project Phoenix documents and one Project Atlas document

_PHOENIX = "PhoenixDesignNotes.md"
_ATLAS = "AtlasBudget.md"
_BY_HINT = "electricity-march.md"  # names no group; the Household hint "invoice" matches
_BY_RULE = "statement-q1.md"  # names no group; the Household filename rule matches
_UNRELATED = "HolidayIdeas.md"


def _library(tmp_path: Path, *, with_pack: bool = False) -> Path:
    """A copy of the flat mock library; the inbox folder is left out unless asked for."""

    library = tmp_path / "library"
    shutil.copytree(_MOCK_FLAT_LIBRARY, library)
    if not with_pack:
        shutil.rmtree(library / "_sorting" / _PACK)
    return library


def _snapshot(library: Path) -> dict[str, str]:
    """Library-relative path -> hash for every file, ignoring microfiche's own state."""

    state_dir = library / MICROFICHE_DIRNAME
    return {
        path.relative_to(library).as_posix(): file_hash(path)
        for path in sorted(library.rglob("*"))
        if path.is_file() and not path.is_relative_to(state_dir)
    }


def _filed(report: SortReport) -> dict[str, str]:
    return {unit.source_path.name: classification.group.name or "" for unit, classification in report.filed}


# endregion


# region Taxonomy


def test_taxonomy_flat_library_lists_groups_with_no_categories(tmp_path: Path) -> None:
    library = Library(_library(tmp_path))

    taxonomy = library.taxonomy()

    assert taxonomy.depth == 1
    assert taxonomy.is_flat
    assert taxonomy.groups == {"Household": [], "Project Atlas": [], "Project Phoenix": []}


# endregion


# region Sort


def test_run_sort_flat_library_files_into_group_folder(tmp_path: Path) -> None:
    root = _library(tmp_path)

    report = run_sort(Library(root))

    assert _filed(report) == {
        _PHOENIX: "Project Phoenix",
        _ATLAS: "Project Atlas",
        _BY_HINT: "Household",
        _BY_RULE: "Household",
    }
    assert (root / "Project Phoenix" / _PHOENIX).is_file()
    assert (root / "Project Atlas" / _ATLAS).is_file()
    assert (root / "Household" / _BY_HINT).is_file()
    assert (root / "Household" / _BY_RULE).is_file()
    assert [unit.source_path.name for unit, _ in report.needs_review] == [_UNRELATED]
    assert (root / "_sorting" / _UNRELATED).is_file()


def test_run_sort_flat_library_classification_has_no_category(tmp_path: Path) -> None:
    report = run_sort(Library(_library(tmp_path)), dry_run=True)

    assert report.filed
    for _, classification in report.filed:
        assert classification.category is None
        assert classification.overall_confidence == classification.group.confidence
        assert classification.folders == (classification.group.name,)


def test_run_sort_flat_library_says_how_each_group_was_found(tmp_path: Path) -> None:
    report = run_sort(Library(_library(tmp_path)), dry_run=True)

    reasons = {unit.source_path.name: classification.group.reason for unit, classification in report.filed}
    assert "Exact match on group name" in reasons[_PHOENIX]
    assert "Keyword hint 'invoice'" in reasons[_BY_HINT]
    assert "rule pattern 'statement-*.md'" in reasons[_BY_RULE]


def test_run_sort_flat_library_unresolved_group_goes_to_review(tmp_path: Path) -> None:
    report = run_sort(Library(_library(tmp_path)), dry_run=True)

    ((_, classification),) = [item for item in report.needs_review if item[0].source_path.name == _UNRELATED]
    assert classification.group.name is None
    assert classification.category is None
    assert not classification.confident


def test_run_sort_flat_library_folder_unit_votes_on_group_alone(tmp_path: Path) -> None:
    root = _library(tmp_path, with_pack=True)

    report = run_sort(Library(root))

    assert _filed(report)[_PACK] == "Project Phoenix"  # two documents voted Phoenix, one Atlas
    assert (root / "Project Phoenix" / _PACK / "atlas-plan.md").is_file()


def test_run_sort_flat_library_folder_unit_tie_goes_to_review(tmp_path: Path) -> None:
    root = _library(tmp_path, with_pack=True)
    (root / "_sorting" / _PACK / "phoenix-risks.md").unlink()

    report = run_sort(Library(root))

    ((_, classification),) = [item for item in report.needs_review if item[0].source_path.name == _PACK]
    assert "disagree" in classification.group.reason
    assert "Project Phoenix (1 documents)" in classification.group.reason  # no "/(no category)" at depth 1
    assert "(no category)" not in classification.group.reason
    assert (root / "_sorting" / _PACK).is_dir()


def test_run_sort_flat_library_ledger_records_group_without_category(tmp_path: Path) -> None:
    root = _library(tmp_path)

    run_sort(Library(root))

    records = {record.path: record for record in Ledger(root / MICROFICHE_DIRNAME).current()}
    record = records[f"Project Phoenix/{_PHOENIX}"]
    assert record.group == "Project Phoenix"
    assert record.category is None
    assert record.category_reason is None


def test_run_sort_flat_library_duplicate_reason_names_the_group(tmp_path: Path) -> None:
    root = _library(tmp_path)
    shutil.copyfile(root / "_sorting" / _PHOENIX, root / "Household" / "copy-of-phoenix.md")

    report = run_sort(Library(root))

    (duplicate,) = report.duplicates
    assert duplicate.unit.source_path.name == _PHOENIX
    assert "this would be filed in Project Phoenix" in duplicate.reason


def test_run_sort_flat_library_name_collision_goes_to_review(tmp_path: Path) -> None:
    root = _library(tmp_path)
    (root / "Project Phoenix" / _PHOENIX).write_text("A different document with that name.", encoding="utf-8")

    report = run_sort(Library(root))

    assert _PHOENIX not in _filed(report)
    ((_, classification),) = [item for item in report.needs_review if item[0].source_path.name == _PHOENIX]
    assert "already exists in Project Phoenix" in classification.reason


def test_run_sort_flat_library_syncs_group_folders_only(tmp_path: Path) -> None:
    root = _library(tmp_path)
    (root / ".microfiche" / "microfiche-library.json").unlink()

    report = run_sort(Library(root))

    assert report.library_sync is not None
    assert report.library_sync.added == ["Household", "Project Atlas", "Project Phoenix"]


# endregion


def test_run_sort_flat_library_hints_of_two_groups_go_to_review(tmp_path: Path) -> None:
    root = _library(tmp_path)
    library_file = root / ".microfiche" / "microfiche-library.json"
    library_file.write_text(
        '{"groups": [{"name": "Household", "hints": ["invoice"]}, {"name": "Project Atlas", "hints": ["budget"]}]}',
        encoding="utf-8",
    )
    (root / "_sorting" / "both.md").write_text("The invoice is over budget.", encoding="utf-8")

    report = run_sort(Library(root), dry_run=True)

    ((_, classification),) = [item for item in report.needs_review if item[0].source_path.name == "both.md"]
    assert classification.group.name is None
    assert "several groups" in classification.reason


def test_run_sort_flat_library_open_file_left_for_review(tmp_path: Path, hold_open: Callable[[Path], None]) -> None:
    root = _library(tmp_path)
    hold_open(root / "_sorting" / _PHOENIX)

    report = run_sort(Library(root))

    held = {unit.source_path.name: classification for unit, classification in report.needs_review}
    assert held[_PHOENIX].reason.endswith(
        "but it could not be moved: it is open in another program; close it and sort again"
    )
    assert held[_PHOENIX].folders == ("Project Phoenix",)  # where it would have gone is kept
    assert _PHOENIX not in _filed(report)
    assert (root / "_sorting" / _PHOENIX).exists()


class _GroupProvider:
    """An AI provider that always answers ``Household``, and keeps the prompts it was asked."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "Household"


def test_run_sort_flat_library_ai_fallback_is_asked_for_the_group_only(tmp_path: Path) -> None:
    library = Library(_library(tmp_path))
    provider = _GroupProvider()

    report = run_sort(library, ai_classifier=LLMClassifier(provider, library.config.ai), dry_run=True)

    ((_, classification),) = [item for item in report.needs_review if item[0].source_path.name == _UNRELATED]
    assert classification.group.name == "Household"  # the AI's answer, held for review at its 0.70
    assert classification.classified_by == "ai_fallback"
    assert classification.confident is False
    assert provider.prompts
    assert all("categories" not in prompt for prompt in provider.prompts)


# endregion


# region Rollback


def test_rollback_flat_library_restores_the_library(tmp_path: Path) -> None:
    root = _library(tmp_path, with_pack=True)
    before = _snapshot(root)
    report = run_sort(Library(root))
    assert report.job is not None
    assert _snapshot(root) != before

    rollback_job(Library(root), report.job.job_id)

    assert _snapshot(root) == before


def test_rollback_after_depth_changes_still_restores_the_library(tmp_path: Path) -> None:
    """A job is replayed from its own record, so changing ``depth`` afterwards does not strand it."""

    root = tmp_path / "library"
    shutil.copytree(Path(__file__).resolve().parents[1] / "mock_library", root)
    shutil.rmtree(root / "_sorting" / "phoenix-weekly-pack")
    before = _snapshot(root)
    report = run_sort(Library(root))
    assert report.job is not None
    config = root / ".microfiche" / "microfiche-config.toml"
    config.write_text(config.read_text(encoding="utf-8").replace("depth = 2", "depth = 1"), encoding="utf-8")

    rollback_job(Library(root), report.job.job_id)

    assert _snapshot(root) == before


# endregion


# region Reclassify


def test_reclassify_flat_library_keeps_documents_in_the_right_group(tmp_path: Path) -> None:
    root = _library(tmp_path)

    proposals = {p.unit.source_path.name: p for p in run_reclassify(Library(root))}

    assert proposals["kickoff-notes.md"].action == "keep"  # names Project Phoenix, and is in it
    assert proposals["scope.md"].action == "keep"
    assert proposals["boiler-service.md"].action == "keep"  # "invoice" hint; in Household


def test_reclassify_flat_library_moves_a_document_in_the_wrong_group(tmp_path: Path) -> None:
    root = _library(tmp_path)
    shutil.move(root / "Project Atlas" / "scope.md", root / "Household" / "scope.md")

    proposals = {p.unit.source_path.name: p for p in run_reclassify(Library(root))}

    proposal = proposals["scope.md"]
    assert proposal.action == "move"
    assert proposal.destination == root / "Project Atlas" / "scope.md"
    assert proposal.proposed_group == "Project Atlas"
    assert proposal.proposed_category is None


def test_reclassify_flat_library_apply_moves_and_rolls_back(tmp_path: Path) -> None:
    root = _library(tmp_path)
    shutil.move(root / "Project Atlas" / "scope.md", root / "Household" / "scope.md")
    before = _snapshot(root)
    library = Library(root)

    result = apply_reclassification(library, run_reclassify(library))

    assert (root / "Project Atlas" / "scope.md").is_file()
    assert result.job is not None
    rollback_job(library, result.job.job_id)
    assert _snapshot(root) == before


def test_reclassify_flat_library_unresolved_goes_to_review(tmp_path: Path) -> None:
    root = _library(tmp_path)
    (root / "Household" / "ideas.md").write_text("A list of places to visit someday.", encoding="utf-8")

    proposals = {p.unit.source_path.name: p for p in run_reclassify(Library(root))}

    assert proposals["ideas.md"].action == "review"


# endregion
