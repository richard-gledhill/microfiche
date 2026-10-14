"""Tests for the sample library builder: each document must end up where its label says, and no route may be missing."""

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest
from microfiche.cli.app import app
from microfiche.core.ai.llm_classifier import LLMClassifier
from microfiche.core.filer import rollback_job
from microfiche.core.library.library import Library
from microfiche.core.organizer import SortReport, run_sort
from microfiche.core.reclassify import run_reclassify
from typer.testing import CliRunner

# region Test helpers


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "make_sample_library.py"

_spec = importlib.util.spec_from_file_location("make_sample_library", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
sample = importlib.util.module_from_spec(_spec)
sys.modules["make_sample_library"] = sample  # dataclasses look their module up here
_spec.loader.exec_module(sample)

runner = CliRunner()


def _build(tmp_path: Path, shape: str = "depth2") -> "sample.SampleLibrary":
    return sample.build_sample_library(tmp_path / "library", shape)


def _snapshot(library: Path) -> dict[str, str]:
    """Library-relative path -> content hash for every file outside microfiche's own state folder."""

    return {
        path.relative_to(library).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(library.rglob("*"))
        if path.is_file() and ".microfiche" not in path.relative_to(library).parts
    }


def _filed_where(report: SortReport) -> dict[str, str]:
    """Inbox entry name -> ``group/category`` (or ``group``) for everything the run filed."""

    return {
        unit.source_path.name: "/".join(folder for folder in classification.folders)
        for unit, classification in report.filed
    }


class _SolarProvider:
    """An AI provider that knows only the rooftop-panels note: Project Atlas, then 03 Research. NONE for any other."""

    def __init__(self) -> None:
        self._answers = iter(["Project Atlas", "03 Research"])

    def complete(self, prompt: str) -> str:
        return next(self._answers, "NONE") if "Rooftop panels" in prompt else "NONE"


# endregion


# region build_sample_library


def test_build_sample_library_existing_destination_refused(tmp_path: Path) -> None:
    (tmp_path / "library").mkdir()

    with pytest.raises(FileExistsError):
        _build(tmp_path)


def test_build_sample_library_unknown_shape_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="deep"):
        _build(tmp_path, "deep")


def test_build_sample_library_every_route_is_covered(tmp_path: Path) -> None:
    covered = set()
    for shape in ("depth2", "flat"):
        covered |= {
            route for item in sample.build_sample_library(tmp_path / shape, shape).items for route in item.covers
        }

    assert sample.PATHS - covered == set()  # a route in PATHS that no document takes would go untested
    assert covered - sample.PATHS == set()  # a typo in a label


def test_build_sample_library_inbox_items_all_written(tmp_path: Path) -> None:
    built = _build(tmp_path)

    for item in built.items:
        for file in item.files:
            assert (built.root / "_sorting" / file.path).is_file(), file.path


# endregion


# region The depth-2 library, sorted


def test_sample_depth2_sort_every_item_has_its_expected_outcome(tmp_path: Path) -> None:
    built = _build(tmp_path)

    report = run_sort(Library(built.root))

    filed = _filed_where(report)
    held = {unit.source_path.name for unit, _ in report.needs_review}
    copies = {duplicate.unit.source_path.name: duplicate.reason for duplicate in report.duplicates}
    for item in built.items:
        if item.outcome == "filed":
            assert filed.get(item.name) == item.destination, item.name
        elif item.outcome == "review":
            assert item.name in held, item.name
        elif item.outcome == "duplicate":
            assert item.reason is not None
            assert item.reason in copies.get(item.name, ""), item.name
        else:
            assert item.name not in set(filed) | held | set(copies), item.name  # never treated as a document
    expected_filed = {item.name for item in built.items if item.outcome == "filed"}
    assert set(filed) == expected_filed  # nothing was filed that the sample does not say should be


def test_sample_depth2_sort_review_reasons_say_why(tmp_path: Path) -> None:
    built = _build(tmp_path)
    report = run_sort(Library(built.root))

    reasons = {unit.source_path.name: classification for unit, classification in report.needs_review}
    for item in built.items:
        if item.outcome == "review" and item.reason:
            text = " ".join(
                part
                for part in (
                    reasons[item.name].group.reason,
                    reasons[item.name].category.reason if reasons[item.name].category else "",
                )
            )
            assert item.reason in text, (item.name, text)


def test_sample_depth2_sort_then_rollback_restores_the_library(tmp_path: Path) -> None:
    built = _build(tmp_path)
    before = _snapshot(built.root)
    library = Library(built.root)

    report = run_sort(library)
    assert report.job is not None
    assert _snapshot(built.root) != before
    rollback_job(library, report.job.job_id)

    assert _snapshot(built.root) == before


def test_sample_depth2_second_sort_files_nothing_new(tmp_path: Path) -> None:
    built = _build(tmp_path)
    library = Library(built.root)
    run_sort(library)

    second = run_sort(library)

    assert second.filed == []
    assert second.job is None


def test_sample_depth2_sort_nothing_is_lost(tmp_path: Path) -> None:
    built = _build(tmp_path)
    before = _snapshot(built.root)

    run_sort(Library(built.root))

    after = _snapshot(built.root)
    # Every document is somewhere afterwards: filed, or left where it was. Names change only by location.
    assert sorted(path.rsplit("/", 1)[-1] for path in after) == sorted(path.rsplit("/", 1)[-1] for path in before)
    assert sorted(after.values()) == sorted(before.values())


def test_sample_depth2_sort_keep_folders_off_files_the_pack_document_by_document(tmp_path: Path) -> None:
    built = _build(tmp_path)

    report = run_sort(Library(built.root), keep_folders=False)

    filed = _filed_where(report)
    assert filed["decision-log.md"] == "Project Phoenix/02 Architecture"
    assert filed["components.md"] == "Project Phoenix/02 Architecture"
    assert filed["reading.md"] == "Project Phoenix/03 Research"
    assert filed["kickoff.md"] == "Project Phoenix/04 Meeting Notes"  # the tie only held the folder as a whole
    assert filed["vendor.md"] == "Project Phoenix/03 Research"
    assert {folder.name for folder in report.folders_removed} == {"phoenix-weekly-pack", "mixed-bag"}
    assert not (built.root / "_sorting" / "phoenix-weekly-pack").exists()  # emptied, so removed


def test_sample_depth2_dry_run_changes_nothing(tmp_path: Path) -> None:
    built = _build(tmp_path)
    before = _snapshot(built.root)

    report = run_sort(Library(built.root), dry_run=True)

    assert report.job is None
    assert _snapshot(built.root) == before
    assert not (built.root / ".microfiche" / "rollback").exists()


# endregion


# region The depth-2 library, reclassified


def test_sample_depth2_reclassify_actions_match_the_label(tmp_path: Path) -> None:
    built = _build(tmp_path)

    proposals = run_reclassify(Library(built.root))

    actions = {proposal.unit.source_path.relative_to(built.root).as_posix(): proposal.action for proposal in proposals}
    for path, expected in built.filed:
        if expected == "skip":
            assert path not in actions, path  # excluded folders are never looked at
        else:
            assert actions[path] == expected, path
    assert {"keep", "move", "review", "conflict"} <= set(actions.values())  # all four actions are shown


# endregion


# region The AI fallback on the sample


def test_sample_depth2_sort_ai_answer_files_the_unknown_document_at_a_lower_threshold(tmp_path: Path) -> None:
    built = _build(tmp_path)
    config = built.root / ".microfiche" / "microfiche-config.toml"
    text = config.read_text(encoding="utf-8").replace("confidence_threshold = 0.75", "confidence_threshold = 0.7")
    config.write_text(text, encoding="utf-8")
    library = Library(built.root)

    report = run_sort(library, ai_classifier=LLMClassifier(_SolarProvider(), library.config.ai))

    assert _filed_where(report)["SolarNotes.md"] == "Project Atlas/03 Research"
    ((_, solar),) = [(unit, c) for unit, c in report.filed if unit.source_path.name == "SolarNotes.md"]
    assert solar.classified_by == "ai_fallback"


def test_sample_depth2_sort_ai_answer_held_at_the_default_threshold(tmp_path: Path) -> None:
    built = _build(tmp_path)
    library = Library(built.root)

    report = run_sort(library, ai_classifier=LLMClassifier(_SolarProvider(), library.config.ai))

    assert "SolarNotes.md" not in _filed_where(report)  # an AI-only answer scores 0.70, below the default 0.75


# endregion


# region The flat library


def test_sample_flat_sort_every_item_has_its_expected_outcome(tmp_path: Path) -> None:
    built = _build(tmp_path, "flat")

    report = run_sort(Library(built.root))

    filed = _filed_where(report)
    held = {unit.source_path.name: classification.group.reason for unit, classification in report.needs_review}
    for item in built.items:
        if item.outcome == "filed":
            assert filed.get(item.name) == item.destination, item.name
        else:
            assert item.name in held, item.name
            assert item.reason is not None
            assert item.reason in held[item.name], item.name  # held for the reason the sample says, not just held


def test_sample_flat_sort_short_group_name_inside_a_word_is_a_known_limit(tmp_path: Path) -> None:
    built = _build(tmp_path, "flat")

    report = run_sort(Library(built.root))

    # Documented in docs/how-to-use.md ("Current limitations") and docs/development/calibration.md.
    assert _filed_where(report)["scarf-pattern.md"] == "Car"


# endregion


# region The command


def test_main_builds_and_lists_the_expected_outcomes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = sample.main([str(tmp_path / "library")])

    out = capsys.readouterr().out
    assert code == 0
    assert "PhoenixArchitectureNotes.md -> Project Phoenix/02 Architecture" in out
    assert "duplicate functional-requirements-copy.md" in out


def test_main_existing_destination_says_so_and_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = sample.main([str(tmp_path)])

    assert code == 1
    assert "already exists" in capsys.readouterr().out


def test_cli_sample_sort_then_rollback_last_restores_the_library(tmp_path: Path) -> None:
    built = _build(tmp_path)
    before = _snapshot(built.root)

    sorted_ = runner.invoke(app, ["sort", "--library", str(built.root)])
    rolled_back = runner.invoke(app, ["rollback", "--library", str(built.root), "--last"])

    assert sorted_.exit_code == 0
    assert rolled_back.exit_code == 0
    assert _snapshot(built.root) == before


# endregion
