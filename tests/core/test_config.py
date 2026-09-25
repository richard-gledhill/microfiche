"""Tests for loading microfiche's YAML configuration files."""

from pathlib import Path

from core.config import load_config
from core.utils.filesystem import is_excluded

_REPO_CONFIG_DIR = Path(__file__).resolve().parents[2] / "microfiche"


def test_load_config_reads_the_shipped_default_config() -> None:
    config = load_config(_REPO_CONFIG_DIR)

    assert config.library_structure.depth == 2
    assert "sorting*" in config.exclusions.exclude
    # .microfiche-config/ and .logs/ aren't listed explicitly - the ".*" wildcard covers any
    # dot-prefixed operational folder, which is what they're renamed to (see
    # microfiche-config [exclusions]).
    assert is_excluded(Path(".logs/audit.log"), config.exclusions.exclude)
    assert config.obsidian.tag_mode == "suggest"


def test_load_config_falls_back_to_defaults_when_files_are_missing(tmp_path: Path) -> None:
    config = load_config(tmp_path / "does-not-exist")

    assert config.library_structure.depth == 2
    assert config.exclusions.exclude == []
