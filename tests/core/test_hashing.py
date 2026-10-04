"""Tests for file and unit hashing."""

import hashlib
from pathlib import Path

from core.utils.hashing import file_hash, unit_hash


def _make_folder(root: Path) -> Path:
    folder = root / "project"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.txt").write_text("alpha", encoding="utf-8")
    (folder / "sub" / "b.bin").write_bytes(b"\x00\x01")
    return folder


def test_unit_hash_of_a_file_is_its_file_hash(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")

    assert unit_hash(path) == file_hash(path) == hashlib.sha256(b"hello").hexdigest()


def test_unit_hash_of_a_folder_is_stable_across_calls_and_locations(tmp_path: Path) -> None:
    first = _make_folder(tmp_path / "one")
    second = _make_folder(tmp_path / "two")

    assert unit_hash(first) == unit_hash(first)
    assert unit_hash(first) == unit_hash(second)


def test_unit_hash_of_a_folder_changes_when_a_file_is_edited(tmp_path: Path) -> None:
    folder = _make_folder(tmp_path)
    before = unit_hash(folder)

    (folder / "a.txt").write_text("changed", encoding="utf-8")

    assert unit_hash(folder) != before


def test_unit_hash_of_a_folder_changes_when_a_file_is_added(tmp_path: Path) -> None:
    folder = _make_folder(tmp_path)
    before = unit_hash(folder)

    (folder / "extra.txt").write_text("more", encoding="utf-8")

    assert unit_hash(folder) != before


def test_unit_hash_of_a_folder_changes_when_a_file_is_renamed(tmp_path: Path) -> None:
    folder = _make_folder(tmp_path)
    before = unit_hash(folder)

    (folder / "a.txt").rename(folder / "renamed.txt")

    assert unit_hash(folder) != before
