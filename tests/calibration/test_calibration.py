"""Tests for the calibration harness and for the integrity of the bundled corpus."""

import json
from pathlib import Path

import pytest
from ai_arm import RESULTS_DIR, RecordedAnswers, load
from core.library.library import Library
from core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD
from harness import (
    ADVERSARIAL_KINDS,
    CORPUS_ROOT,
    UNFILED,
    Blend,
    Case,
    blend,
    break_even,
    by_kind,
    by_signal,
    evaluate,
    format_report,
    load_corpus,
    misfiles,
    sweep,
)

# region Test helpers


KNOWN_KINDS = ADVERSARIAL_KINDS | {"clear", "hint", "rule", "fuzzy", "shortform", "nogroup"}


def _case(
    *,
    truth: tuple[str, str] | None = ("G", "C"),
    predicted: tuple[str | None, str | None] = ("G", "C"),
    confidence: float = 0.9,
    kind: str = "clear",
    group_signal: str = "exact",
    category_signal: str = "name",
) -> Case:
    return Case("lib", "G/C/doc.md", kind, truth, predicted, confidence, group_signal, category_signal)


# endregion


# region The maths of one threshold


def test_a_confident_correct_answer_is_filed_correctly() -> None:
    outcome = evaluate([_case(confidence=0.9)], threshold=0.8)

    assert (outcome.filed_correct, outcome.filed_wrong, outcome.held_right, outcome.held_other) == (1, 0, 0, 0)


def test_a_confident_wrong_answer_is_a_misfile() -> None:
    outcome = evaluate([_case(predicted=("G", "Other"), confidence=0.9)], threshold=0.8)

    assert (outcome.filed_correct, outcome.filed_wrong) == (0, 1)
    assert outcome.misfile_rate == 1.0


def test_a_correct_answer_below_the_threshold_is_held_though_right() -> None:
    outcome = evaluate([_case(confidence=0.75)], threshold=0.8)

    assert (outcome.filed, outcome.held_right, outcome.held_other) == (0, 1, 0)


def test_a_wrong_answer_below_the_threshold_is_held_with_nothing_right_on_offer() -> None:
    outcome = evaluate([_case(predicted=("G", "Other"), confidence=0.75)], threshold=0.8)

    assert (outcome.filed, outcome.held_right, outcome.held_other) == (0, 0, 1)


def test_the_threshold_boundary_is_inclusive() -> None:
    case = _case(confidence=0.8)

    assert evaluate([case], 0.8).filed == 1
    assert evaluate([case], 0.81).filed == 0


def test_an_unresolved_answer_is_never_filed_even_at_a_zero_threshold() -> None:
    case = _case(predicted=("G", None), confidence=0.0)

    assert evaluate([case], 0.0).filed == 0


def test_filing_a_document_that_belongs_nowhere_is_a_misfile() -> None:
    outcome = evaluate([_case(truth=None, predicted=("G", "C"), confidence=0.9)], threshold=0.8)

    assert outcome.filed_wrong == 1


def test_holding_a_document_that_belongs_nowhere_is_right_but_not_a_missed_filing() -> None:
    outcome = evaluate([_case(truth=None, predicted=(None, None), confidence=0.0)], threshold=0.8)

    assert (outcome.filed, outcome.held_other, outcome.belonging) == (0, 1, 0)


def test_rates_and_per_hundred_figures() -> None:
    cases = [
        _case(confidence=0.9),
        _case(confidence=0.9),
        _case(confidence=0.9),
        _case(predicted=("G", "Other"), confidence=0.9),
        _case(confidence=0.75),
        _case(truth=None, predicted=(None, None), confidence=0.0),
    ]

    outcome = evaluate(cases, threshold=0.8)

    assert (outcome.total, outcome.belonging, outcome.filed) == (6, 5, 4)
    assert outcome.misfile_rate == 0.25  # 1 wrong of 4 filed
    assert outcome.coverage == 3 / 5  # 3 correct filings of 5 documents that belong somewhere
    assert outcome.misfiles_per_100 == pytest.approx(100 / 6)


def test_rates_of_an_empty_outcome_are_zero_not_an_error() -> None:
    outcome = evaluate([], threshold=0.8)

    assert (outcome.misfile_rate, outcome.coverage, outcome.misfiles_per_100) == (0.0, 0.0, 0.0)


def test_raising_the_threshold_never_files_more() -> None:
    cases = [_case(confidence=c) for c in (0.0, 0.5, 0.75, 0.9, 0.95)]

    filed = [outcome.filed for outcome in sweep(cases)]

    assert filed == sorted(filed, reverse=True)


def test_misfiles_lists_only_wrong_filings() -> None:
    right = _case(confidence=0.9)
    wrong = _case(predicted=("G", "Other"), confidence=0.9)
    held = _case(predicted=("G", "Other"), confidence=0.5)

    assert misfiles([right, wrong, held], 0.8) == [wrong]


def test_by_signal_leaves_out_unresolved_answers() -> None:
    resolved = _case(group_signal="exact", category_signal="hint")
    unresolved = _case(predicted=(None, None), group_signal="none", category_signal="none", confidence=0.0)

    assert list(by_signal([resolved, unresolved])) == ["group exact / category hint"]


def test_by_kind_groups_cases() -> None:
    grouped = by_kind([_case(kind="clear"), _case(kind="hint"), _case(kind="clear")])

    assert {kind: len(cases) for kind, cases in grouped.items()} == {"clear": 2, "hint": 1}


# endregion


# region Blending ordinary and adversarial documents


def test_a_blend_weights_the_ordinary_and_adversarial_outcomes_by_share() -> None:
    ordinary = evaluate([_case(confidence=0.9)] * 4, 0.8)  # 4 filed correctly of 4
    adversarial = evaluate([_case(predicted=("G", "X"), confidence=0.9)] * 2, 0.8)  # 2 misfiled of 2

    assert blend(ordinary, adversarial, 0.0) == Blend(right=100.0, wrong=0.0)
    assert blend(ordinary, adversarial, 1.0) == Blend(right=0.0, wrong=100.0)
    half = blend(ordinary, adversarial, 0.5)
    assert (half.right, half.wrong) == (50.0, 50.0)


def test_a_blend_with_an_empty_side_ignores_it() -> None:
    ordinary = evaluate([_case(confidence=0.9)] * 4, 0.8)
    nothing = evaluate([], 0.8)

    assert blend(ordinary, nothing, 0.3).right == pytest.approx(70.0)


def test_break_even_is_extra_reviews_per_misfile_avoided() -> None:
    higher = Blend(right=30.0, wrong=5.0)

    assert break_even(Blend(right=80.0, wrong=10.0), higher) == 10.0  # 50 more reviews for 5 fewer misfires


def test_break_even_is_none_when_the_higher_threshold_avoids_no_misfiles() -> None:
    assert break_even(Blend(right=80.0, wrong=5.0), Blend(right=30.0, wrong=5.0)) is None


# endregion


# region The harness on any labelled library


def test_the_harness_classifies_any_labelled_library(tmp_path: Path) -> None:
    library = tmp_path / "lib"
    (library / ".microfiche").mkdir(parents=True)
    (library / ".microfiche" / "microfiche-config.toml").write_text(
        '[exclusions]\nexclude = ["_*", ".*"]\n', encoding="utf-8"
    )
    (library / "Project X" / "Notes").mkdir(parents=True)
    (library / "Project X" / "Notes" / "a.md").write_text("Project X notes from the call.", encoding="utf-8")
    (library / UNFILED).mkdir()
    (library / UNFILED / "b.md").write_text("Nothing relevant here.", encoding="utf-8")

    cases = {case.path: case for case in load_corpus(tmp_path)}

    assert cases["Project X/Notes/a.md"].truth == ("Project X", "Notes")
    assert cases["Project X/Notes/a.md"].correct
    assert cases["Project X/Notes/a.md"].kind == "untagged"  # no kinds.json needed
    assert cases[f"{UNFILED}/b.md"].truth is None
    assert not cases[f"{UNFILED}/b.md"].resolved


def test_the_harness_skips_the_inbox_excluded_folders_and_loose_files_and_reads_nested_files(tmp_path: Path) -> None:
    library = tmp_path / "lib"
    (library / ".microfiche").mkdir(parents=True)
    (library / ".microfiche" / "microfiche-config.toml").write_text(
        '[exclusions]\nexclude = ["_*", ".*"]\n', encoding="utf-8"
    )
    for relative in (
        "_sorting/waiting.md",  # the inbox
        "_archive/old.md",  # an excluded folder
        "Project X/loose.md",  # loose in a group, so it has no category
        "Project X/Notes/sub/deep.md",  # nested below a category
        "README.md",  # loose at the top
    ):
        path = library / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Project X notes.", encoding="utf-8")

    cases = load_corpus(tmp_path)

    assert [(case.path, case.truth) for case in cases] == [("Project X/Notes/sub/deep.md", ("Project X", "Notes"))]


# endregion


# region The bundled corpus


LIBRARIES = sorted(p for p in CORPUS_ROOT.iterdir() if p.is_dir())


def _documents(library_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(library_dir.rglob("*"))
        if p.is_file() and not p.relative_to(library_dir).parts[0].startswith(".") and p.name != "kinds.json"
    ]


def test_the_corpus_is_big_and_varied_enough_to_mean_something() -> None:
    documents = [d for library in LIBRARIES for d in _documents(library)]

    assert len(LIBRARIES) >= 5
    assert len(documents) >= 100


@pytest.mark.parametrize("library_dir", LIBRARIES, ids=lambda p: p.name)
def test_every_library_has_a_config_and_a_tag_for_every_document(library_dir: Path) -> None:
    assert (library_dir / ".microfiche" / "microfiche-config.toml").is_file()
    kinds = json.loads((library_dir / "kinds.json").read_text(encoding="utf-8"))
    documents = {d.relative_to(library_dir).as_posix() for d in _documents(library_dir)}

    assert set(kinds) == documents
    assert set(kinds.values()) <= KNOWN_KINDS


@pytest.mark.parametrize("library_dir", LIBRARIES, ids=lambda p: p.name)
def test_every_document_sits_where_its_truth_says_it_does(library_dir: Path) -> None:
    taxonomy = Library(library_dir).taxonomy()

    for document in _documents(library_dir):
        parts = document.relative_to(library_dir).parts
        if parts[0] == UNFILED:
            assert len(parts) == 2, document
        else:
            assert len(parts) == 3, document
            assert parts[1] in taxonomy.categories_for(parts[0]), document


@pytest.mark.parametrize("library_dir", LIBRARIES, ids=lambda p: p.name)
def test_every_library_has_documents_that_belong_nowhere(library_dir: Path) -> None:
    assert any(d.relative_to(library_dir).parts[0] == UNFILED for d in _documents(library_dir))


def test_the_kinds_that_make_a_name_or_hint_match_the_wrong_answer_are_represented() -> None:
    kinds = {case.kind for case in load_corpus()}

    assert kinds >= ADVERSARIAL_KINDS


# endregion


# region Known documents classify the way the signal table says


def _corpus_case(path_fragment: str) -> Case:
    (case,) = [c for c in load_corpus() if path_fragment in f"{c.taxonomy}/{c.path}"]
    return case


@pytest.mark.parametrize(
    ("path_fragment", "confidence", "group_signal", "category_signal"),
    [
        ("software-projects/Project Phoenix/04 Meeting Notes/meeting-notes-2026-03-02.md", 0.95, "exact", "rule"),
        ("software-projects/Project Phoenix/02 Architecture/architecture-notes.md", 0.9, "exact", "name"),
        ("software-projects/Project Phoenix/01 Requirements/backlog-march.md", 0.75, "exact", "hint"),
    ],
)
def test_known_documents_score_the_way_the_signals_promise(
    path_fragment: str, confidence: float, group_signal: str, category_signal: str
) -> None:
    case = _corpus_case(path_fragment)

    assert case.correct
    assert case.confidence == confidence
    assert (case.group_signal, case.category_signal) == (group_signal, category_signal)


def test_a_document_that_names_no_group_is_not_resolved() -> None:
    case = _corpus_case("software-projects/_unfiled/holiday-rota.md")

    assert not case.resolved
    assert case.truth is None


def test_a_cross_reference_files_under_the_wrong_group_with_full_confidence() -> None:
    """The corpus exists to show this: a passing mention of another project outranks the real one."""

    case = _corpus_case("software-projects/Project Phoenix/02 Architecture/carrier-adapter.md")

    assert not case.correct
    assert case.predicted[0] == "Project Atlas"
    assert case.group_signal == "exact"


# endregion


# region The report


def test_the_report_has_every_section_and_marks_the_default() -> None:
    report = format_report(load_corpus(), default_threshold=0.8)

    for heading in (
        "ALL DOCUMENTS",
        "ORDINARY DOCUMENTS",
        "ADVERSARIAL DOCUMENTS",
        "BY HOW THE ANSWER WAS FOUND",
        "MISFILES AT",
        "IF THIS SHARE",
    ):
        assert heading in report
    assert "<- default" in report


# endregion


# region What the calibration found, pinned


#
# These tests state the findings in docs/development/calibration.md. If one fails, the classifier
# or the corpus changed enough that the evidence behind DEFAULT_CONFIDENCE_THRESHOLD may no longer
# hold: re-run tests/calibration/report.py, re-read the document, and update both together.


@pytest.fixture(scope="module")
def corpus() -> list[Case]:
    return load_corpus()


def _ordinary(corpus: list[Case]) -> list[Case]:
    return [case for case in corpus if case.kind not in ADVERSARIAL_KINDS]


def _adversarial(corpus: list[Case]) -> list[Case]:
    return [case for case in corpus if case.kind in ADVERSARIAL_KINDS]


def test_at_the_default_threshold_ordinary_documents_are_filed_accurately_and_mostly_filed(corpus: list[Case]) -> None:
    outcome = evaluate(_ordinary(corpus), DEFAULT_CONFIDENCE_THRESHOLD)

    assert outcome.coverage >= 0.90
    assert outcome.misfile_rate <= 0.02


def test_the_default_does_not_hold_back_correct_keyword_hint_matches(corpus: list[Case]) -> None:
    """A threshold above the hint score (0.75) silently switches hints off: that is what 0.8 did."""

    hints = [case for case in corpus if case.kind == "hint" and case.correct]

    assert hints
    assert all(case.is_filed(DEFAULT_CONFIDENCE_THRESHOLD) for case in hints)


def test_filename_rules_are_right_every_time_and_survive_the_strictest_useful_threshold(corpus: list[Case]) -> None:
    rules = [case for case in corpus if case.kind == "rule"]

    assert rules
    assert all(case.correct and case.confidence == 0.95 for case in rules)
    assert [case.kind for case in corpus if case.is_filed(0.95)] == ["rule"] * len(rules)


def test_a_higher_threshold_files_less_without_filing_any_more_accurately(corpus: list[Case]) -> None:
    """The central finding: 0.8 is not safer per document filed, it just files far fewer.

    With 5% tricky documents the share of auto-filed documents that are wrong is about the same at 0.75
    and at 0.8. If that stops being true - say the classifier learns to tell a confident name match from
    an incidental one - then a higher default may be worth it, and calibration.md needs rewriting.
    """

    ordinary, adversarial = _ordinary(corpus), _adversarial(corpus)

    def wrong_share(threshold: float) -> float:
        mix = blend(evaluate(ordinary, threshold), evaluate(adversarial, threshold), 0.05)
        return mix.wrong / (mix.right + mix.wrong)

    assert wrong_share(0.8) >= wrong_share(DEFAULT_CONFIDENCE_THRESHOLD) - 0.02
    assert (
        blend(evaluate(ordinary, 0.8), evaluate(adversarial, 0.8), 0.05).right
        < 0.5
        * blend(
            evaluate(ordinary, DEFAULT_CONFIDENCE_THRESHOLD), evaluate(adversarial, DEFAULT_CONFIDENCE_THRESHOLD), 0.05
        ).right
    )


def test_no_threshold_makes_a_confident_category_name_match_reliable_on_tricky_documents(corpus: list[Case]) -> None:
    """Category-name matches score 0.9 and are wrong every time on the tricky documents, so no threshold
    between 0.75 and 0.9 can separate them: the weakness is in the matching, not the cut-off."""

    tricky_name_matches = [c for c in _adversarial(corpus) if c.resolved and c.category_signal == "name"]

    assert tricky_name_matches
    assert not any(case.correct for case in tricky_name_matches)


# endregion


# region The AI arm, replayed from saved answers


AI_RESULTS = sorted(RESULTS_DIR.glob("ai-*.json"))


@pytest.mark.skipif(not AI_RESULTS, reason="no saved AI results")
def test_the_saved_ai_answers_cover_exactly_the_corpus(corpus: list[Case]) -> None:
    saved = {f"{r.taxonomy}/{r.path}" for r in load(AI_RESULTS[0])}

    assert saved == {f"{case.taxonomy}/{case.path}" for case in corpus}


@pytest.mark.skipif(not AI_RESULTS, reason="no saved AI results")
def test_the_measured_model_was_accurate_on_what_it_answered() -> None:
    answered = [r for r in load(AI_RESULTS[0]) if r.answered]

    assert sum(r.correct for r in answered) / len(answered) >= 0.95


@pytest.mark.skipif(not AI_RESULTS, reason="no saved AI results")
def test_ai_answers_score_below_the_default_threshold_so_they_never_file_by_default() -> None:
    recorded = RecordedAnswers(load(AI_RESULTS[0]))
    threshold = DEFAULT_CONFIDENCE_THRESHOLD

    alone = evaluate(load_corpus(threshold=threshold), threshold)
    with_ai = evaluate(load_corpus(fallback=recorded, threshold=threshold), threshold)

    assert with_ai.filed == alone.filed


@pytest.mark.skipif(not AI_RESULTS, reason="no saved AI results")
def test_lowering_the_threshold_to_the_ai_score_lets_ai_answers_file() -> None:
    recorded = RecordedAnswers(load(AI_RESULTS[0]))

    alone = evaluate(load_corpus(threshold=0.7), 0.7)
    with_ai = evaluate(load_corpus(fallback=recorded, threshold=0.7), 0.7)

    assert with_ai.filed > alone.filed
    assert with_ai.filed_correct > alone.filed_correct


# endregion
