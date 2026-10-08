"""Tests for loading microfiche's configuration file."""

from pathlib import Path

import pytest
from core.config import (
    DEFAULT_INBOX_DIRNAME,
    CategoryHintsConfig,
    ClassificationConfig,
    ConfigError,
    ExclusionsConfig,
    FilingRulesConfig,
    LibraryStructureConfig,
    MicroficheConfig,
    NamingRulesConfig,
    ObsidianConfig,
    TomlConfigParseError,
    load_config,
)
from core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD
from core.utils.filesystem import is_excluded
from pydantic import BaseModel, ValidationError

_REPO_CONFIG_DIR = Path(__file__).resolve().parents[2] / "microfiche"

# --- config defaults ------------------------------------------------------------------------


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


def test_the_default_confidence_threshold_is_the_keyword_hint_score() -> None:
    """Set by calibration (docs/development/calibration.md): hint matches file, AI answers do not."""

    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.75


def test_the_shipped_config_uses_the_default_confidence_threshold() -> None:
    assert load_config(_REPO_CONFIG_DIR).classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_a_missing_classification_table_falls_back_to_the_default_threshold(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[library_structure]\ndepth = 2\n", encoding="utf-8")

    assert load_config(tmp_path).classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD
    assert load_config(tmp_path / "does-not-exist").classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_a_library_can_set_its_own_confidence_threshold(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[classification]\nconfidence_threshold = 0.7\n", encoding="utf-8")

    assert load_config(tmp_path).classification.confidence_threshold == 0.7


@pytest.mark.parametrize(
    "value",
    [0.0, 0.5, 1.0],
)
def test_thresholds_from_zero_to_one_are_accepted(value: float) -> None:
    assert ClassificationConfig(confidence_threshold=value).confidence_threshold == value


@pytest.mark.parametrize(
    "value",
    [-0.1, 1.01, 8],
)
def test_thresholds_outside_zero_to_one_are_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        ClassificationConfig(confidence_threshold=value)


def test_the_shipped_library_templates_are_loaded() -> None:
    config = load_config(_REPO_CONFIG_DIR)

    assert "01 Requirements" in config.library_templates["software_project"]


# --- config error checks ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "section",
    [
        LibraryStructureConfig,
        ExclusionsConfig,
        ObsidianConfig,
        CategoryHintsConfig,
        FilingRulesConfig,
        NamingRulesConfig,
        ClassificationConfig,
    ],
)
def test_each_section_rejects_unknown_key(section: type[BaseModel]) -> None:
    """A key a section doesn't define is an error, so a typo can't be silently ignored."""
    with pytest.raises(ValidationError) as exc_info:
        section(not_a_real_key=1)

    [error] = exc_info.value.errors()
    assert error["type"] == "extra_forbidden"
    assert error["loc"] == ("not_a_real_key",)


def test_a_library_template_that_is_not_a_list_of_names_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        '[library_templates]\nsoftware_project = "oops"\n', encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="software_project"):
        load_config(tmp_path)


def test_library_structure_rejects_unknown_key() -> None:
    invalid_data = {
        "library_structure": {
            "library_inbox": "_sorting",
            "depth": 2,
            "levels": ["group", "category"],
            "file_target_level": 2,
            "invalid_key": "invalid-key",  # The offender
        }
    }
    with pytest.raises(ValidationError) as exc_info:
        LibraryStructureConfig(**invalid_data.get("library_structure", {}))

    [error] = exc_info.value.errors()
    assert error["type"] == "extra_forbidden"
    assert error["loc"] == ("invalid_key",)


def test_an_unknown_section_in_config_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[classifcation]\nconfidence_threshold = 0.9\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="classifcation"):
        load_config(tmp_path)


def test_an_unknown_key_in_a_section_of_the_config_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        "[classification]\nconfidence_threshhold = 0.9\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="confidence_threshhold"):
        load_config(tmp_path)


def test_a_wrong_type_in_config_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        '[classification]\nconfidence_threshold = "high"\n', encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="confidence_threshold"):
        load_config(tmp_path)


def test_a_toml_syntax_error_in_config_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[classification\n", encoding="utf-8")

    with pytest.raises(TomlConfigParseError):
        load_config(tmp_path)


def test_a_section_that_is_not_a_table_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("classification = 5", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_a_bad_value_is_reported_with_its_file_section_and_setting(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        '[classification]\nconfidence_threshold = "high"\n', encoding="utf-8"
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(tmp_path)

    message = str(exc_info.value)
    assert "microfiche-config.toml" in message
    assert "classification" in message
    assert "confidence_threshold" in message
    assert "valid number" in message
    assert "pydantic.dev" not in message
    assert "MicroficheConfig" not in message


def test_a_mistyped_name_is_reported_as_an_unknown_section_or_setting(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        "[classification]\nconfidence_threshhold = 0.9\n\n[classifcation]\nx = 1\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(tmp_path)

    message = str(exc_info.value)
    assert "classification.confidence_threshhold: unknown setting" in message
    assert "classifcation: unknown section" in message
    assert "Extra inputs are not permitted" not in message


def test_a_section_written_as_a_plain_value_is_not_called_unknown(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("classification = 5\n", encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(tmp_path)

    message = str(exc_info.value)
    assert "classification:" in message
    assert "unknown" not in message


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
