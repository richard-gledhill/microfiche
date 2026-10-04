"""Tests for loading microfiche's configuration file."""

from pathlib import Path

import pytest
from core.config import (
    DEFAULT_INBOX_DIRNAME,
    ClassificationConfig,
    MicroficheConfig,
    load_config,
)
from core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD
from core.utils.filesystem import is_excluded
from pydantic import ValidationError

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


def test_the_default_confidence_threshold_is_high() -> None:
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.8


def test_the_shipped_config_uses_the_default_confidence_threshold() -> None:
    assert load_config(_REPO_CONFIG_DIR).classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_a_missing_classification_table_falls_back_to_the_default_threshold(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[library_structure]\ndepth = 2\n", encoding="utf-8")

    assert load_config(tmp_path).classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD
    assert load_config(tmp_path / "does-not-exist").classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_a_library_can_set_its_own_confidence_threshold(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[classification]\nconfidence_threshold = 0.7\n", encoding="utf-8")

    assert load_config(tmp_path).classification.confidence_threshold == 0.7


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
def test_thresholds_from_zero_to_one_are_accepted(value: float) -> None:
    assert ClassificationConfig(confidence_threshold=value).confidence_threshold == value


@pytest.mark.parametrize("value", [-0.1, 1.01, 8])
def test_thresholds_outside_zero_to_one_are_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        ClassificationConfig(confidence_threshold=value)


# --- the library inbox ------------------------------------------------------------------------


def test_the_inbox_defaults_to_the_sorting_folder() -> None:
    assert load_config(Path("does-not-exist")).library_structure.library_inbox == DEFAULT_INBOX_DIRNAME == "_sorting"


def test_the_shipped_config_names_the_default_inbox() -> None:
    assert load_config(_REPO_CONFIG_DIR).library_structure.library_inbox == DEFAULT_INBOX_DIRNAME


def test_a_library_can_name_its_own_inbox(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        '[library_structure]\nlibrary_inbox = "Incoming"\n', encoding="utf-8"
    )

    assert load_config(tmp_path).library_structure.library_inbox == "Incoming"


@pytest.mark.parametrize("name", ["", "   ", "a/b", "a\\b", ".", "..", ".microfiche"])
def test_an_inbox_that_is_not_a_plain_folder_name_is_rejected(name: str) -> None:
    config = load_config(Path("does-not-exist")).model_dump()
    config["library_structure"]["library_inbox"] = name

    with pytest.raises(ValidationError, match="not a valid folder name"):
        MicroficheConfig.model_validate(config)
