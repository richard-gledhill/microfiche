"""Tests for the calibration harness and for the integrity of the bundled corpus."""

import json
from pathlib import Path

import pytest
from ai_arm import RESULTS_DIR, RecordedAnswers, load
from harness import (
    ADVERSARIAL_KINDS,
    CORPUS_ROOT,
    FLAT_CORPUS_ROOT,
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
from microfiche.core.library.library import Library
from microfiche.core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD

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


def test_evaluate_confident_correct_answer_filed_correctly() -> None:
    outcome = evaluate([_case(confidence=0.9)], threshold=0.8)

    assert (outcome.filed_correct, outcome.filed_wrong, outcome.held_right, outcome.held_other) == (1, 0, 0, 0)


def test_evaluate_confident_wrong_answer_misfile() -> None:
    outcome = evaluate([_case(predicted=("G", "Other"), confidence=0.9)], threshold=0.8)

    assert (outcome.filed_correct, outcome.filed_wrong) == (0, 1)
    assert outcome.misfile_rate == 1.0


def test_evaluate_correct_answer_below_threshold_held() -> None:
    outcome = evaluate([_case(confidence=0.75)], threshold=0.8)

    assert (outcome.filed, outcome.held_right, outcome.held_other) == (0, 1, 0)


def test_evaluate_wrong_answer_below_threshold_held_nothing_right() -> None:
    outcome = evaluate([_case(predicted=("G", "Other"), confidence=0.75)], threshold=0.8)

    assert (outcome.filed, outcome.held_right, outcome.held_other) == (0, 0, 1)


def test_evaluate_threshold_boundary_inclusive() -> None:
    case = _case(confidence=0.8)

    assert evaluate([case], 0.8).filed == 1
    assert evaluate([case], 0.81).filed == 0


def test_evaluate_unresolved_answer_never_filed() -> None:
    case = _case(predicted=("G", None), confidence=0.0)

    assert evaluate([case], 0.0).filed == 0


def test_evaluate_filing_document_belonging_nowhere_misfile() -> None:
    outcome = evaluate([_case(truth=None, predicted=("G", "C"), confidence=0.9)], threshold=0.8)

    assert outcome.filed_wrong == 1


def test_evaluate_holding_document_belonging_nowhere_right() -> None:
    outcome = evaluate([_case(truth=None, predicted=(None, None), confidence=0.0)], threshold=0.8)

    assert (outcome.filed, outcome.held_other, outcome.belonging) == (0, 1, 0)


def test_outcome_rates_and_per_hundred_figures() -> None:
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


def test_outcome_empty_rates_zero_not_error() -> None:
    outcome = evaluate([], threshold=0.8)

    assert (outcome.misfile_rate, outcome.coverage, outcome.misfiles_per_100) == (0.0, 0.0, 0.0)


def test_sweep_raising_threshold_never_files_more() -> None:
    cases = [_case(confidence=c) for c in (0.0, 0.5, 0.75, 0.9, 0.95)]

    filed = [outcome.filed for outcome in sweep(cases)]

    assert filed == sorted(filed, reverse=True)


def test_misfiles_lists_only_wrong_filings() -> None:
    right = _case(confidence=0.9)
    wrong = _case(predicted=("G", "Other"), confidence=0.9)
    held = _case(predicted=("G", "Other"), confidence=0.5)

    assert misfiles([right, wrong, held], 0.8) == [wrong]


def test_by_signal_omits_unresolved_answers() -> None:
    resolved = _case(group_signal="exact", category_signal="hint")
    unresolved = _case(predicted=(None, None), group_signal="none", category_signal="none", confidence=0.0)

    assert list(by_signal([resolved, unresolved])) == ["group exact / category hint"]


def test_by_kind_groups_cases() -> None:
    grouped = by_kind([_case(kind="clear"), _case(kind="hint"), _case(kind="clear")])

    assert {kind: len(cases) for kind, cases in grouped.items()} == {"clear": 2, "hint": 1}


# endregion


# region Blending ordinary and adversarial documents


def test_blend_weights_outcomes_by_share() -> None:
    ordinary = evaluate([_case(confidence=0.9)] * 4, 0.8)  # 4 filed correctly of 4
    adversarial = evaluate([_case(predicted=("G", "X"), confidence=0.9)] * 2, 0.8)  # 2 misfiled of 2

    assert blend(ordinary, adversarial, 0.0) == Blend(right=100.0, wrong=0.0)
    assert blend(ordinary, adversarial, 1.0) == Blend(right=0.0, wrong=100.0)
    half = blend(ordinary, adversarial, 0.5)
    assert (half.right, half.wrong) == (50.0, 50.0)


def test_blend_empty_side_ignored() -> None:
    ordinary = evaluate([_case(confidence=0.9)] * 4, 0.8)
    nothing = evaluate([], 0.8)

    assert blend(ordinary, nothing, 0.3).right == pytest.approx(70.0)


def test_break_even_extra_reviews_per_misfile_avoided() -> None:
    higher = Blend(right=30.0, wrong=5.0)

    assert break_even(Blend(right=80.0, wrong=10.0), higher) == 10.0  # 50 more reviews for 5 fewer misfires


def test_break_even_none_when_higher_threshold_avoids_none() -> None:
    assert break_even(Blend(right=80.0, wrong=5.0), Blend(right=30.0, wrong=5.0)) is None


# endregion


# region The harness on any labelled library


def test_harness_classifies_any_labelled_library(tmp_path: Path) -> None:
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


def test_harness_skips_inbox_and_excluded_reads_nested_files(tmp_path: Path) -> None:
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


def test_corpus_big_and_varied_enough() -> None:
    documents = [d for library in LIBRARIES for d in _documents(library)]

    assert len(LIBRARIES) >= 5
    assert len(documents) >= 100


@pytest.mark.parametrize("library_dir", LIBRARIES, ids=lambda p: p.name)
def test_corpus_every_library_has_config_and_tags(library_dir: Path) -> None:
    assert (library_dir / ".microfiche" / "microfiche-config.toml").is_file()
    kinds = json.loads((library_dir / "kinds.json").read_text(encoding="utf-8"))
    documents = {d.relative_to(library_dir).as_posix() for d in _documents(library_dir)}

    assert set(kinds) == documents
    assert set(kinds.values()) <= KNOWN_KINDS


@pytest.mark.parametrize("library_dir", LIBRARIES, ids=lambda p: p.name)
def test_corpus_documents_sit_where_truth_says(library_dir: Path) -> None:
    taxonomy = Library(library_dir).taxonomy()

    for document in _documents(library_dir):
        parts = document.relative_to(library_dir).parts
        if parts[0] == UNFILED:
            assert len(parts) == 2, document
        else:
            assert len(parts) == 3, document
            assert parts[1] in taxonomy.categories_for(parts[0]), document


@pytest.mark.parametrize("library_dir", LIBRARIES, ids=lambda p: p.name)
def test_corpus_every_library_has_documents_belonging_nowhere(library_dir: Path) -> None:
    assert any(d.relative_to(library_dir).parts[0] == UNFILED for d in _documents(library_dir))


def test_corpus_represents_adversarial_kinds() -> None:
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
def test_known_documents_score_as_signals_promise(
    path_fragment: str, confidence: float, group_signal: str, category_signal: str
) -> None:
    case = _corpus_case(path_fragment)

    assert case.correct
    assert case.confidence == confidence
    assert (case.group_signal, case.category_signal) == (group_signal, category_signal)


def test_known_documents_naming_no_group_unresolved() -> None:
    case = _corpus_case("software-projects/_unfiled/holiday-rota.md")

    assert not case.resolved
    assert case.truth is None


def test_known_documents_cross_reference_misfiles_confidently() -> None:
    """The corpus exists to show this: a passing mention of another project outranks the real one."""

    case = _corpus_case("software-projects/Project Phoenix/02 Architecture/carrier-adapter.md")

    assert not case.correct
    assert case.predicted[0] == "Project Atlas"
    assert case.group_signal == "exact"


# endregion


# region Flat libraries (depth 1)


def _flat_library(tmp_path: Path) -> Path:
    library = tmp_path / "flat"
    (library / ".microfiche").mkdir(parents=True)
    (library / ".microfiche" / "microfiche-config.toml").write_text(
        '[library_structure]\ndepth = 1\n\n[exclusions]\nexclude = ["_*", ".*"]\n', encoding="utf-8"
    )
    return library


def test_harness_flat_library_truth_is_the_group_alone(tmp_path: Path) -> None:
    library = _flat_library(tmp_path)
    for relative, text in (
        ("Project X/a.md", "Project X notes from the call."),
        ("Project X/sub/deep.md", "Project X deeper notes."),  # nested below a group still belongs to it
        ("Project Y/b.md", "Project Y budget."),
        (f"{UNFILED}/c.md", "Nothing relevant here."),
        ("_sorting/waiting.md", "Project X."),  # the inbox
    ):
        path = library / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    cases = {case.path: case for case in load_corpus(tmp_path)}

    assert set(cases) == {"Project X/a.md", "Project X/sub/deep.md", "Project Y/b.md", f"{UNFILED}/c.md"}
    assert cases["Project X/a.md"].truth == ("Project X", None)
    assert cases["Project X/a.md"].predicted == ("Project X", None)
    assert cases["Project X/a.md"].flat
    assert cases["Project X/a.md"].resolved
    assert cases["Project X/a.md"].correct
    assert cases["Project X/sub/deep.md"].truth == ("Project X", None)
    assert not cases[f"{UNFILED}/c.md"].resolved


def test_case_flat_library_resolved_needs_no_category() -> None:
    flat = Case("lib", "G/doc.md", "clear", ("G", None), ("G", None), 0.9, "exact", "none", flat=True)
    two_level = Case("lib", "G/C/doc.md", "clear", ("G", "C"), ("G", None), 0.0, "exact", "none")

    assert flat.resolved
    assert not two_level.resolved
    assert flat.signal == "group exact"
    assert two_level.signal == "group exact / category none"


FLAT_LIBRARIES = sorted(p for p in FLAT_CORPUS_ROOT.iterdir() if p.is_dir())


@pytest.mark.parametrize("library_dir", FLAT_LIBRARIES, ids=lambda p: p.name)
def test_flat_corpus_documents_sit_directly_in_a_group(library_dir: Path) -> None:
    taxonomy = Library(library_dir).taxonomy()
    kinds = json.loads((library_dir / "kinds.json").read_text(encoding="utf-8"))

    assert taxonomy.is_flat
    assert set(kinds) == {d.relative_to(library_dir).as_posix() for d in _documents(library_dir)}
    assert set(kinds.values()) <= KNOWN_KINDS
    for document in _documents(library_dir):
        parts = document.relative_to(library_dir).parts
        assert len(parts) == 2, document
        assert parts[0] == UNFILED or parts[0] in taxonomy.group_names, document


@pytest.fixture(scope="module")
def flat_corpus() -> list[Case]:
    return load_corpus(FLAT_CORPUS_ROOT)


def test_flat_corpus_default_threshold_files_ordinary_documents_accurately(flat_corpus: list[Case]) -> None:
    outcome = evaluate(_ordinary(flat_corpus), DEFAULT_CONFIDENCE_THRESHOLD)

    assert outcome.coverage >= 0.90
    assert outcome.misfile_rate <= 0.02


def test_flat_corpus_group_hints_and_rules_score_as_signals_promise(flat_corpus: list[Case]) -> None:
    by_found = {case.signal: case for case in flat_corpus if case.kind in {"hint", "rule", "clear"}}

    assert by_found["group hint"].confidence == 0.75
    assert by_found["group rule"].confidence == 0.95
    assert by_found["group exact"].confidence == 1.0


def test_flat_corpus_higher_threshold_files_fewer_not_more_accurately(flat_corpus: list[Case]) -> None:
    """The two-level finding holds at depth 1: 0.8 switches the keyword hints off and filed no extra right."""

    default = evaluate(_ordinary(flat_corpus), DEFAULT_CONFIDENCE_THRESHOLD)
    stricter = evaluate(_ordinary(flat_corpus), 0.8)

    assert stricter.filed_correct < 0.5 * default.filed_correct
    assert stricter.misfile_rate <= default.misfile_rate  # and no safer to speak of: ordinary documents never missed


def test_flat_corpus_short_group_name_inside_another_word_misfiles_confidently(flat_corpus: list[Case]) -> None:
    """With group names the only signal, `Car` in `care` and `scarf` is wrong at 1.00: see calibration.md."""

    shortnames = [case for case in flat_corpus if case.kind == "shortname"]

    assert shortnames
    assert all(case.predicted[0] == "Car" and not case.correct and case.confidence == 1.0 for case in shortnames)


def test_flat_corpus_hints_of_two_groups_are_held_not_guessed(flat_corpus: list[Case]) -> None:
    (collision,) = [case for case in flat_corpus if case.kind == "hintcollision"]

    assert not collision.resolved
    assert not collision.is_filed(0.0)


def test_flat_corpus_report_renders_group_signals(flat_corpus: list[Case]) -> None:
    report = format_report(flat_corpus, default_threshold=DEFAULT_CONFIDENCE_THRESHOLD)

    assert "group hint" in report
    assert "category" not in report.split("BY HOW THE ANSWER WAS FOUND")[1]  # a flat library has no category signal


# endregion


# region The report


def test_format_report_has_every_section_and_marks_default() -> None:
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


def test_default_threshold_files_ordinary_documents_accurately(corpus: list[Case]) -> None:
    outcome = evaluate(_ordinary(corpus), DEFAULT_CONFIDENCE_THRESHOLD)

    assert outcome.coverage >= 0.90
    assert outcome.misfile_rate <= 0.02


def test_default_threshold_files_correct_keyword_hints(corpus: list[Case]) -> None:
    """A threshold above the hint score (0.75) silently switches hints off: that is what 0.8 did."""

    hints = [case for case in corpus if case.kind == "hint" and case.correct]

    assert hints
    assert all(case.is_filed(DEFAULT_CONFIDENCE_THRESHOLD) for case in hints)


def test_filename_rules_always_right_at_strictest_threshold(corpus: list[Case]) -> None:
    rules = [case for case in corpus if case.kind == "rule"]

    assert rules
    assert all(case.correct and case.confidence == 0.95 for case in rules)
    assert [case.kind for case in corpus if case.is_filed(0.95)] == ["rule"] * len(rules)


def test_higher_threshold_files_less_not_more_accurately(corpus: list[Case]) -> None:
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


def test_no_threshold_makes_name_match_reliable_when_tricky(corpus: list[Case]) -> None:
    """Category-name matches score 0.9 and are wrong every time on the tricky documents, so no threshold
    between 0.75 and 0.9 can separate them: the weakness is in the matching, not the cut-off."""

    tricky_name_matches = [c for c in _adversarial(corpus) if c.resolved and c.category_signal == "name"]

    assert tricky_name_matches
    assert not any(case.correct for case in tricky_name_matches)


# endregion


# region The AI arm, replayed from saved answers


AI_RESULTS = sorted(RESULTS_DIR.glob("ai-*.json"))


@pytest.mark.skipif(not AI_RESULTS, reason="no saved AI results")
def test_ai_arm_saved_answers_cover_exact_corpus(corpus: list[Case]) -> None:
    saved = {f"{r.taxonomy}/{r.path}" for r in load(AI_RESULTS[0])}

    assert saved == {f"{case.taxonomy}/{case.path}" for case in corpus}


@pytest.mark.skipif(not AI_RESULTS, reason="no saved AI results")
def test_ai_arm_model_accurate_on_what_it_answered() -> None:
    answered = [r for r in load(AI_RESULTS[0]) if r.answered]

    assert sum(r.correct for r in answered) / len(answered) >= 0.95


@pytest.mark.skipif(not AI_RESULTS, reason="no saved AI results")
def test_ai_arm_answers_below_default_threshold_never_file() -> None:
    recorded = RecordedAnswers(load(AI_RESULTS[0]))
    threshold = DEFAULT_CONFIDENCE_THRESHOLD

    alone = evaluate(load_corpus(threshold=threshold), threshold)
    with_ai = evaluate(load_corpus(fallback=recorded, threshold=threshold), threshold)

    assert with_ai.filed == alone.filed


@pytest.mark.skipif(not AI_RESULTS, reason="no saved AI results")
def test_ai_arm_lowering_threshold_lets_answers_file() -> None:
    recorded = RecordedAnswers(load(AI_RESULTS[0]))

    alone = evaluate(load_corpus(threshold=0.7), 0.7)
    with_ai = evaluate(load_corpus(fallback=recorded, threshold=0.7), 0.7)

    assert with_ai.filed > alone.filed
    assert with_ai.filed_correct > alone.filed_correct


# endregion
