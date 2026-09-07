"""Tests for filesystem utility helpers."""

from pathlib import Path

import pytest
from core.utils.filesystem import ensure_dir, is_excluded, safe_move


def test_is_excluded_matches_any_path_component() -> None:
    assert is_excluded(Path("library/sorting/inbox.txt"), ["sorting"])
    assert not is_excluded(Path("library/Project Phoenix/inbox.txt"), ["sorting"])


def test_is_excluded_supports_glob_patterns() -> None:
    assert is_excluded(Path("library/.obsidian/config"), [".*"])


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


def test_ensure_dir_creates_missing_directory(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b"
    assert ensure_dir(target) == target
    assert target.is_dir()
