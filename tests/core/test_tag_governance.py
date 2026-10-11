"""Tests for TagIndex parsing and suggest-only tag governance."""

from pathlib import Path

from core.obsidian.tag_index import TagIndex
from core.obsidian.tag_mapper import map_tags


def test_tag_index_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "TagIndex.md"
    index = TagIndex(path=path, canonical_tags={"requirements", "architecture"})
    index.save()

    reloaded = TagIndex.load(path)

    assert reloaded.canonical_tags == {"requirements", "architecture"}


def test_map_tags_suggest_mode_normalizes_and_proposes_new(tmp_path: Path) -> None:
    index = TagIndex(path=tmp_path / "TagIndex.md", canonical_tags={"requirements"})

    resolved = map_tags(["requirement", "brand-new-tag"], index, mode="suggest")

    assert "requirements" in resolved
    assert "brand-new-tag" in resolved
    assert "brand-new-tag" in index.proposed_tags


def test_map_tags_strict_mode_drops_unmatched_tags(tmp_path: Path) -> None:
    index = TagIndex(path=tmp_path / "TagIndex.md", canonical_tags={"requirements"})

    resolved = map_tags(["requirement", "totally-unrelated"], index, mode="strict")

    assert resolved == ["requirements"]


def test_map_tags_candidate_matched_ignoring_case(tmp_path: Path) -> None:
    index = TagIndex(path=tmp_path / "TagIndex.md", canonical_tags={"python"})

    assert map_tags(["Python"], index, mode="strict") == ["python"]


def test_map_tags_candidate_matched_ignoring_punctuation(tmp_path: Path) -> None:
    index = TagIndex(path=tmp_path / "TagIndex.md", canonical_tags={"machine-learning"})

    assert map_tags(["Machine_Learning"], index, mode="strict") == ["machine-learning"]


def test_map_tags_accented_tag_matched_to_itself_ignoring_case(tmp_path: Path) -> None:
    index = TagIndex(path=tmp_path / "TagIndex.md", canonical_tags={"café"})

    assert map_tags(["Café"], index, mode="strict") == ["café"]


def test_map_tags_unrelated_word_not_mapped_by_stripping_accents(tmp_path: Path) -> None:
    # Accents are part of the tag: "ber" must not be read as "über" by deleting the umlaut from one side.
    index = TagIndex(path=tmp_path / "TagIndex.md", canonical_tags={"über"})

    assert map_tags(["ber"], index, mode="strict") == []
