"""Tests for having the AI check rules answers that score below ``[ai] verify_below``."""

import json
import logging
from pathlib import Path

import pytest
from microfiche.core.ai.llm_classifier import LLMClassifier
from microfiche.core.classifier import Classifier
from microfiche.core.config import load_config
from microfiche.core.library.library import Library
from microfiche.core.models.category import Taxonomy
from microfiche.core.models.classification import CategoryMatch, GroupMatch
from microfiche.core.models.document import Document
from microfiche.core.models.unit import SortableUnit
from microfiche.core.organizer import run_sort

# region Test helpers


PHOENIX = "Project Phoenix"
ATLAS = "Project Atlas"
REQS = "01 Requirements"
ARCH = "02 Architecture"
TAXONOMY = Taxonomy(groups={PHOENIX: [REQS, ARCH], ATLAS: [REQS, ARCH]})
_HINT = 0.75
_NAME = 0.9


def _document(file_name: str = "doc.md") -> Document:
    return Document(file_path=Path(file_name), file_name=file_name, extension=".md", content="text")


def _group(name: str | None, confidence: float = 1.0) -> GroupMatch:
    return GroupMatch(name=name, confidence=confidence if name else 0.0, reason=f"group {name}")


def _category(name: str | None, confidence: float = _HINT) -> CategoryMatch:
    return CategoryMatch(name=name, confidence=confidence if name else 0.0, reason=f"category {name}")


class _Resolver:
    """Answers the same every time, and counts how often it was asked."""

    def __init__(self, name: str, group: GroupMatch, category: CategoryMatch) -> None:
        self.name = name
        self._group = group
        self._category = category
        self.asked = 0
        self.failure: str | None = None

    def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
        self.asked += 1
        return self._group

    def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
        self.asked += 1
        return self._category


def _classify(rules: _Resolver, ai: _Resolver | None, *, verify_below: float) -> tuple[Classifier, object]:
    classifier = Classifier(rules, ai, verify_below=verify_below)
    return classifier, classifier.classify_document(_document(), TAXONOMY)


# endregion

# region Verification


def test_classify_document_verify_below_zero_never_asks_the_ai() -> None:
    rules = _Resolver("rules_engine", _group(PHOENIX), _category(ARCH))
    ai = _Resolver("ai_fallback", _group(PHOENIX, 0.7), _category(ARCH, 0.7))

    classifier, result = _classify(rules, ai, verify_below=0.0)

    assert ai.asked == 0
    assert result.confident  # type: ignore[attr-defined]
    assert classifier.verification.checked == 0


def test_classify_document_ai_agrees_unit_files_at_the_rules_score() -> None:
    rules = _Resolver("rules_engine", _group(PHOENIX), _category(ARCH, _HINT))
    ai = _Resolver("ai_fallback", _group(PHOENIX, 0.7), _category(ARCH, 0.7))

    classifier, result = _classify(rules, ai, verify_below=0.8)

    assert result.confident  # type: ignore[attr-defined]
    assert result.overall_confidence == _HINT  # type: ignore[attr-defined]
    assert result.category.reason.endswith("confirmed by the AI")  # type: ignore[attr-defined]
    assert result.classified_by == "rules_engine+ai_fallback"  # type: ignore[attr-defined]
    assert ai.asked == 1  # the group (1.0) was not checked, only the hint-level category
    assert (classifier.verification.checked, classifier.verification.confirmed) == (1, 1)


def test_classify_document_ai_picks_another_category_unit_held_with_both_answers() -> None:
    rules = _Resolver("rules_engine", _group(PHOENIX), _category(ARCH))
    ai = _Resolver("ai_fallback", _group(PHOENIX, 0.7), _category(REQS, 0.7))

    classifier, result = _classify(rules, ai, verify_below=0.8)

    assert not result.confident  # type: ignore[attr-defined]
    assert result.ai_overruled  # type: ignore[attr-defined]
    assert result.category.name == ARCH  # type: ignore[attr-defined]  # still where the rules would have put it
    assert f"category {ARCH}" in result.reason  # type: ignore[attr-defined]
    assert f"the AI disagrees about the category: it chose '{REQS}'" in result.reason  # type: ignore[attr-defined]
    assert classifier.verification.overruled == 1


def test_classify_document_ai_finds_no_match_unit_held() -> None:
    rules = _Resolver("rules_engine", _group(PHOENIX), _category(ARCH))
    ai = _Resolver("ai_fallback", _group(PHOENIX, 0.7), _category(None))

    _, result = _classify(rules, ai, verify_below=0.8)

    assert not result.confident  # type: ignore[attr-defined]
    assert "it found no match" in result.reason  # type: ignore[attr-defined]


def test_classify_document_name_level_answer_checked_only_when_verify_below_reaches_it() -> None:
    rules = _Resolver("rules_engine", _group(PHOENIX), _category(ARCH, _NAME))
    ai = _Resolver("ai_fallback", _group(PHOENIX, 0.7), _category(REQS, 0.7))

    _, hints_only = _classify(rules, ai, verify_below=0.8)
    _, with_names = _classify(rules, ai, verify_below=0.95)

    assert hints_only.confident  # type: ignore[attr-defined]
    assert not with_names.confident  # type: ignore[attr-defined]


def test_classify_document_fuzzy_group_checked_and_overruled() -> None:
    rules = _Resolver("rules_engine", _group(PHOENIX, 0.88), _category(ARCH, _NAME))
    ai = _Resolver("ai_fallback", _group(ATLAS, 0.7), _category(ARCH, 0.7))

    _, result = _classify(rules, ai, verify_below=0.95)

    assert not result.confident  # type: ignore[attr-defined]
    assert f"the AI disagrees about the group: it chose '{ATLAS}'" in result.reason  # type: ignore[attr-defined]


def test_classify_document_unavailable_ai_leaves_rules_answer_and_is_not_counted() -> None:
    rules = _Resolver("rules_engine", _group(PHOENIX), _category(ARCH))
    ai = _Resolver("ai_fallback", _group(None), _category(None))
    ai.failure = "Ollama is not running"

    classifier, result = _classify(rules, ai, verify_below=0.8)

    assert result.confident  # type: ignore[attr-defined]
    assert result.classified_by == "rules_engine"  # type: ignore[attr-defined]
    assert classifier.verification.checked == 0


def test_classify_document_without_a_fallback_nothing_is_checked() -> None:
    rules = _Resolver("rules_engine", _group(PHOENIX), _category(ARCH))

    classifier, result = _classify(rules, None, verify_below=0.8)

    assert result.confident  # type: ignore[attr-defined]
    assert classifier.verification.checked == 0


def test_classify_unit_overruled_document_casts_no_vote() -> None:
    answers = {
        "a.md": (_group(PHOENIX), _category(ARCH, _NAME)),  # not checked at 0.8
        "b.md": (_group(PHOENIX), _category(ARCH, _NAME)),
        "c.md": (_group(PHOENIX), _category(REQS, _HINT)),  # checked, and the AI says Arch
    }

    class PerDocument:
        name = "rules_engine"

        def resolve_group(self, document: Document, taxonomy: Taxonomy) -> GroupMatch:
            return answers[document.file_name][0]

        def resolve_category(self, document: Document, group: str, taxonomy: Taxonomy) -> CategoryMatch:
            return answers[document.file_name][1]

    ai = _Resolver("ai_fallback", _group(PHOENIX, 0.7), _category(ARCH, 0.7))
    unit = SortableUnit(
        source_path=Path("folder"), kind="folder", documents=[_document(name) for name in ("a.md", "b.md", "c.md")]
    )

    result = Classifier(PerDocument(), ai, verify_below=0.8).classify_unit(unit, TAXONOMY)

    assert result.folders == (PHOENIX, ARCH)


# endregion

# region Through sort


class _ScriptedProvider:
    """A fake AI provider that gives the next scripted answer."""

    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._answers:
            message = "Failed to connect to Ollama"
            raise ConnectionError(message)
        return self._answers.pop(0)


def _library(tmp_path: Path, *, verify_below: float) -> Path:
    root = tmp_path / "library"
    for category in ("Bills", "Reports"):
        (root / "Finance" / category).mkdir(parents=True)
    (root / "_sorting").mkdir()
    (root / ".microfiche").mkdir()
    (root / ".microfiche" / "microfiche-config.toml").write_text(
        f'[ai]\nmodel = "m"\nverify_below = {verify_below}\n', encoding="utf-8"
    )
    (root / ".microfiche" / "microfiche-library.json").write_text(
        json.dumps({"groups": [{"name": "Finance", "children": [{"name": "Bills", "hints": ["invoice"]}]}]}),
        encoding="utf-8",
    )
    (root / "_sorting" / "note.md").write_text("Finance: please find the invoice attached.", encoding="utf-8")
    return root


def _ai(library: Library, provider: _ScriptedProvider) -> LLMClassifier:
    return LLMClassifier(provider, library.config.ai)


def test_run_sort_ai_agrees_files_and_reports_the_check(tmp_path: Path) -> None:
    root = _library(tmp_path, verify_below=0.8)
    library = Library(root)

    report = run_sort(library, ai_classifier=_ai(library, _ScriptedProvider("Bills")))

    assert (root / "Finance" / "Bills" / "note.md").is_file()
    assert (report.ai_verification.checked, report.ai_verification.confirmed) == (1, 1)


def test_run_sort_ai_disagrees_leaves_unit_for_review(tmp_path: Path) -> None:
    root = _library(tmp_path, verify_below=0.8)
    library = Library(root)

    report = run_sort(library, ai_classifier=_ai(library, _ScriptedProvider("Reports")))

    assert (root / "_sorting" / "note.md").is_file()
    ((_, classification),) = report.needs_review
    assert classification.ai_overruled
    assert report.ai_verification.overruled == 1


def test_run_sort_ai_unavailable_files_as_the_rules_did_with_one_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    root = _library(tmp_path, verify_below=0.8)
    library = Library(root)

    with caplog.at_level(logging.WARNING):
        report = run_sort(library, ai_classifier=_ai(library, _ScriptedProvider()))

    assert (root / "Finance" / "Bills" / "note.md").is_file()
    assert report.ai_unavailable is not None
    assert report.ai_verification.checked == 0
    assert len([r for r in caplog.records if "AI fallback unavailable" in r.message]) == 1


def test_run_sort_verify_below_zero_makes_no_ai_call(tmp_path: Path) -> None:
    root = _library(tmp_path, verify_below=0)
    library = Library(root)
    provider = _ScriptedProvider("Reports")

    run_sort(library, ai_classifier=_ai(library, provider))

    assert provider.prompts == []
    assert (root / "Finance" / "Bills" / "note.md").is_file()


def test_config_verify_below_defaults_to_off() -> None:
    assert load_config(Path("does-not-exist")).ai.verify_below == 0


# endregion
