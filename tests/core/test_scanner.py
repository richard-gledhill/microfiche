"""Tests for scanning the library's inbox into sortable units."""

from pathlib import Path

from core.library.library import Library
from core.scanner import scan_sorting_inbox


def _write(path: Path, text: str = "content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_loose_supported_files_in_the_default_inbox_become_units(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "b.md")
    _write(tmp_path / "_sorting" / "a.txt")

    units = scan_sorting_inbox(Library(tmp_path))

    assert [unit.source_path.name for unit in units] == ["a.txt", "b.md"]
    assert {unit.kind for unit in units} == {"file"}


def test_unsupported_files_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "photo.png")
    _write(tmp_path / "_sorting" / "note.md")

    assert [unit.source_path.name for unit in scan_sorting_inbox(Library(tmp_path))] == ["note.md"]


def test_a_missing_inbox_has_nothing_to_scan(tmp_path: Path) -> None:
    assert scan_sorting_inbox(Library(tmp_path)) == []


def test_the_inbox_is_the_folder_the_config_names(tmp_path: Path) -> None:
    (tmp_path / ".microfiche").mkdir()
    (tmp_path / ".microfiche" / "microfiche-config.toml").write_text(
        '[library_structure]\nlibrary_inbox = "Incoming"\n', encoding="utf-8"
    )
    _write(tmp_path / "Incoming" / "wanted.md")
    _write(tmp_path / "_sorting" / "ignored.md")

    units = scan_sorting_inbox(Library(tmp_path))

    assert [unit.source_path.name for unit in units] == ["wanted.md"]
    assert units[0].source_path.parent == tmp_path / "Incoming"


def test_a_library_still_using_the_older_sorting_folder_name_can_name_it(tmp_path: Path) -> None:
    (tmp_path / ".microfiche").mkdir()
    (tmp_path / ".microfiche" / "microfiche-config.toml").write_text(
        '[library_structure]\nlibrary_inbox = "sorting"\n', encoding="utf-8"
    )
    _write(tmp_path / "sorting" / "legacy.md")

    assert [unit.source_path.name for unit in scan_sorting_inbox(Library(tmp_path))] == ["legacy.md"]


def test_folders_are_left_alone_unless_kept_whole(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "one.md")
    _write(tmp_path / "_sorting" / "bundle" / "two.md")

    assert scan_sorting_inbox(Library(tmp_path)) == []

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True)
    assert unit.kind == "folder"
    assert unit.source_path == tmp_path / "_sorting" / "bundle"
    assert len(unit.documents) == 2


def test_a_folder_with_no_supported_files_is_not_a_unit(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "photos" / "a.png")

    assert scan_sorting_inbox(Library(tmp_path), keep_folders=True) == []


# --- files that can't be read ------------------------------------------------------------------


def _corrupt(path: Path) -> Path:
    return _write(path, "this is not a zip file")  # a .docx is a zip, so this can't be parsed


def test_an_unreadable_file_becomes_a_unit_with_no_documents_instead_of_stopping_the_scan(tmp_path: Path) -> None:
    bad = _corrupt(tmp_path / "_sorting" / "broken.docx")

    (unit,) = scan_sorting_inbox(Library(tmp_path))

    assert unit.source_path == bad
    assert unit.documents == []
    (unreadable,) = unit.unreadable
    assert unreadable.file_path == bad
    assert "PackageNotFoundError" in unreadable.reason


def test_readable_files_are_still_scanned_alongside_an_unreadable_one(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "a.md")
    _corrupt(tmp_path / "_sorting" / "b.docx")
    _write(tmp_path / "_sorting" / "c.md")

    units = scan_sorting_inbox(Library(tmp_path))

    assert [unit.source_path.name for unit in units] == ["a.md", "b.docx", "c.md"]
    assert [len(unit.documents) for unit in units] == [1, 0, 1]


def test_a_folder_keeps_its_readable_documents_and_lists_the_unreadable_ones(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    _corrupt(tmp_path / "_sorting" / "bundle" / "bad.docx")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True)

    assert [document.file_name for document in unit.documents] == ["good.md"]
    assert [u.file_path.name for u in unit.unreadable] == ["bad.docx"]


def test_a_folder_of_only_unreadable_files_is_still_a_unit(tmp_path: Path) -> None:
    _corrupt(tmp_path / "_sorting" / "bundle" / "bad.docx")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True)

    assert unit.documents == []
    assert [u.file_path.name for u in unit.unreadable] == ["bad.docx"]


def test_unsupported_files_inside_a_folder_are_neither_documents_nor_unreadable(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    _write(tmp_path / "_sorting" / "bundle" / "photo.png")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True)

    assert [document.file_name for document in unit.documents] == ["good.md"]
    assert unit.unreadable == []
