"""Tests for scanning the library's inbox into sortable units."""

import logging
from pathlib import Path

import pytest
from conftest import LinkMaker
from microfiche.core.library.library import Library
from microfiche.core.scanner import scan_sorting_inbox, snapshot_inbox

# region Test helpers


def _write(path: Path, text: str = "content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# endregion


# region Scanning the inbox


def test_scan_sorting_inbox_loose_files_become_units(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "b.md")
    _write(tmp_path / "_sorting" / "a.txt")

    units = scan_sorting_inbox(Library(tmp_path)).units

    assert [unit.source_path.name for unit in units] == ["a.txt", "b.md"]
    assert {unit.kind for unit in units} == {"file"}


def test_scan_sorting_inbox_skips_unsupported_files(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "photo.png")
    _write(tmp_path / "_sorting" / "note.md")

    assert [unit.source_path.name for unit in scan_sorting_inbox(Library(tmp_path)).units] == ["note.md"]


def test_scan_sorting_inbox_missing_inbox_empty(tmp_path: Path) -> None:
    assert scan_sorting_inbox(Library(tmp_path)).units == []


def test_scan_sorting_inbox_uses_configured_inbox(tmp_path: Path) -> None:
    (tmp_path / ".microfiche").mkdir()
    (tmp_path / ".microfiche" / "microfiche-config.toml").write_text(
        '[library_structure]\nlibrary_inbox = "Incoming"\n', encoding="utf-8"
    )
    _write(tmp_path / "Incoming" / "wanted.md")
    _write(tmp_path / "_sorting" / "ignored.md")

    units = scan_sorting_inbox(Library(tmp_path)).units

    assert [unit.source_path.name for unit in units] == ["wanted.md"]
    assert units[0].source_path.parent == tmp_path / "Incoming"


def test_scan_sorting_inbox_accepts_older_sorting_folder_name(tmp_path: Path) -> None:
    (tmp_path / ".microfiche").mkdir()
    (tmp_path / ".microfiche" / "microfiche-config.toml").write_text(
        '[library_structure]\nlibrary_inbox = "sorting"\n', encoding="utf-8"
    )
    _write(tmp_path / "sorting" / "legacy.md")

    assert [unit.source_path.name for unit in scan_sorting_inbox(Library(tmp_path)).units] == ["legacy.md"]


def test_scan_sorting_inbox_folder_is_one_unit_only_when_kept_whole(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "one.md")
    _write(tmp_path / "_sorting" / "bundle" / "two.md")

    separate = scan_sorting_inbox(Library(tmp_path), keep_folders=False).units
    assert [unit.source_path.name for unit in separate] == ["one.md", "two.md"]
    assert {unit.kind for unit in separate} == {"file"}

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True).units
    assert unit.kind == "folder"
    assert unit.source_path == tmp_path / "_sorting" / "bundle"
    assert len(unit.documents) == 2


def test_scan_sorting_inbox_unsupported_only_folder_not_unit(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "photos" / "a.png")

    assert scan_sorting_inbox(Library(tmp_path), keep_folders=True).units == []
    assert scan_sorting_inbox(Library(tmp_path), keep_folders=False).units == []


def test_scan_sorting_inbox_folders_off_records_origin_folder(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "loose.md")
    _write(tmp_path / "_sorting" / "bundle" / "top.md")
    _write(tmp_path / "_sorting" / "bundle" / "nested" / "deep.md")  # still comes from the top-level folder

    units = {unit.source_path.name: unit for unit in scan_sorting_inbox(Library(tmp_path), keep_folders=False).units}

    assert set(units) == {"loose.md", "top.md", "deep.md"}
    assert units["loose.md"].origin_folder is None
    assert units["top.md"].origin_folder == tmp_path / "_sorting" / "bundle"
    assert units["deep.md"].origin_folder == tmp_path / "_sorting" / "bundle"


def test_scan_sorting_inbox_folders_off_skips_unsupported_files_inside(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    _write(tmp_path / "_sorting" / "bundle" / "photo.png")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=False).units

    assert unit.source_path.name == "good.md"


def test_scan_sorting_inbox_folders_kept_whole_have_no_origin_folder(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "one.md")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True).units

    assert unit.origin_folder is None


# endregion


# region Files that can't be read


def _corrupt(path: Path) -> Path:
    return _write(path, "this is not a zip file")  # a .docx is a zip, so this can't be parsed


def test_scan_sorting_inbox_unreadable_file_becomes_empty_unit(tmp_path: Path) -> None:
    bad = _corrupt(tmp_path / "_sorting" / "broken.docx")

    (unit,) = scan_sorting_inbox(Library(tmp_path)).units

    assert unit.source_path == bad
    assert unit.documents == []
    (unreadable,) = unit.unreadable
    assert unreadable.file_path == bad
    assert "PackageNotFoundError" in unreadable.reason


def test_scan_sorting_inbox_readable_scanned_beside_unreadable(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "a.md")
    _corrupt(tmp_path / "_sorting" / "b.docx")
    _write(tmp_path / "_sorting" / "c.md")

    units = scan_sorting_inbox(Library(tmp_path)).units

    assert [unit.source_path.name for unit in units] == ["a.md", "b.docx", "c.md"]
    assert [len(unit.documents) for unit in units] == [1, 0, 1]


def test_scan_sorting_inbox_folder_splits_readable_unreadable(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    _corrupt(tmp_path / "_sorting" / "bundle" / "bad.docx")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True).units

    assert [document.file_name for document in unit.documents] == ["good.md"]
    assert [u.file_path.name for u in unit.unreadable] == ["bad.docx"]


def test_scan_sorting_inbox_folders_off_unreadable_file_still_unit(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    bad = _corrupt(tmp_path / "_sorting" / "bundle" / "bad.docx")

    units = {unit.source_path.name: unit for unit in scan_sorting_inbox(Library(tmp_path), keep_folders=False).units}

    assert units["bad.docx"].documents == []
    assert [u.file_path for u in units["bad.docx"].unreadable] == [bad]
    assert units["bad.docx"].origin_folder == tmp_path / "_sorting" / "bundle"


def test_scan_sorting_inbox_all_unreadable_folder_still_unit(tmp_path: Path) -> None:
    _corrupt(tmp_path / "_sorting" / "bundle" / "bad.docx")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True).units

    assert unit.documents == []
    assert [u.file_path.name for u in unit.unreadable] == ["bad.docx"]


def _set_keep_folders(library: Path, value: bool) -> None:
    (library / ".microfiche").mkdir(exist_ok=True)
    (library / ".microfiche" / "microfiche-config.toml").write_text(
        f"[sorting]\nkeep_folders = {str(value).lower()}\n", encoding="utf-8"
    )


def test_scan_sorting_inbox_keep_folders_defaults_to_library_setting_on(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")

    (unit,) = scan_sorting_inbox(Library(tmp_path)).units

    assert unit.kind == "folder"


def test_scan_sorting_inbox_keep_folders_off_in_library_config_splits_folders(tmp_path: Path) -> None:
    _set_keep_folders(tmp_path, False)
    _write(tmp_path / "_sorting" / "bundle" / "good.md")

    (unit,) = scan_sorting_inbox(Library(tmp_path)).units

    assert unit.kind == "file"
    assert unit.origin_folder == tmp_path / "_sorting" / "bundle"


def test_scan_sorting_inbox_keep_folders_argument_overrides_library_setting(tmp_path: Path) -> None:
    _set_keep_folders(tmp_path, False)
    _write(tmp_path / "_sorting" / "bundle" / "good.md")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True).units

    assert unit.kind == "folder"


def test_scan_sorting_inbox_folder_unsupported_files_ignored(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    _write(tmp_path / "_sorting" / "bundle" / "photo.png")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True).units

    assert [document.file_name for document in unit.documents] == ["good.md"]
    assert unit.unreadable == []


# endregion


# region Names that are skipped


def _set_config(library: Path, text: str) -> None:
    (library / ".microfiche").mkdir(exist_ok=True)
    (library / ".microfiche" / "microfiche-config.toml").write_text(text, encoding="utf-8")


def test_scan_sorting_inbox_ignored_names_skipped_silently(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "~$report.docx")  # an Office lock file
    _write(tmp_path / "_sorting" / "scratch.tmp")
    _write(tmp_path / "_sorting" / "Thumbs.db")
    _write(tmp_path / "_sorting" / "real.md")

    scan = scan_sorting_inbox(Library(tmp_path))

    assert [unit.source_path.name for unit in scan.units] == ["real.md"]
    assert scan.skipped_links == []


def test_scan_sorting_inbox_ignored_name_inside_folder_not_read(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    _write(tmp_path / "_sorting" / "bundle" / "~$lock.docx")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True).units

    assert [document.file_name for document in unit.documents] == ["good.md"]
    assert unit.unreadable == []  # the lock file is not reported as a corrupt .docx


def test_scan_sorting_inbox_ignored_folder_not_descended_into(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    _write(tmp_path / "_sorting" / "bundle" / "cache.tmp" / "hidden.md")  # a folder named like an ignored pattern
    _write(tmp_path / "_sorting" / "scratch.tmp" / "also-hidden.md")

    units = scan_sorting_inbox(Library(tmp_path), keep_folders=False).units

    assert [unit.source_path.name for unit in units] == ["good.md"]


def test_scan_sorting_inbox_ignore_setting_replaces_default_list(tmp_path: Path) -> None:
    _set_config(tmp_path, '[sorting]\nignore = ["*.bak"]\n')
    _write(tmp_path / "_sorting" / "old.bak")
    _write(tmp_path / "_sorting" / "~$report.docx")  # no longer ignored, so it is read, and is not a real .docx

    units = scan_sorting_inbox(Library(tmp_path)).units

    assert [unit.source_path.name for unit in units] == ["~$report.docx"]
    assert units[0].unreadable


# endregion


# region Links

# A link is never followed, read or filed; the user is told about it.


def test_scan_sorting_inbox_symlink_skipped_and_listed(tmp_path: Path, make_symlink: LinkMaker) -> None:
    outside = _write(tmp_path / "elsewhere" / "outside.md")
    _write(tmp_path / "_sorting" / "real.md")
    make_symlink(tmp_path / "_sorting" / "linked.md", outside)

    scan = scan_sorting_inbox(Library(tmp_path))

    assert [unit.source_path.name for unit in scan.units] == ["real.md"]
    assert scan.skipped_links == [tmp_path / "_sorting" / "linked.md"]


def test_scan_sorting_inbox_symlinked_folder_not_followed(tmp_path: Path, make_symlink: LinkMaker) -> None:
    _write(tmp_path / "elsewhere" / "outside.md")
    (tmp_path / "_sorting").mkdir()
    make_symlink(tmp_path / "_sorting" / "linked-folder", tmp_path / "elsewhere")

    scan = scan_sorting_inbox(Library(tmp_path))

    assert scan.units == []
    assert scan.skipped_links == [tmp_path / "_sorting" / "linked-folder"]


def test_scan_sorting_inbox_junction_skipped_and_listed(tmp_path: Path, make_junction: LinkMaker) -> None:
    _write(tmp_path / "elsewhere" / "outside.md")
    (tmp_path / "_sorting").mkdir()
    make_junction(tmp_path / "_sorting" / "junction", tmp_path / "elsewhere")

    scan = scan_sorting_inbox(Library(tmp_path))

    assert scan.units == []
    assert scan.skipped_links == [tmp_path / "_sorting" / "junction"]


def test_scan_sorting_inbox_junction_inside_folder_not_followed(tmp_path: Path, make_junction: LinkMaker) -> None:
    _write(tmp_path / "elsewhere" / "outside.md")
    _write(tmp_path / "_sorting" / "bundle" / "good.md")
    make_junction(tmp_path / "_sorting" / "bundle" / "junction", tmp_path / "elsewhere")

    scan = scan_sorting_inbox(Library(tmp_path), keep_folders=False)

    assert [unit.source_path.name for unit in scan.units] == ["good.md"]
    assert scan.skipped_links == [tmp_path / "_sorting" / "bundle" / "junction"]


def test_scan_sorting_inbox_no_links_nothing_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "_sorting" / "a.md")
    _write(tmp_path / "_sorting" / "bundle" / "b.md")

    assert scan_sorting_inbox(Library(tmp_path)).skipped_links == []


# endregion


# region Files that are too big


def test_scan_sorting_inbox_oversize_file_becomes_unreadable_unit(tmp_path: Path) -> None:
    _set_config(tmp_path, "[parsing]\nmax_file_mb = 1\n")
    big = tmp_path / "_sorting" / "big.txt"
    big.parent.mkdir()
    big.write_bytes(b"x" * 2 * 1024 * 1024)
    _write(tmp_path / "_sorting" / "small.md")

    units = {unit.source_path.name: unit for unit in scan_sorting_inbox(Library(tmp_path)).units}

    assert units["big.txt"].documents == []
    (unreadable,) = units["big.txt"].unreadable
    assert unreadable.reason == "it is 2.0 MB, over the 1 MB limit ([parsing] max_file_mb)"
    assert units["small.md"].documents  # the rest of the inbox is read as usual


def test_scan_sorting_inbox_oversize_file_inside_folder_listed_unreadable(tmp_path: Path) -> None:
    _set_config(tmp_path, "[parsing]\nmax_file_mb = 1\n")
    big = tmp_path / "_sorting" / "bundle" / "big.txt"
    big.parent.mkdir(parents=True)
    big.write_bytes(b"x" * 2 * 1024 * 1024)
    _write(tmp_path / "_sorting" / "bundle" / "good.md")

    (unit,) = scan_sorting_inbox(Library(tmp_path), keep_folders=True).units

    assert [document.file_name for document in unit.documents] == ["good.md"]
    assert [u.file_path.name for u in unit.unreadable] == ["big.txt"]


# endregion


# region Logging


def test_scan_sorting_inbox_logs_counts(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _write(tmp_path / "_sorting" / "a.md")
    _write(tmp_path / "_sorting" / "b.md")
    caplog.set_level(logging.INFO, logger="microfiche.core")

    scan_sorting_inbox(Library(tmp_path))

    assert "scanned _sorting: 2 unit(s) to classify, 0 link(s) skipped" in caplog.messages


def test_scan_sorting_inbox_logs_skipped_link(
    tmp_path: Path, make_symlink: LinkMaker, caplog: pytest.LogCaptureFixture
) -> None:
    outside = _write(tmp_path / "elsewhere" / "outside.md")
    _write(tmp_path / "_sorting" / "real.md")
    make_symlink(tmp_path / "_sorting" / "linked.md", outside)
    caplog.set_level(logging.INFO, logger="microfiche.core")

    scan_sorting_inbox(Library(tmp_path))

    assert "skipped link linked.md: links are never followed" in caplog.messages
    assert "scanned _sorting: 1 unit(s) to classify, 1 link(s) skipped" in caplog.messages


def test_scan_sorting_inbox_logs_ignored_name_at_debug(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _write(tmp_path / "_sorting" / "~$draft.docx")
    caplog.set_level(logging.DEBUG, logger="microfiche.core")

    scan_sorting_inbox(Library(tmp_path))

    assert "ignored ~$draft.docx: it matches [sorting] ignore" in caplog.messages


def test_scan_sorting_inbox_info_level_leaves_out_ignored_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write(tmp_path / "_sorting" / "~$draft.docx")
    caplog.set_level(logging.INFO, logger="microfiche.core")

    scan_sorting_inbox(Library(tmp_path))

    assert not any("ignored" in message for message in caplog.messages)


def test_scan_sorting_inbox_missing_inbox_logs_it(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="microfiche.core")

    scan_sorting_inbox(Library(tmp_path))

    assert "inbox _sorting does not exist; nothing to scan" in caplog.messages


# endregion


# region Scanning only some entries


def test_scan_sorting_inbox_only_scans_the_named_entries(tmp_path: Path) -> None:
    wanted = _write(tmp_path / "_sorting" / "a.md")
    _write(tmp_path / "_sorting" / "b.md")
    _write(tmp_path / "_sorting" / "pack" / "c.md")

    units = scan_sorting_inbox(Library(tmp_path), only=[wanted]).units

    assert [unit.source_path.name for unit in units] == ["a.md"]


def test_scan_sorting_inbox_only_leaves_other_entries_unread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wanted = _write(tmp_path / "_sorting" / "a.md")
    _write(tmp_path / "_sorting" / "b.md")
    read: list[str] = []
    original = Path.read_text

    def spy(self: Path, *args: object, **kwargs: object) -> str:
        read.append(self.name)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)

    scan_sorting_inbox(Library(tmp_path), only=[wanted])

    assert "b.md" not in read


# endregion


# region snapshot_inbox


def test_snapshot_inbox_lists_files_and_folders_with_signatures(tmp_path: Path) -> None:
    note = _write(tmp_path / "_sorting" / "a.md", "hello")
    inside = _write(tmp_path / "_sorting" / "pack" / "deep" / "b.txt", "x")

    snapshot = snapshot_inbox(Library(tmp_path))

    assert list(snapshot) == [note, tmp_path / "_sorting" / "pack"]
    assert snapshot[note] == (("a.md", 5, note.stat().st_mtime_ns),)
    assert snapshot[tmp_path / "_sorting" / "pack"] == (("deep/b.txt", 1, inside.stat().st_mtime_ns),)


def test_snapshot_inbox_skips_what_the_scan_skips(tmp_path: Path, make_symlink: LinkMaker) -> None:
    kept = _write(tmp_path / "_sorting" / "kept.md")
    _write(tmp_path / "_sorting" / "photo.png")  # no parser
    _write(tmp_path / "_sorting" / "~$lock.docx")  # ignored name
    _write(tmp_path / "_sorting" / "empty-ish" / "photo.png")  # a folder with no supported file
    target = _write(tmp_path / "elsewhere" / "linked.md")
    make_symlink(tmp_path / "_sorting" / "link.md", target)

    assert list(snapshot_inbox(Library(tmp_path))) == [kept]


def test_snapshot_inbox_signature_changes_when_a_file_inside_a_folder_changes(tmp_path: Path) -> None:
    folder = tmp_path / "_sorting" / "pack"
    note = _write(folder / "a.md", "one")
    before = snapshot_inbox(Library(tmp_path))[folder]

    note.write_text("longer text", encoding="utf-8")

    assert snapshot_inbox(Library(tmp_path))[folder] != before


def test_snapshot_inbox_never_reads_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "_sorting" / "a.md")
    library = Library(tmp_path)
    _ = library.config  # loaded lazily, by reading the packaged defaults: not what is being tested

    def refuse(*_args: object, **_kwargs: object) -> None:
        pytest.fail("the snapshot must not open files")

    monkeypatch.setattr(Path, "open", refuse)
    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "read_bytes", refuse)

    assert len(snapshot_inbox(library)) == 1


def test_snapshot_inbox_missing_inbox_empty(tmp_path: Path) -> None:
    assert snapshot_inbox(Library(tmp_path)) == {}


# endregion
