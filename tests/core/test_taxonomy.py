"""Tests for library taxonomy discovery."""

from pathlib import Path

from core.library.taxonomy import discover_taxonomy


def test_discover_taxonomy_finds_groups_and_categories(tmp_path: Path) -> None:
    (tmp_path / "Project Phoenix" / "01 Requirements").mkdir(parents=True)
    (tmp_path / "Project Phoenix" / "02 Architecture").mkdir(parents=True)
    (tmp_path / "sorting").mkdir()

    taxonomy = discover_taxonomy(tmp_path, exclusions=["sorting"])

    assert taxonomy.group_names == ["Project Phoenix"]
    assert taxonomy.categories_for("Project Phoenix") == ["01 Requirements", "02 Architecture"]
