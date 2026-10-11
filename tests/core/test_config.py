"""Tests for loading microfiche's configuration file."""

import copy
import tomllib
from pathlib import Path
from typing import Any

import pytest
from core.config import (
    AIConfig,
    ClassificationConfig,
    ConfigError,
    ExclusionsConfig,
    LibraryStructureConfig,
    MicroficheConfig,
    NamingRulesConfig,
    ObsidianConfig,
    SortingConfig,
    TomlConfigParseError,
    UnsupportedDepthError,
    load_config,
)
from core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD
from core.utils.filesystem import is_excluded
from pydantic import BaseModel, ValidationError

# region Test helpers


_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_CONFIG_DIR = _REPO_ROOT / "microfiche"
_PACKAGED_DEFAULTS = _REPO_ROOT / "packages" / "core" / "src" / "core" / "defaults" / "microfiche-config.toml"
# The one setting the template deliberately sets differently: it ships example folder patterns to leave out,
# while the packaged default excludes nothing beyond the inbox and the state folder.
_TEMPLATE_MAY_DIFFER = {"exclusions.exclude"}

_SECTIONS: list[tuple[str, type[BaseModel]]] = [
    ("library_structure", LibraryStructureConfig),
    ("exclusions", ExclusionsConfig),
    ("obsidian", ObsidianConfig),
    ("naming_rules", NamingRulesConfig),
    ("classification", ClassificationConfig),
    ("ai", AIConfig),
    ("sorting", SortingConfig),
]


def _classification(**overrides: Any) -> ClassificationConfig:
    """The packaged ``[classification]`` settings with ``overrides`` applied."""
    return ClassificationConfig(**{**_packaged_defaults()["classification"], **overrides})


def _settings_in(toml_file: Path) -> dict[str, Any]:
    """Every setting in a TOML file as ``{"section.name": value}``, read as written (nothing merged in)."""

    found: dict[str, Any] = {}
    for section, table in tomllib.loads(toml_file.read_text(encoding="utf-8")).items():
        for name, value in table.items():
            found[f"{section}.{name}"] = value
    return found


def _ai(**overrides: Any) -> AIConfig:
    """The packaged ``[ai]`` settings with ``overrides`` applied."""
    return AIConfig(**{**_packaged_defaults()["ai"], **overrides})


def _packaged_defaults() -> dict[str, Any]:
    """The packaged defaults as plain data, for building a valid section to then break."""
    return load_config(Path("does-not-exist")).model_dump()


# endregion


# region Public API


# region Defaults


def test_load_config_reads_shipped_default_config() -> None:
    config = load_config(_REPO_CONFIG_DIR)

    assert config.library_structure.depth == 2
    assert "sorting*" in config.exclusions.exclude
    # .microfiche-config/ and .logs/ aren't listed explicitly - the ".*" wildcard covers any
    # dot-prefixed operational folder, which is what they're renamed to (see
    # microfiche-config [exclusions]).
    assert is_excluded(Path(".logs/audit.log"), config.exclusions.exclude)
    assert config.obsidian.tag_mode == "suggest"


# region Template and packaged defaults


def test_template_config_lists_exactly_the_settings_the_packaged_defaults_have() -> None:
    # A setting added to the defaults but not the template would be invisible to anyone who copies the template.
    template = _settings_in(_REPO_CONFIG_DIR / "microfiche-config.toml")
    packaged = _settings_in(_PACKAGED_DEFAULTS)

    assert set(template) == set(packaged)


def test_template_config_values_equal_the_packaged_defaults_except_the_listed_ones() -> None:
    template = _settings_in(_REPO_CONFIG_DIR / "microfiche-config.toml")
    packaged = _settings_in(_PACKAGED_DEFAULTS)

    differing = {name for name in packaged if template[name] != packaged[name]}

    assert differing <= _TEMPLATE_MAY_DIFFER


def test_template_config_loads_to_the_packaged_defaults_except_the_listed_ones() -> None:
    # The same check on the validated result, so a value that parses differently is caught too.
    template = load_config(_REPO_CONFIG_DIR).model_dump()
    packaged = load_config(Path("does-not-exist")).model_dump()

    differing = {
        f"{section}.{name}"
        for section, values in packaged.items()
        for name, value in values.items()
        if template[section][name] != value
    }

    assert differing <= _TEMPLATE_MAY_DIFFER


@pytest.mark.parametrize("readme", ["README.md", "microfiche/README.md"])
def test_readme_config_table_names_every_packaged_section(readme: str) -> None:
    # These tables were the first place to drift when sections were added.
    text = (_REPO_ROOT / readme).read_text(encoding="utf-8")
    sections = {name.split(".")[0] for name in _settings_in(_PACKAGED_DEFAULTS)}

    missing = {section for section in sections if f"| `{section}` |" not in text}

    assert not missing


# endregion


def test_load_config_missing_files_fall_back_to_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "does-not-exist")

    assert config.library_structure.depth == 2
    assert config.exclusions.exclude == []


def test_load_config_missing_file_uses_packaged_defaults(tmp_path: Path) -> None:
    # The packaged file turns Obsidian off; the model's own default used to say on.
    assert load_config(tmp_path / "does-not-exist").obsidian.enabled is False


def test_load_config_partial_table_keeps_other_defaults(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text('[obsidian]\ntag_mode = "strict"\n', encoding="utf-8")

    config = load_config(tmp_path)

    assert config.obsidian.tag_mode == "strict"
    # Not mentioned in the library's table, so it comes from the packaged defaults.
    assert config.obsidian.enabled is False
    assert config.obsidian.tag_index_path == "TagIndex.md"


def test_load_config_library_value_overrides_default(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[obsidian]\nenabled = true\n", encoding="utf-8")

    assert load_config(tmp_path).obsidian.enabled is True


def _with_packaged_defaults(monkeypatch: pytest.MonkeyPatch, **sections: dict[str, Any]) -> None:
    """Make ``load_config`` start from the real packaged defaults with ``sections`` merged in."""

    defaults = load_config(Path("does-not-exist")).model_dump()
    for name, values in sections.items():
        defaults[name] = {**defaults[name], **values}
    monkeypatch.setattr("core.config._load_packaged_defaults", lambda: defaults)


def test_load_config_list_replaces_default_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Replacing gives exactly the library's list; appending would give three entries.
    _with_packaged_defaults(monkeypatch, exclusions={"exclude": ["x", "y"]})
    (tmp_path / "microfiche-config.toml").write_text('[exclusions]\nexclude = ["z"]\n', encoding="utf-8")

    assert load_config(tmp_path).exclusions.exclude == ["z"]


def test_load_config_nested_table_merges_with_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_packaged_defaults(monkeypatch, naming_rules={"rules": {"a": "1"}})
    (tmp_path / "microfiche-config.toml").write_text('[naming_rules.rules]\nb = "2"\n', encoding="utf-8")

    config = load_config(tmp_path)

    assert config.naming_rules.rules == {"a": "1", "b": "2"}
    assert config.obsidian.enabled is False


def test_default_confidence_threshold_equals_keyword_hint_score() -> None:
    """Set by calibration (docs/development/calibration.md): hint matches file, AI answers do not."""

    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.75


def test_shipped_config_uses_default_confidence_threshold() -> None:
    assert load_config(_REPO_CONFIG_DIR).classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_load_config_no_classification_default_threshold(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[library_structure]\ndepth = 2\n", encoding="utf-8")

    assert load_config(tmp_path).classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD
    assert load_config(tmp_path / "does-not-exist").classification.confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD


def test_load_config_custom_confidence_threshold(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[classification]\nconfidence_threshold = 0.7\n", encoding="utf-8")

    assert load_config(tmp_path).classification.confidence_threshold == 0.7


@pytest.mark.parametrize(
    "value",
    [0.0, 0.5, 1.0],
)
def test_classification_config_threshold_in_range_accepted(value: float) -> None:
    assert _classification(confidence_threshold=value).confidence_threshold == value


@pytest.mark.parametrize(
    "value",
    [-0.1, 1.01, 8],
)
def test_classification_config_threshold_out_of_range_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        _classification(confidence_threshold=value)


@pytest.mark.parametrize("section", [model for _, model in _SECTIONS] + [MicroficheConfig])
def test_config_section_no_defaults_of_its_own(section: type[BaseModel]) -> None:
    """Defaults live only in the packaged file, so a section built without them is missing everything."""
    with pytest.raises(ValidationError) as exc_info:
        section()

    assert {error["type"] for error in exc_info.value.errors()} == {"missing"}


def test_load_config_signal_strengths_default_to_todays_values() -> None:
    settings = load_config(Path("does-not-exist")).classification

    assert settings.name_match_confidence == 0.9
    assert settings.filename_match_confidence == 0.95
    assert settings.hint_match_confidence == 0.75
    assert settings.fuzzy_group_threshold == 85


def test_load_config_ai_settings_default_to_todays_values() -> None:
    settings = load_config(Path("does-not-exist")).ai

    assert settings.ai_confidence == 0.70
    assert settings.max_document_chars == 4000


def test_load_config_custom_signal_strength(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        "[classification]\nhint_match_confidence = 0.6\n", encoding="utf-8"
    )

    settings = load_config(tmp_path).classification

    assert settings.hint_match_confidence == 0.6
    # Not mentioned, so the packaged default stands.
    assert settings.name_match_confidence == 0.9


def test_load_config_custom_ai_settings(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[ai]\nmax_document_chars = 100\n", encoding="utf-8")

    settings = load_config(tmp_path).ai

    assert settings.max_document_chars == 100
    assert settings.ai_confidence == 0.70


@pytest.mark.parametrize("name", ["name_match_confidence", "filename_match_confidence", "hint_match_confidence"])
@pytest.mark.parametrize("value", [-0.1, 1.01])
def test_classification_config_score_out_of_range_rejected(name: str, value: float) -> None:
    with pytest.raises(ValidationError, match=name):
        _classification(**{name: value})


@pytest.mark.parametrize("value", [-1, 101])
def test_classification_config_fuzzy_threshold_out_of_range_rejected(value: int) -> None:
    with pytest.raises(ValidationError, match="fuzzy_group_threshold"):
        _classification(fuzzy_group_threshold=value)


@pytest.mark.parametrize("value", [-0.1, 1.01])
def test_ai_config_confidence_out_of_range_rejected(value: float) -> None:
    with pytest.raises(ValidationError, match="ai_confidence"):
        _ai(ai_confidence=value)


def test_ai_config_max_document_chars_zero_means_unlimited_accepted() -> None:
    assert _ai(max_document_chars=0).max_document_chars == 0


def test_ai_config_max_document_chars_negative_rejected() -> None:
    with pytest.raises(ValidationError, match="max_document_chars"):
        _ai(max_document_chars=-1)


def test_load_config_ai_provider_settings_default_to_local_ollama() -> None:
    settings = load_config(Path("does-not-exist")).ai

    assert settings.provider == "ollama"
    assert settings.model == ""  # empty means the provider's own default model
    assert settings.host == ""  # empty means Ollama's default address
    assert settings.timeout == 120
    assert settings.api_key_env == "OPENAI_API_KEY"


def test_load_config_ai_provider_openai_chosen_in_library_config(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text('[ai]\nprovider = "openai"\n', encoding="utf-8")

    assert load_config(tmp_path).ai.provider == "openai"


def test_load_config_ai_unknown_provider_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text('[ai]\nprovider = "bedrock"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match=r"ai\.provider"):
        load_config(tmp_path)


@pytest.mark.parametrize("value", [0, -5])
def test_ai_config_timeout_not_positive_rejected(value: float) -> None:
    with pytest.raises(ValidationError, match="timeout"):
        _ai(timeout=value)


def test_ai_config_host_with_openai_rejected() -> None:
    with pytest.raises(ValidationError, match="host"):
        _ai(provider="openai", host="http://localhost:11434")


def test_ai_config_host_with_ollama_accepted() -> None:
    assert _ai(host="http://gpu-box:11434").host == "http://gpu-box:11434"


@pytest.mark.parametrize("value", ["sk-abc123", "has space", "", "1ABC", "KEY="])
def test_ai_config_api_key_env_not_a_variable_name_rejected(value: str) -> None:
    # A real key pasted here would end up in the library's config file, so it is refused.
    with pytest.raises(ValidationError, match="environment variable"):
        _ai(api_key_env=value)


def test_load_config_keep_folders_defaults_on() -> None:
    assert load_config(Path("does-not-exist")).sorting.keep_folders is True


def test_load_config_keep_folders_off_in_library_config(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[sorting]\nkeep_folders = false\n", encoding="utf-8")

    assert load_config(tmp_path).sorting.keep_folders is False


def test_load_config_keep_folders_not_a_boolean_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text('[sorting]\nkeep_folders = "perhaps"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match=r"sorting.keep_folders"):
        load_config(tmp_path)


# endregion


# region Error reporting


@pytest.mark.parametrize(("name", "section"), _SECTIONS)
def test_config_section_unknown_key_rejected(name: str, section: type[BaseModel]) -> None:
    """A key a section doesn't define is an error, so a typo can't be silently ignored."""
    with pytest.raises(ValidationError) as exc_info:
        section(**_packaged_defaults()[name], not_a_real_key=1)

    [error] = exc_info.value.errors()
    assert error["type"] == "extra_forbidden"
    assert error["loc"] == ("not_a_real_key",)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('[category_hints.categories]\n"A" = ["x"]\n', "category_hints: unknown section"),
        ("[filing_rules]\nrules = []\n", "filing_rules: unknown section"),
        ('[library_templates]\nsoftware = ["A"]\n', "library_templates: unknown section"),
        ('[library_structure]\nlevels = ["group"]\n', "library_structure.levels: unknown setting"),
        ("[library_structure]\nfile_target_level = 2\n", "library_structure.file_target_level: unknown setting"),
    ],
)
def test_load_config_settings_moved_or_removed_rejected(tmp_path: Path, text: str, expected: str) -> None:
    # Hints and rules moved to microfiche-library.json; the others had no effect and were dropped.
    (tmp_path / "microfiche-config.toml").write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError, match=expected):
        load_config(tmp_path)


def test_library_structure_unknown_key_rejected() -> None:
    invalid_data = {
        "library_structure": {
            "library_inbox": "_sorting",
            "depth": 2,
            "invalid_key": "invalid-key",  # The offender
        }
    }
    with pytest.raises(ValidationError) as exc_info:
        LibraryStructureConfig(**invalid_data.get("library_structure", {}))

    [error] = exc_info.value.errors()
    assert error["type"] == "extra_forbidden"
    assert error["loc"] == ("invalid_key",)


def test_load_config_unknown_section_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[classifcation]\nconfidence_threshold = 0.9\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="classifcation"):
        load_config(tmp_path)


def test_load_config_unknown_key_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        "[classification]\nconfidence_threshhold = 0.9\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="confidence_threshhold"):
        load_config(tmp_path)


def test_load_config_wrong_type_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        '[classification]\nconfidence_threshold = "high"\n', encoding="utf-8"
    )

    with pytest.raises(ConfigError, match="confidence_threshold"):
        load_config(tmp_path)


def test_load_config_toml_syntax_error_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[classification\n", encoding="utf-8")

    with pytest.raises(TomlConfigParseError):
        load_config(tmp_path)


def test_load_config_non_table_section_rejected(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("classification = 5", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_load_config_bad_value_reports_file_section_setting(tmp_path: Path) -> None:
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


def test_load_config_mistyped_name_reported_as_unknown(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        "[classification]\nconfidence_threshhold = 0.9\n\n[classifcation]\nx = 1\n", encoding="utf-8"
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(tmp_path)

    message = str(exc_info.value)
    assert "classification.confidence_threshhold: unknown setting" in message
    assert "classifcation: unknown section" in message
    assert "Extra inputs are not permitted" not in message


def test_load_config_plain_value_section_not_called_unknown(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("classification = 5\n", encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(tmp_path)

    message = str(exc_info.value)
    assert "classification:" in message
    assert "unknown" not in message


def test_load_config_bad_list_value_located_by_index(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text('[exclusions]\nexclude = ["a", 1]\n', encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(tmp_path)

    assert "exclusions.exclude[1]" in str(exc_info.value)


# region Depth


def test_load_config_depth_two_accepted(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text("[library_structure]\ndepth = 2\n", encoding="utf-8")

    assert load_config(tmp_path).library_structure.depth == 2


@pytest.mark.parametrize("depth", [0, 1, 3, 4])
def test_load_config_depth_not_supported_yet_rejected(tmp_path: Path, depth: int) -> None:
    (tmp_path / "microfiche-config.toml").write_text(f"[library_structure]\ndepth = {depth}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=f"library_structure.depth: depth {depth} is not supported") as exc_info:
        load_config(tmp_path)

    assert "group and category" in str(exc_info.value)


def test_unsupported_depth_error_names_the_supported_depths() -> None:
    assert str(UnsupportedDepthError(1)).endswith("only 2 is supported")


# endregion


# endregion


# region Library inbox


def test_library_inbox_defaults_to_sorting_folder() -> None:
    assert load_config(Path("does-not-exist")).library_structure.library_inbox == "_sorting"


def test_shipped_config_names_default_inbox() -> None:
    assert load_config(_REPO_CONFIG_DIR).library_structure.library_inbox == "_sorting"


def test_load_config_custom_inbox_name(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        '[library_structure]\nlibrary_inbox = "Incoming"\n', encoding="utf-8"
    )

    assert load_config(tmp_path).library_structure.library_inbox == "Incoming"


@pytest.mark.parametrize("name", ["", "   ", "a/b", "a\\b", ".", "..", ".microfiche"])
def test_library_inbox_non_folder_name_rejected(name: str) -> None:
    config = load_config(Path("does-not-exist")).model_dump()
    config["library_structure"]["library_inbox"] = name

    with pytest.raises(ValidationError, match="not a valid folder name"):
        MicroficheConfig.model_validate(config)


def test_load_config_accepts_file_path(tmp_path: Path) -> None:
    config_file = tmp_path / "custom.toml"
    config_file.write_text("[classification]\nconfidence_threshold = 0.7\n", encoding="utf-8")

    assert load_config(config_file).classification.confidence_threshold == 0.7


def test_config_error_survives_copy(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text(
        '[classification]\nconfidence_threshold = "high"\n', encoding="utf-8"
    )

    with pytest.raises(ConfigError) as exc_info:
        load_config(tmp_path)

    assert str(copy.copy(exc_info.value)) == str(exc_info.value)


def test_load_config_rejected_inbox_omits_pydantic_prefix(tmp_path: Path) -> None:
    (tmp_path / "microfiche-config.toml").write_text('[library_structure]\nlibrary_inbox = "a/b"\n', encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(tmp_path)

    assert "library_structure.library_inbox" in str(exc_info.value)
    assert "Value error" not in str(exc_info.value)


# endregion


# endregion
