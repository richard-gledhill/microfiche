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
