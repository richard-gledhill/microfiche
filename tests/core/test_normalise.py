"""Tests for the shared spelling used to compare folder names, hints and document text."""

from pathlib import Path

import pytest
from microfiche.core.config import ClassificationConfig, load_config
from microfiche.core.rules.group_rules import match_group
from microfiche.core.rules.keyword_rules import match_category, match_group_hints
from microfiche.core.rules.normalise import contains_words, normalise_for_matching

# region Normalise for matching


@pytest.mark.parametrize(
    "name",
    [
        "Meeting Notes",
        "meeting-notes",
        "meeting_notes",
        "MeetingNotes",
        "meetingNotes",
        "01-meeting-notes",
        "02_meeting_notes",
        "03. Meeting Notes",
        "04 - Meeting Notes",
        "(Meeting) Notes",
    ],
)
def test_normalise_for_matching_folder_styles_same_words(name: str) -> None:
    assert normalise_for_matching(name, folder_name=True) == "meeting notes"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("R&D", "r and d"),
        ("Terms & Conditions", "terms and conditions"),
        ("Tom's Recipes", "toms recipes"),
        (f"Tom{chr(0x2019)}s Recipes", "toms recipes"),
        ("Café", "cafe"),
        ("C++ Notes", "c++ notes"),
        ("C# Notes", "c# notes"),
        ("2024-03 Invoices", "2024 03 invoices"),
        ("1.2 Design", "1 2 design"),
        ("NASAReport", "nasa report"),
        ("&", "and"),
        ("---", ""),
        ("(  )", ""),
    ],
)
def test_normalise_for_matching_special_characters(name: str, expected: str) -> None:
    assert normalise_for_matching(name, folder_name=True) == expected


def test_normalise_for_matching_text_keeps_digit_prefix_and_camel_case() -> None:
    # Document text has its own numbers and capitalisation.
    assert normalise_for_matching("01 TermsAndConditions") == "01 termsandconditions"


@pytest.mark.parametrize("name", ["01-Meeting_Notes", "R&D", "Tom's Café", "---"])
def test_normalise_for_matching_idempotent(name: str) -> None:
    once = normalise_for_matching(name, folder_name=True)
    assert normalise_for_matching(once, folder_name=True) == once


# endregion

# region Whole words


@pytest.mark.parametrize("text", ["car", "my car insurance", "the car.", "(Car)", "car, bus", "see car"])
def test_contains_words_whole_word_found(text: str) -> None:
    assert contains_words(normalise_for_matching(text), "car")


@pytest.mark.parametrize("text", ["carrier", "care", "scarf", "cars", "card payment"])
def test_contains_words_inside_longer_word_not_found(text: str) -> None:
    assert not contains_words(normalise_for_matching(text), "car")


def test_contains_words_multi_word_phrase_in_order() -> None:
    assert contains_words("the meeting notes from monday", "meeting notes")
    assert not contains_words("meeting minutes and notes", "meeting notes")


def test_contains_words_empty_phrase_never_found() -> None:
    assert not contains_words("anything", "")


# endregion

# region Rules use the normal form


@pytest.mark.parametrize(
    "folder", ["meeting-notes", "meeting_notes", "MeetingNotes", "01-meeting-notes", "Meeting Notes"]
)
def test_match_category_folder_style_same_result(folder: str) -> None:
    result = match_category(
        "Minutes: Meeting Notes from Tuesday", [folder], {}, name_confidence=0.9, hint_confidence=0.75
    )

    assert (result.name, result.confidence) == (folder, 0.9)


@pytest.mark.parametrize("folder", ["project-alpha", "project_alpha", "ProjectAlpha", "Project Alpha"])
def test_match_group_folder_style_exact(folder: str) -> None:
    result = match_group("Status of Project Alpha", [folder], fuzzy_threshold=85)

    assert (result.name, result.confidence) == (folder, 1.0)


def test_match_group_ampersand_exact_not_fuzzy() -> None:
    result = match_group("Terms and Conditions apply", ["Terms & Conditions"], fuzzy_threshold=85)

    assert result.confidence == 1.0


def test_match_group_unmatchable_name_skipped() -> None:
    assert match_group("anything", ["---"], fuzzy_threshold=0).name is None


def test_match_group_off_literal() -> None:
    result = match_group("Status of Project Alpha", ["project-alpha"], fuzzy_threshold=100, normalise=False)

    assert result.name is None


def test_match_category_off_literal() -> None:
    result = match_category(
        "Meeting Notes", ["meeting-notes"], {}, name_confidence=0.9, hint_confidence=0.75, normalise=False
    )

    assert result.name is None


def test_match_category_hint_normalised() -> None:
    result = match_category(
        "Budget for R and D", ["Research"], {"Research": ["r&d"]}, name_confidence=0.9, hint_confidence=0.75
    )

    assert (result.name, result.confidence) == ("Research", 0.75)


def test_match_group_hints_normalised() -> None:
    result = match_group_hints("Budget for R and D", {"Research": ["r&d"]}, confidence=0.75)

    assert result.name == "Research"


def test_classification_config_normalise_names_default_on() -> None:
    settings: ClassificationConfig = load_config(Path("does-not-exist")).classification

    assert settings.normalise_names is True


# endregion


# region Rules match whole words


def test_match_group_inside_longer_word_unresolved() -> None:
    assert match_group("lawn care and a wool scarf", ["Car"], fuzzy_threshold=85).name is None


def test_match_group_whole_word_found_with_punctuation() -> None:
    assert match_group("Insurance for the (Car).", ["Car"], fuzzy_threshold=85).confidence == 1.0


def test_match_group_fuzzy_span_inside_longer_word_refused() -> None:
    assert match_group("the projectalphabet file", ["Project Alpha"], fuzzy_threshold=80).name is None


def test_match_group_fuzzy_whole_words_accepted() -> None:
    result = match_group("the projct alpha file", ["Project Alpha"], fuzzy_threshold=85)

    assert result.name == "Project Alpha"
    assert result.confidence < 1.0


def test_match_category_hint_inside_longer_word_unresolved() -> None:
    result = match_category(
        "Lectures on graphs", ["Notes"], {"Notes": ["lecture"]}, name_confidence=0.9, hint_confidence=0.75
    )

    assert result.name is None


def test_match_category_substring_still_matches_when_normalisation_off() -> None:
    result = match_category(
        "Lectures on graphs",
        ["Notes"],
        {"Notes": ["lecture"]},
        name_confidence=0.9,
        hint_confidence=0.75,
        normalise=False,
    )

    assert result.name == "Notes"


# endregion
