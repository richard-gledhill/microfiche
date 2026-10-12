"""Tests for filesystem utility helpers."""

import errno
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import LinkMaker
from core.utils.filesystem import ensure_dir, is_excluded, is_link, name_matches, safe_move


def test_is_excluded_matches_any_path_component() -> None:
    assert is_excluded(Path("library/sorting/inbox.txt"), ["sorting"])
    assert not is_excluded(Path("library/Project Phoenix/inbox.txt"), ["sorting"])


def test_is_excluded_supports_glob_patterns() -> None:
    assert is_excluded(Path("library/.obsidian/config"), [".*"])


@pytest.mark.parametrize("name", ["~$report.docx", ".DS_Store", "Thumbs.db", "scratch.tmp"])
def test_name_matches_listed_clutter(name: str) -> None:
    assert name_matches(name, ["~$*", ".DS_Store", "Thumbs.db", "*.tmp"])


def test_name_matches_ordinary_name_no_match() -> None:
    assert not name_matches("report.docx", ["~$*", ".DS_Store", "Thumbs.db", "*.tmp"])
    assert not name_matches("anything", [])


def test_is_link_regular_file_and_folder_false(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    (tmp_path / "folder").mkdir()

    assert not is_link(tmp_path / "file.txt")
    assert not is_link(tmp_path / "folder")


def test_is_link_missing_path_false(tmp_path: Path) -> None:
    assert not is_link(tmp_path / "missing")


def test_is_link_symlink_true_to_file_and_folder(tmp_path: Path, make_symlink: LinkMaker) -> None:
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    make_symlink(tmp_path / "file-link", tmp_path / "file.txt")
    make_symlink(tmp_path / "folder-link", tmp_path / "folder")

    assert is_link(tmp_path / "file-link")
    assert is_link(tmp_path / "folder-link")


def test_is_link_junction_true(tmp_path: Path, make_junction: LinkMaker) -> None:
    (tmp_path / "folder").mkdir()
    make_junction(tmp_path / "junction", tmp_path / "folder")

    assert is_link(tmp_path / "junction")
    assert not is_link(tmp_path / "folder")


def _fake_lstat(reparse_tag: int | None) -> object:
    """An lstat result for an ordinary file, carrying a Windows reparse tag when given one."""

    fields = {"st_mode": stat.S_IFREG | 0o644}
    if reparse_tag is not None:
        fields["st_reparse_tag"] = reparse_tag
    return SimpleNamespace(**fields)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        (stat.IO_REPARSE_TAG_MOUNT_POINT, True),  # a junction
        (stat.IO_REPARSE_TAG_SYMLINK, True),
        (0x9000701A, False),  # a OneDrive cloud placeholder: a reparse point, but a real file
        (0, False),
        (None, False),  # not Windows: no tag at all
    ],
)
def test_is_link_decided_by_reparse_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tag: int | None, expected: bool
) -> None:
    placeholder = tmp_path / "cloud.docx"
    placeholder.write_text("x", encoding="utf-8")
    monkeypatch.setattr(Path, "lstat", lambda self: _fake_lstat(tag))

    assert is_link(placeholder) is expected


def test_safe_move_refuses_to_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("source")
    destination = tmp_path / "dest.txt"
    destination.write_text("existing")

    with pytest.raises(FileExistsError):
        safe_move(source, destination)


def test_safe_move_creates_parent_dirs(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello")
    destination = tmp_path / "nested" / "dest.txt"

    result = safe_move(source, destination)

    assert result == destination
    assert destination.read_text() == "hello"
    assert not source.exists()


def test_safe_move_open_file_fails_cleanly_without_a_copy(tmp_path: Path, hold_open: Callable[[Path], None]) -> None:
    """A file another program has open: the move fails, and nothing is left behind (the old shutil.move left a copy)."""

    source = tmp_path / "inbox" / "report.docx"
    source.parent.mkdir()
    source.write_text("the document", encoding="utf-8")
    destination = tmp_path / "library" / "report.docx"
    hold_open(source)

    with pytest.raises(PermissionError):
        safe_move(source, destination)

    assert source.read_text(encoding="utf-8") == "the document"
    assert not destination.exists()


def test_safe_move_folder_with_open_file_fails_cleanly(tmp_path: Path, hold_open: Callable[[Path], None]) -> None:
    folder = tmp_path / "inbox" / "bundle"
    folder.mkdir(parents=True)
    (folder / "open.docx").write_text("held by Word", encoding="utf-8")
    (folder / "other.md").write_text("not held", encoding="utf-8")
    destination = tmp_path / "library" / "bundle"
    hold_open(folder / "open.docx")

    with pytest.raises(PermissionError):
        safe_move(folder, destination)

    assert sorted(path.name for path in folder.iterdir()) == ["open.docx", "other.md"]
    assert not destination.exists()  # no partial copy of the folder


def test_safe_move_failed_rename_never_falls_back_to_copying(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = tmp_path / "library" / "dest.txt"

    def refuse(self: Path, target: Path) -> Path:
        raise PermissionError(13, "in use")

    def must_not_copy(*args: object, **kwargs: object) -> None:
        pytest.fail("a failed move must not be retried as a copy")

    monkeypatch.setattr(Path, "rename", refuse)
    for name in ("move", "copy", "copy2", "copyfile", "copytree"):
        monkeypatch.setattr(shutil, name, must_not_copy)

    with pytest.raises(PermissionError):
        safe_move(source, destination)

    assert source.read_text(encoding="utf-8") == "hello"
    assert not destination.exists()


def test_safe_move_across_volumes_fails_instead_of_copying(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    destination = tmp_path / "elsewhere" / "dest.txt"

    def different_volume(self: Path, target: Path) -> Path:
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(Path, "rename", different_volume)

    with pytest.raises(OSError, match="cross-device") as raised:
        safe_move(source, destination)

    assert raised.value.errno == errno.EXDEV
    assert source.exists()
    assert not destination.exists()


def test_ensure_dir_creates_missing_directory(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b"
    assert ensure_dir(target) == target
    assert target.is_dir()
