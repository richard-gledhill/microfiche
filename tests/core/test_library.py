"""Tests for the Library: its layout, exclusions, taxonomy, and lazily loaded config."""

from pathlib import Path

import pytest
from core.config import ConfigError, MicroficheConfig, TomlConfigParseError, load_config
from core.library.library import Library, ScopeOutsideLibraryError

# region Test helpers


_REPO_CONFIG_DIR = Path(__file__).resolve().parents[2] / "microfiche"


def _defaults() -> MicroficheConfig:
    """A config with every setting at its default (no exclusions)."""

    return load_config(Path("does-not-exist"))


def _shipped() -> MicroficheConfig:
    return load_config(_REPO_CONFIG_DIR)


def _build(root: Path) -> Path:
    (root / "Project Phoenix" / "01 Requirements").mkdir(parents=True)
    (root / "Project Phoenix" / "02 Architecture").mkdir(parents=True)
    (root / "_sorting").mkdir()
    (root / ".microfiche").mkdir()
    return root


# endregion


# region Taxonomy


def test_taxonomy_lists_existing_groups_and_categories(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    config = _defaults()
    config.exclusions.exclude = ["sorting"]
    (root / "sorting").mkdir()

    taxonomy = Library(root, config=config).taxonomy()

    assert taxonomy.categories_for("Project Phoenix") == ["01 Requirements", "02 Architecture"]
    assert "sorting" not in taxonomy.group_names


def test_taxonomy_never_includes_inbox_or_state_folder(tmp_path: Path) -> None:
    """Regression: with no config file the exclusion list was empty, so the inbox and .microfiche
    showed up as groups."""

    root = _build(tmp_path / "library")

    taxonomy = Library(root).taxonomy()  # no .microfiche/microfiche-config.toml exists

    assert taxonomy.group_names == ["Project Phoenix"]


@pytest.mark.parametrize("ancestor", [".vaults", "_work"])
def test_taxonomy_library_under_dot_or_underscore_folder(tmp_path: Path, ancestor: str) -> None:
    """Regression: exclusion patterns like `_*` and `.*` were matched against every part of the
    absolute path, so a library under `~/.vaults` or `~/_work` found no groups at all."""

    root = _build(tmp_path / ancestor / "library")

    taxonomy = Library(root, config=_shipped()).taxonomy()

    assert taxonomy.group_names == ["Project Phoenix"]
    assert taxonomy.categories_for("Project Phoenix") == ["01 Requirements", "02 Architecture"]


def test_taxonomy_exclusion_patterns_apply_inside_library(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    (root / "_archive" / "old").mkdir(parents=True)
    (root / "Project Phoenix" / ".hidden").mkdir()
    (root / "Project Phoenix" / "_scratch").mkdir()

    taxonomy = Library(root, config=_shipped()).taxonomy()

    assert taxonomy.group_names == ["Project Phoenix"]
    assert taxonomy.categories_for("Project Phoenix") == ["01 Requirements", "02 Architecture"]


def test_taxonomy_rebuilt_on_every_call(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    library = Library(root, config=_shipped())
    assert library.taxonomy().group_names == ["Project Phoenix"]

    (root / "Project Atlas" / "01 Requirements").mkdir(parents=True)

    assert library.taxonomy().group_names == ["Project Atlas", "Project Phoenix"]


# endregion


# region Layout


def test_layout_default_paths(tmp_path: Path) -> None:
    library = Library(tmp_path)

    assert library.root == tmp_path
    assert library.state_dir == tmp_path / ".microfiche"
    assert library.inbox == tmp_path / "_sorting"
    assert library.target_dir("Project Phoenix", "02 Architecture") == tmp_path / "Project Phoenix" / "02 Architecture"


def test_layout_inbox_follows_configured_name(tmp_path: Path) -> None:
    config = _defaults()
    config.library_structure.library_inbox = "Incoming"

    assert Library(tmp_path, config=config).inbox == tmp_path / "Incoming"


def test_layout_configured_inbox_excluded_not_default(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    (root / "Incoming").mkdir()
    config = _defaults()
    config.library_structure.library_inbox = "Incoming"

    taxonomy = Library(root, config=config).taxonomy()

    assert "Incoming" not in taxonomy.group_names
    assert ".microfiche" not in taxonomy.group_names


def test_relative_gives_forward_slash_path_inside_library(tmp_path: Path) -> None:
    library = Library(tmp_path)

    assert library.relative(tmp_path / "Project Phoenix" / "02 Architecture" / "a.md") == (
        "Project Phoenix/02 Architecture/a.md"
    )


def test_relative_leaves_outside_path_unchanged(tmp_path: Path) -> None:
    library = Library(tmp_path / "library")
    outside = tmp_path / "elsewhere" / "a.md"

    assert library.relative(outside) == outside.as_posix()


# endregion


# region Exclusion


def test_is_excluded_checks_only_path_inside_library(tmp_path: Path) -> None:
    root = tmp_path / ".vaults" / "library"
    library = Library(root, config=_shipped())

    assert library.is_excluded(root / "_archive" / "a.md") is True
    assert library.is_excluded(root / "Project Phoenix" / "01 Requirements" / "a.md") is False
    assert library.is_excluded(root) is False


def test_is_excluded_always_excludes_inbox_and_state_folder(tmp_path: Path) -> None:
    library = Library(tmp_path, config=_defaults())

    assert library.is_excluded(tmp_path / "_sorting" / "a.md") is True
    assert library.is_excluded(tmp_path / ".microfiche" / "ledger.jsonl") is True


def test_is_excluded_outside_path_refused(tmp_path: Path) -> None:
    library = Library(tmp_path / "library")

    with pytest.raises(ValueError, match="not in the subpath"):
        library.is_excluded(tmp_path / "elsewhere" / "a.md")


# endregion


# region Files


def _touch(root: Path, *relative_paths: str) -> None:
    for relative_path in relative_paths:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


def test_files_lists_non_excluded_in_sorted_order(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    _touch(
        root,
        "Project Phoenix/02 Architecture/b.md",
        "Project Phoenix/01 Requirements/a.md",
        "_sorting/inbox.md",
        ".microfiche/ledger.jsonl",
        "_archive/old.md",
    )

    files = Library(root, config=_shipped()).files()

    assert [path.relative_to(root).as_posix() for path in files] == [
        "Project Phoenix/01 Requirements/a.md",
        "Project Phoenix/02 Architecture/b.md",
    ]


def test_files_limited_to_scope(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    _touch(root, "Project Phoenix/01 Requirements/a.md", "Project Phoenix/02 Architecture/b.md")

    files = Library(root, config=_shipped()).files(root / "Project Phoenix" / "02 Architecture")

    assert [path.name for path in files] == ["b.md"]


def test_files_accepts_cwd_relative_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _build(tmp_path / "library")
    _touch(root, "Project Phoenix/01 Requirements/a.md", "Project Phoenix/02 Architecture/b.md")
    monkeypatch.chdir(tmp_path)

    files = Library(root, config=_shipped()).files(Path("library/Project Phoenix/01 Requirements"))

    assert files == [root / "Project Phoenix" / "01 Requirements" / "a.md"]


def test_files_excluded_scope_not_listed(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    _touch(root, "_sorting/inbox.md")

    assert Library(root, config=_shipped()).files(root / "_sorting") == []


def test_files_outside_scope_refused(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    with pytest.raises(ScopeOutsideLibraryError):
        Library(root, config=_shipped()).files(outside)


# endregion


# region Config


def test_config_loaded_from_state_folder(tmp_path: Path) -> None:
    (tmp_path / ".microfiche").mkdir()
    (tmp_path / ".microfiche" / "microfiche-config.toml").write_text(
        '[library_structure]\nlibrary_inbox = "Incoming"\n\n[classification]\nconfidence_threshold = 0.7\n',
        encoding="utf-8",
    )

    library = Library(tmp_path)

    assert library.config.library_structure.library_inbox == "Incoming"
    assert library.config.classification.confidence_threshold == 0.7
    assert library.inbox == tmp_path / "Incoming"


def test_config_missing_file_uses_defaults(tmp_path: Path) -> None:
    assert Library(tmp_path).config.library_structure.library_inbox == "_sorting"


def test_config_passed_in_used_as_is(tmp_path: Path) -> None:
    config = _defaults()

    assert Library(tmp_path, config=config).config is config


def test_config_loaded_once_changes_stick(tmp_path: Path) -> None:
    library = Library(tmp_path)

    assert library.config is library.config
    library.config.classification.confidence_threshold = 0.5
    assert library.config.classification.confidence_threshold == 0.5


def test_paths_need_no_readable_config(tmp_path: Path) -> None:
    (tmp_path / ".microfiche").mkdir()
    (tmp_path / ".microfiche" / "microfiche-config.toml").write_text("this is [not valid toml", encoding="utf-8")
    library = Library(tmp_path)

    assert library.state_dir == tmp_path / ".microfiche"
    assert library.target_dir("G", "C") == tmp_path / "G" / "C"
    assert library.relative(tmp_path / "G" / "a.md") == "G/a.md"
    with pytest.raises(TomlConfigParseError):
        _ = library.config


# endregion


# region Library file


def _write_library_file(root: Path, text: str) -> None:
    (root / ".microfiche").mkdir(exist_ok=True)
    (root / ".microfiche" / "microfiche-library.json").write_text(text, encoding="utf-8")


def test_library_file_loaded_from_state_folder(tmp_path: Path) -> None:
    _write_library_file(tmp_path, '{"groups": [{"name": "*", "children": [{"name": "Notes", "hints": ["note"]}]}]}')

    assert Library(tmp_path).library_file.hints_for("Any", "Notes") == ["note"]


def test_library_file_missing_file_is_empty(tmp_path: Path) -> None:
    assert Library(tmp_path).library_file.groups == []


def test_library_file_loaded_once(tmp_path: Path) -> None:
    library = Library(tmp_path)

    assert library.library_file is library.library_file


def test_library_file_checked_against_config_depth(tmp_path: Path) -> None:
    (tmp_path / ".microfiche").mkdir()
    (tmp_path / ".microfiche" / "microfiche-config.toml").write_text(
        "[library_structure]\ndepth = 1\n", encoding="utf-8"
    )
    _write_library_file(tmp_path, '{"groups": [{"name": "A", "children": [{"name": "Notes"}]}]}')

    with pytest.raises(ConfigError, match="depth"):
        _ = Library(tmp_path).library_file


def test_library_file_invalid_file_raises_config_error(tmp_path: Path) -> None:
    _write_library_file(tmp_path, '{"groups": [')

    with pytest.raises(ConfigError, match="Invalid JSON"):
        _ = Library(tmp_path).library_file


def test_paths_need_no_readable_library_file(tmp_path: Path) -> None:
    _write_library_file(tmp_path, "this is not json")
    library = Library(tmp_path)

    assert library.state_dir == tmp_path / ".microfiche"
    assert library.target_dir("G", "C") == tmp_path / "G" / "C"


# endregion
