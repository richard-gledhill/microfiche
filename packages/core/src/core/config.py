"""Loads microfiche's TOML configuration files into typed settings objects.

These live at ``<library_root>/.microfiche/`` for the library microfiche is managing -
not inside this repository. Dot-prefixed so it's hidden from Obsidian's or similar file explorer by
default. The ``microfiche/`` folder shipped in this repo is the set of defaults a new
library should start from, copied in as ``.microfiche/`` (see microfiche/README.md).
"""

from __future__ import annotations

import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# region Constants and types

CONFIG_FILENAME = "microfiche-config.toml"
# Per-library folder holding the config and everything microfiche writes about its own work
# (ledger, audit log, rollback jobs). Dot-prefixed so Obsidian's file explorer hides it.
MICROFICHE_DIRNAME = ".microfiche"


class _ConfigSection(BaseModel):
    """
    BaseModel class abstraction for a configuration section.
    """

    model_config = ConfigDict(extra="forbid")


class LibraryStructureConfig(_ConfigSection):
    """The shape of the library: its group/category hierarchy, and the name of its inbox.

    Attributes:
        library_inbox (str): Name of the inbox folder at the library root (default ``"_sorting"``).
            A plain folder name, not a path, and not the state folder's name.
        depth (int): Depth of the group/category hierarchy. Only 2 is implemented.
        levels (list[str]): Names of the levels. Not read by the code yet.
        file_target_level (int): The level files are filed at. Not read by the code yet.
    """

    library_inbox: str
    depth: int
    levels: list[str]
    file_target_level: int

    @field_validator("library_inbox")
    @classmethod
    def _inbox_is_a_folder_name(cls, value: str) -> str:
        if not value.strip():
            raise InvalidInboxNameError(value, "it is empty")
        if "/" in value or "\\" in value:
            raise InvalidInboxNameError(value, "it must be a single folder name, not a path")
        if value in (".", ".."):
            raise InvalidInboxNameError(value, "it must name a folder inside the library")
        if value == MICROFICHE_DIRNAME:
            raise InvalidInboxNameError(value, "that is the library's own state folder")
        return value


class ExclusionsConfig(_ConfigSection):
    """Folder name/glob patterns never treated as a category, never descended into."""

    exclude: list[str]


class ObsidianConfig(_ConfigSection):
    """Handles configuration details for Obsidian-related operations.

    This class is used to manage settings required for integration or operations
    with Obsidian, such as enabling or disabling functionality, setting paths,
    and defining modes of operation. It aids in maintaining configurable options
    to adapt behavior based on user needs or application requirements.

    Attributes:
        enabled (bool): Indicates whether the Obsidian-related functionality is
            enabled or disabled.
        tag_index_path (str): Specifies the file path for the tag index used in
            Obsidian-related operations.
        tag_mode (Literal["suggest", "strict", "off"]): Determines the mode of operation
            for handling tags. The allowed values are "suggest", "strict", or "off".
    """

    enabled: bool
    tag_index_path: str
    tag_mode: Literal["suggest", "strict", "off"]


class CategoryHintsConfig(_ConfigSection):
    """Represents the configuration for category hints.

    Keyword hints per *existing* category name, used by the rules engine - not the category
    list itself, which is discovered from the library's folders (see core.library.taxonomy).

    This class is used to define and manage a mapping between category names and their
    associated hints. The primary purpose of this configuration is to store and organize
    categories while allowing easy access to their related hints. It serves as a data
    structure for categorization-related functionality.

    Attributes:
        categories (dict[str, list[str]]): A dictionary mapping category names to a list of associated hints.
    """

    categories: dict[str, list[str]]


class FilingRulesConfig(_ConfigSection):
    """Represents the configuration for filing rules.

    Filename-glob -> category rules, checked before keyword hints.

    This class is used to define the configuration for filing rules, which are
    represented as a list of dictionaries mapping strings to strings. It provides
    a structure to easily store and access the filing rules for various applications.

    Attributes:
        rules (list[dict[str, str]]): List of filing rules, where each rule is represented
            as a dictionary mapping strings to strings.
    """

    rules: list[dict[str, str]]


class NamingRulesConfig(_ConfigSection):
    """Represents configuration for naming rules.

    This class is intended to store and manage Regex pattern naming rules defined as key-value pairs.
    These are applied to filenames before filing.
    It provides a way to structure and validate configuration data for naming conventions.

    Attributes:
        rules (dict[str, str]): A dictionary containing naming rules, where the key is the name of the
            rule and the value is its corresponding pattern or configuration.
    """

    rules: dict[str, str]


class ClassificationConfig(_ConfigSection):
    """How confident microfiche must be before it files a document without asking.

    Attributes:
        confidence_threshold (float): From 0 to 1. A document is filed automatically only if the
            weaker of its group and category confidence reaches this; otherwise it is left for
            review. Higher is stricter. Today's signal strengths are 0.9-1.0 for exact names,
            0.95 for filename rules, 0.75 for keyword hints and 0.70 for AI answers, so the
            default of 0.75 files everything except AI answers; raise it to 0.8 to hold keyword-hint
            matches for review too, or lower it to 0.7 to file AI answers.
        name_match_confidence (float): From 0 to 1. How sure a match is when a category's name
            appears in the document text.
        filename_match_confidence (float): From 0 to 1. How sure a match is when a filename rule
            applies.
        hint_match_confidence (float): From 0 to 1. How sure a match is when one of a category's
            keyword hints appears in the document text.
        fuzzy_group_threshold (int): From 0 to 100. How close a near-miss must be to a group's name
            (a ``thefuzz`` partial-ratio score) to count as that group.
    """

    confidence_threshold: float = Field(ge=0.0, le=1.0)
    name_match_confidence: float = Field(ge=0.0, le=1.0)
    filename_match_confidence: float = Field(ge=0.0, le=1.0)
    hint_match_confidence: float = Field(ge=0.0, le=1.0)
    fuzzy_group_threshold: int = Field(ge=0, le=100)


class AIConfig(_ConfigSection):
    """How the AI fallback is trusted and what it is sent.

    Attributes:
        ai_confidence (float): From 0 to 1. How sure any answer from the AI fallback is, whatever
            model gave it. Compared with ``[classification] confidence_threshold`` to decide whether
            an AI-only answer files or goes to review.
        max_document_chars (int): At least 1. How much of a document's text is sent to the AI.
    """

    ai_confidence: float = Field(ge=0.0, le=1.0)
    max_document_chars: int = Field(ge=1)


class SortingConfig(_ConfigSection):
    """How the inbox is sorted.

    Attributes:
        keep_folders (bool): Whether a folder in the inbox is filed whole, as one unit under its
            dominant category, rather than being left alone. The ``--keep-folders`` and
            ``--keep-folders-off`` options override it for one run.
    """

    keep_folders: bool


class MicroficheConfig(_ConfigSection):
    """Configuration container for Microfiche.

    Represents the configuration settings for the Microfiche system, which
    defines the structure and behavior of file management, organization, and
    categorization. This class holds detailed settings for library structure,
    file exclusions, integration with Obsidian, category hints, filing rules,
    and naming conventions.

    Attributes:
        library_structure (LibraryStructureConfig): Configuration for the library structure.
        exclusions (ExclusionsConfig): Configuration for file and folder exclusions.
        obsidian (ObsidianConfig): Configuration for Obsidian integration.
        category_hints (CategoryHintsConfig): Configuration for category hints used in
            categorizing files or folders.
        filing_rules (FilingRulesConfig): Configuration for rules dictating how files
            are organized and filed.
        naming_rules (NamingRulesConfig): Configuration for rules governing file naming.
        classification (ClassificationConfig): Configuration for how confident a
            classification must be before a document is filed automatically.
        ai (AIConfig): Configuration for the AI fallback.
        sorting (SortingConfig): Configuration for how the inbox is sorted.
        library_templates (dict[str, list[str]]): Named category sets for a future
            `create-library`/`init` command, e.g. ``software_project``. Not read by the code yet.
    """

    library_structure: LibraryStructureConfig
    exclusions: ExclusionsConfig
    obsidian: ObsidianConfig
    category_hints: CategoryHintsConfig
    filing_rules: FilingRulesConfig
    naming_rules: NamingRulesConfig
    classification: ClassificationConfig
    ai: AIConfig
    sorting: SortingConfig
    library_templates: dict[str, list[str]]


# endregion


# region Errors


class InvalidInboxNameError(ValueError):
    """Raised when ``library_inbox`` isn't a usable folder name."""

    def __init__(self, value: str, reason: str) -> None:
        self.value = value
        super().__init__(f"library_inbox {value!r} is not a valid folder name: {reason}")


class ConfigError(ValueError):
    """The library's configuration can't be used; the message says why and where."""


class TomlConfigParseError(ConfigError):
    """Exception raised when a TOML configuration file fails to parse."""

    def __init__(self, path: Path | str, error: Exception | str) -> None:
        super().__init__(f"Config file error: Failed to parse TOML configuration at {path}: {error}")
        self.path = Path(path)


# endregion


# region Public API


def load_config(config_path: Path) -> MicroficheConfig:
    """Load the library's configuration from ``config_path`` into a ``MicroficheConfig``.

    The packaged defaults (``core/defaults/microfiche-config.toml``) are read first and the library's
    file is merged over them: tables merge key by key, and a list replaces the default list. A
    missing file, section or setting therefore keeps its default. The merged result is validated, so
    a mistyped section or setting, or a value of the wrong type, is an error rather than being
    silently ignored.

    Args:
        config_path: The folder holding ``microfiche-config.toml`` (a library's ``.microfiche/``
            folder), or the path of a config file itself.

    Returns:
        The validated configuration.

    Raises:
        TomlConfigParseError: If the file is not valid TOML.
        ConfigError: If the file is valid TOML but not a valid configuration. The message names
            the file and every setting that is wrong.
    """

    target_file = config_path if config_path.is_file() else config_path / CONFIG_FILENAME

    config = _deep_merge(_load_packaged_defaults(), _load_toml(target_file))

    try:
        return MicroficheConfig.model_validate(config)
    except ValidationError as err:
        raise ConfigError(_describe_errors(target_file, err)) from err


# endregion


# region Helpers


def _load_packaged_defaults() -> dict[str, Any]:
    """Read the defaults file shipped inside the ``core`` package (``core/defaults/``)."""
    text = resources.files("core").joinpath("defaults", CONFIG_FILENAME).read_text(encoding="utf-8")
    return tomllib.loads(text)


def _deep_merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge ``overrides`` over ``defaults`` without changing either.

    Tables merge key by key; anything else, including a list, is replaced by the override. A key
    the library sets to a non-table where the defaults hold a table (or the reverse) is replaced
    too, so validation reports it instead of the merge hiding it.

    Args:
        defaults: The packaged defaults.
        overrides: What the library's file sets.

    Returns:
        A new dict holding the merged settings.
    """
    merged = dict(defaults)
    for key, value in overrides.items():
        base = merged.get(key)
        merged[key] = _deep_merge(base, value) if isinstance(base, dict) and isinstance(value, dict) else value
    return merged


def _load_toml(path: Path) -> dict[str, Any]:
    """Loads and parses a TOML file from the specified path.

    If the file does not exist or cannot be parsed due to format errors,
    appropriate handling is performed.

    Args:
        path (Path): The path to the TOML file to be loaded.

    Returns:
        dict[str, Any]: A dictionary representing the parsed TOML configuration if the file
            is valid, or an empty dictionary if the file does not exist.

    Raises:
        TomlConfigParseError: If the TOML file cannot be parsed due to a decoding error.
    """

    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as err:
        raise TomlConfigParseError(path, err) from err


def _loc_to_dot_sep(loc: tuple[str | int, ...]) -> str:
    """Join an error location into a dotted path, such as ``filing_rules.rules[0].pattern``."""
    path = ""
    for i, part in enumerate(loc):
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if i else part
    return path


def _describe_errors(target_file: Path, err: ValidationError) -> str:
    """Format pydantic validation errors as one line per problem, under the file path."""
    lines = [f"Config file error: {target_file}:"]
    for error in err.errors():
        setting = _loc_to_dot_sep(error["loc"])
        match error["type"], len(error["loc"]):
            case "extra_forbidden", 1:
                reason = "unknown section"
            case "extra_forbidden", _:
                reason = "unknown setting"
            case _:
                reason = error["msg"].removeprefix("Value error, ")
        lines.append(f"  {setting}: {reason}")
    return "\n".join(lines)


# endregion
