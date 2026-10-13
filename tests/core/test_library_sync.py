"""Tests for keeping the library file in step with the library's folders."""

import json
from pathlib import Path
from typing import Any

import pytest
from microfiche.core.config import ConfigError, load_config
from microfiche.core.library.library import Library
from microfiche.core.library.library_file import LIBRARY_FILENAME, FolderNode, load_library_file
from microfiche.core.library.library_sync import sync_library_file

# region Test helpers


def _build(root: Path) -> Path:
    (root / "Project Phoenix" / "01 Requirements").mkdir(parents=True)
    (root / "Project Phoenix" / "02 Architecture").mkdir(parents=True)
    (root / "_sorting").mkdir()
    return root


def _file_path(root: Path) -> Path:
    return root / ".microfiche" / LIBRARY_FILENAME


def _write(root: Path, data: dict[str, Any]) -> bytes:
    """Write ``data`` as the library file and return its bytes."""

    path = _file_path(root)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path.read_bytes()


def _tree(root: Path) -> dict[str, list[str]]:
    """The library file on disk as {group: [category, ...]}, in file order."""

    file = load_library_file(root / ".microfiche", depth=2)
    return {group.name: [child.name for child in group.children] for group in file.groups}


# endregion


# region Public API


# region sync_library_file: creating and adding


def test_sync_library_file_no_file_creates_it_without_hints(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")

    sync = sync_library_file(Library(root))

    assert sync.created
    assert sync.added == [
        "Project Phoenix",
        "Project Phoenix/01 Requirements",
        "Project Phoenix/02 Architecture",
    ]
    assert _tree(root) == {"Project Phoenix": ["01 Requirements", "02 Architecture"]}
    file = load_library_file(root / ".microfiche", depth=2)
    assert all(not node.hints and not node.rules for node in file.groups)


def test_sync_library_file_second_run_changes_nothing(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    sync_library_file(Library(root))
    first = _file_path(root).read_bytes()

    sync = sync_library_file(Library(root))

    assert not sync.created
    assert sync.added == []
    assert _file_path(root).read_bytes() == first


def test_sync_library_file_new_folder_added_and_reported_once(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    sync_library_file(Library(root))
    (root / "Project Phoenix" / "03 Research").mkdir()

    first = sync_library_file(Library(root))
    second = sync_library_file(Library(root))

    assert first.added == ["Project Phoenix/03 Research"]
    assert not first.created
    assert second.added == []
    assert _tree(root)["Project Phoenix"] == ["01 Requirements", "02 Architecture", "03 Research"]


def test_sync_library_file_new_group_lists_its_categories(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    sync_library_file(Library(root))
    (root / "Project Atlas" / "01 Requirements").mkdir(parents=True)

    sync = sync_library_file(Library(root))

    assert sync.added == ["Project Atlas", "Project Atlas/01 Requirements"]
    assert list(_tree(root)) == ["Project Phoenix", "Project Atlas"]  # appended after the existing group


def test_sync_library_file_no_folders_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "_sorting").mkdir(parents=True)

    sync = sync_library_file(Library(root))

    assert not sync.created
    assert not _file_path(root).exists()


def test_sync_library_file_matches_folder_names_ignoring_case(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    before = _write(
        root,
        {"groups": [{"name": "project phoenix", "children": [{"name": "01 REQUIREMENTS", "hints": ["spec"]}]}]},
    )

    sync = sync_library_file(Library(root))

    assert sync.added == ["project phoenix/02 Architecture"]  # named as the entry that holds it is spelt
    assert _tree(root) == {"project phoenix": ["01 REQUIREMENTS", "02 Architecture"]}  # the user's spelling is kept
    assert _file_path(root).read_bytes() != before


def test_sync_library_file_keeps_edit_made_after_library_was_opened(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    library = Library(root)
    assert library.library_file.groups == []  # loaded and kept before the user edits the file
    _write(root, {"groups": [{"name": "Project Phoenix", "hints": ["phoenix"]}]})

    sync_library_file(library)

    file = load_library_file(root / ".microfiche", depth=2)
    assert file.groups[0].hints == ["phoenix"]


def test_sync_library_file_rewrite_keeps_schema_and_non_ascii_text(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    _write(
        root,
        {
            "$schema": "./microfiche-library.schema.json",
            "groups": [
                {
                    "name": "Project Phoenix",
                    "description": "Café — résumé",
                    "hints": ["naïve"],
                    "rules": [{"pattern": "rapport*.docx"}],
                    "children": [{"name": "01 Requirements", "hints": []}],
                }
            ],
        },
    )

    sync_library_file(Library(root))

    after = json.loads(_file_path(root).read_text(encoding="utf-8"))
    assert after["$schema"] == "./microfiche-library.schema.json"
    phoenix = after["groups"][0]
    assert phoenix["description"] == "Café — résumé"
    assert phoenix["hints"] == ["naïve"]
    assert phoenix["rules"] == [{"pattern": "rapport*.docx"}]
    assert phoenix["children"][0] == {"name": "01 Requirements"}  # an empty list is left out, not changed in meaning
    assert not list(_file_path(root).parent.glob("*.tmp"))


def test_sync_library_file_skips_folder_names_the_file_cannot_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a case-sensitive file system `X` and `x` can both exist; listing both would make the file unloadable."""

    root = _build(tmp_path / "library")
    names = ["Atlas", "atlas", "back\\slash", " padded", "Fine"]
    monkeypatch.setattr(
        Library, "structure", lambda self: [FolderNode.model_construct(name=name, children=[]) for name in names]
    )

    sync = sync_library_file(Library(root))

    assert sync.added == ["Atlas", "Fine"]
    assert list(_tree(root)) == ["Atlas", "Fine"]  # and the file loads again


def test_sync_library_file_refreshes_loaded_library_file(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    library = Library(root)
    assert library.library_file.groups == []

    sync_library_file(library)

    assert [group.name for group in library.library_file.groups] == ["Project Phoenix"]


# endregion


# region sync_library_file: preserving what the user wrote


def test_sync_library_file_keeps_hints_rules_wildcards_and_order(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    (root / "Project Phoenix" / "03 Research").mkdir()
    (root / "Project Atlas").mkdir()
    written = {
        "groups": [
            {"name": "*", "children": [{"name": "01 Requirements", "hints": ["requirement"]}]},
            {
                "name": "Project Phoenix",
                "description": "The Phoenix project.",
                "hints": ["phoenix"],
                "children": [
                    {"name": "02 Architecture", "rules": [{"pattern": "adr*.md"}]},
                    {"name": "01 Requirements"},
                ],
            },
        ]
    }
    _write(root, written)

    sync = sync_library_file(Library(root))

    assert sync.added == ["Project Phoenix/03 Research"]  # Project Atlas is covered by the '*' group entry
    after = json.loads(_file_path(root).read_text(encoding="utf-8"))
    assert after["groups"][0] == written["groups"][0]  # the wildcard entry, untouched
    phoenix = after["groups"][1]
    assert {key: phoenix[key] for key in ("name", "description", "hints")} == {
        "name": "Project Phoenix",
        "description": "The Phoenix project.",
        "hints": ["phoenix"],
    }
    assert phoenix["children"][:2] == written["groups"][1]["children"]  # kept, in the user's order
    assert phoenix["children"][2] == {"name": "03 Research"}  # appended after them
    assert len(after["groups"]) == 2


def test_sync_library_file_wildcard_level_covers_every_folder(tmp_path: Path) -> None:
    """The shipped template is all '*' entries: syncing it adds nothing and leaves the file as the user has it."""

    root = _build(tmp_path / "library")
    before = _write(root, {"groups": [{"name": "*", "children": [{"name": "01 Requirements", "hints": ["spec"]}]}]})

    sync = sync_library_file(Library(root))

    assert sync.added == []
    assert _file_path(root).read_bytes() == before


def test_sync_library_file_nothing_to_add_leaves_bytes_alone(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    before = _write(
        root,
        {
            "groups": [
                {"name": "Project Phoenix", "children": [{"name": "02 Architecture"}, {"name": "01 Requirements"}]}
            ]
        },
    )

    sync = sync_library_file(Library(root))

    assert sync.added == []
    assert _file_path(root).read_bytes() == before  # hand-written layout and order survive


# endregion


# region sync_library_file: missing folders


def test_sync_library_file_missing_entry_reported_every_run_and_kept(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    before = _write(
        root,
        {
            "groups": [
                {
                    "name": "Project Phoenix",
                    "children": [{"name": "01 Requirements"}, {"name": "02 Architecture"}, {"name": "09 Gone"}],
                },
                {"name": "Old Project"},
            ]
        },
    )

    first = sync_library_file(Library(root))
    second = sync_library_file(Library(root))

    assert first.missing == ["Project Phoenix/09 Gone", "Old Project"]
    assert second.missing == first.missing
    assert _file_path(root).read_bytes() == before


def test_sync_library_file_excluded_folder_that_exists_not_missing(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    (root / "Scratch").mkdir()
    config = load_config(Path("does-not-exist"))
    config.exclusions.exclude = ["Scratch"]
    _write(root, {"groups": [{"name": "Scratch"}]})

    sync = sync_library_file(Library(root, config=config))

    assert sync.missing == []
    assert "Scratch" not in sync.added


def test_sync_library_file_wildcard_entry_never_missing(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    _write(root, {"groups": [{"name": "*", "children": [{"name": "05 Nowhere", "hints": ["x"]}]}]})

    sync = sync_library_file(Library(root))

    assert sync.missing == []


def test_sync_library_file_one_gone_one_new_is_possible_rename(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    _write(
        root,
        {
            "groups": [
                {
                    "name": "Project Phoenix",
                    "children": [{"name": "01 Requirements", "hints": ["spec"]}, {"name": "02 Architecture"}],
                }
            ]
        },
    )
    (root / "Project Phoenix" / "01 Requirements").rename(root / "Project Phoenix" / "01 Specs")

    sync = sync_library_file(Library(root))

    assert sync.missing == ["Project Phoenix/01 Requirements"]
    assert sync.possible_renames == [("Project Phoenix/01 Requirements", "Project Phoenix/01 Specs")]
    # never merged: the old entry and its hints stay, and the new one starts empty
    file = load_library_file(root / ".microfiche", depth=2)
    old, new = (child for child in file.groups[0].children if child.name != "02 Architecture")
    assert old.hints == ["spec"]
    assert new.name == "01 Specs"
    assert new.hints == []


def test_sync_library_file_several_gone_or_new_is_not_a_rename(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    _write(
        root,
        {"groups": [{"name": "Project Phoenix", "children": [{"name": "Gone One"}, {"name": "Gone Two"}]}]},
    )

    sync = sync_library_file(Library(root))

    assert len(sync.missing) == 2
    assert sync.possible_renames == []


# endregion


# region sync_library_file: failures


def test_sync_library_file_invalid_file_raises_and_is_not_overwritten(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    path = _file_path(root)
    path.parent.mkdir()
    path.write_text('{"groups": [{"name": "A", "bogus": 1}]}', encoding="utf-8")

    with pytest.raises(ConfigError):
        sync_library_file(Library(root))

    assert path.read_text(encoding="utf-8") == '{"groups": [{"name": "A", "bogus": 1}]}'


def test_sync_library_file_state_folder_unwritable_is_reported_not_raised(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    (root / ".microfiche").write_text("not a folder", encoding="utf-8")  # so nothing can be created inside it

    sync = sync_library_file(Library(root, config=load_config(Path("does-not-exist"))))

    assert sync.write_error is not None
    assert not sync.created
    assert sync.added  # what a write would have added


@pytest.mark.usefixtures("library_file_locked")
def test_sync_library_file_rename_fails_original_kept_no_leftover(tmp_path: Path) -> None:
    root = _build(tmp_path / "library")
    before = _write(root, {"groups": [{"name": "Project Phoenix"}]})

    sync = sync_library_file(Library(root))

    assert sync.write_error is not None
    assert "locked" in sync.write_error
    assert _file_path(root).read_bytes() == before
    assert list(_file_path(root).parent.glob("*.tmp")) == []


# endregion


# endregion
