"""Loads microfiche's TOML configuration files into typed settings objects.

These live at ``<library_root>/.microfiche/`` for the library microfiche is managing -
not inside this repository. Dot-prefixed so it's hidden from Obsidian's or similar file explorer by
default. The ``microfiche/`` folder shipped in this repo is the set of defaults a new
library should start from, copied in as ``.microfiche/`` (see microfiche/README.md).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from core.rules.confidence import DEFAULT_CONFIDENCE_THRESHOLD

CONFIG_FILENAME = "microfiche-config.toml"
# Per-library folder holding the config and everything microfiche writes about its own work
# (ledger, audit log, rollback jobs). Dot-prefixed so Obsidian's file explorer hides it.
MICROFICHE_DIRNAME = ".microfiche"
# Default name of the library's inbox: the one folder new documents are dropped into.
DEFAULT_INBOX_DIRNAME = "_sorting"


class InvalidInboxNameError(ValueError):
    """Raised when ``library_inbox`` isn't a usable folder name."""

    def __init__(self, value: str, reason: str) -> None:
        self.value = value
        super().__init__(f"library_inbox {value!r} is not a valid folder name: {reason}")


class LibraryStructureConfig(BaseModel):
    """The shape of the library: its group/category hierarchy, and the name of its inbox.

    Attributes:
        library_inbox (str): Name of the inbox folder at the library root (default ``"_sorting"``).
            A plain folder name, not a path, and not the state folder's name.
        depth (int): Depth of the group/category hierarchy. Only 2 is implemented.
        levels (list[str]): Names of the levels. Not read by the code yet.
        file_target_level (int): The level files are filed at. Not read by the code yet.
    """

    library_inbox: str = DEFAULT_INBOX_DIRNAME
    depth: int = 2
    levels: list[str] = Field(default_factory=lambda: ["group", "category"])
    file_target_level: int = 2

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


class ExclusionsConfig(BaseModel):
    """Folder name/glob patterns never treated as a category, never descended into."""

    exclude: list[str] = Field(default_factory=list)


class ObsidianConfig(BaseModel):
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

    enabled: bool = True
    tag_index_path: str = "TagIndex.md"
    tag_mode: Literal["suggest", "strict", "off"] = "suggest"


class CategoryHintsConfig(BaseModel):
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

    categories: dict[str, list[str]] = Field(default_factory=dict)


class FilingRulesConfig(BaseModel):
    """Represents the configuration for filing rules.

    Filename-glob -> category rules, checked before keyword hints.

    This class is used to define the configuration for filing rules, which are
    represented as a list of dictionaries mapping strings to strings. It provides
    a structure to easily store and access the filing rules for various applications.

    Attributes:
        rules (list[dict[str, str]]): List of filing rules, where each rule is represented
            as a dictionary mapping strings to strings.
    """

    rules: list[dict[str, str]] = Field(default_factory=list)


class NamingRulesConfig(BaseModel):
    """Represents configuration for naming rules.

    This class is intended to store and manage Regex pattern naming rules defined as key-value pairs.
    These are applied to filenames before filing.
    It provides a way to structure and validate configuration data for naming conventions.

    Attributes:
        rules (dict[str, str]): A dictionary containing naming rules, where the key is the name of the
            rule and the value is its corresponding pattern or configuration.
    """

    rules: dict[str, str] = Field(default_factory=dict)


class ClassificationConfig(BaseModel):
    """How confident microfiche must be before it files a document without asking.

    Attributes:
        confidence_threshold (float): From 0 to 1. A document is filed automatically only if the
            weaker of its group and category confidence reaches this; otherwise it is left for
            review. Higher is stricter. Today's signal strengths are 0.9-1.0 for exact names,
            0.95 for filename rules, 0.75 for keyword hints and 0.70 for AI answers, so the
            default of 0.75 files everything except AI answers; raise it to 0.8 to hold keyword-hint
            matches for review too, or lower it to 0.7 to file AI answers.
    """

    confidence_threshold: float = Field(default=DEFAULT_CONFIDENCE_THRESHOLD, ge=0.0, le=1.0)


class MicroficheConfig(BaseModel):
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
    """

    library_structure: LibraryStructureConfig
    exclusions: ExclusionsConfig
    obsidian: ObsidianConfig
    category_hints: CategoryHintsConfig
    filing_rules: FilingRulesConfig
    naming_rules: NamingRulesConfig
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)


class TomlConfigParseError(ValueError):
    """Exception raised when a TOML configuration file fails to parse.

    This exception is used to provide detailed information about the file path and the
    specific error encountered during the parsing attempt.

    Attributes:
        path (Path | str): Path to the TOML configuration file that failed to parse.
        error (Exception | str): The error message or exception that caused the failure.
    """

    def __init__(self, path: Path | str, error: Exception | str) -> None:
        super().__init__(f"Failed to parse TOML configuration at {path}: {error}")
        self.path = Path(path)
        self.error = error


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


def load_config(config_path: Path) -> MicroficheConfig:
    """Loads the configuration file from the given path and creates a MicroficheConfig object.

    This function evaluates the provided path, determines the existence of a file,
    reads the TOML configuration, and processes various sub-configurations to assemble
    a complete MicroficheConfig object.

    Args:
        config_path (Path): The path to the base configuration directory or a specific
            configuration file. If a directory is provided, the function tries to locate
            the configuration file using a predefined filename.

    Returns:
        MicroficheConfig: An instance of MicroficheConfig containing the parsed configurations
            with details for library structure, exclusions, Obsidian, category hints,
            filing rules, and naming rules.
    Todo:
        - Implement check for .microfiche folder
        - Implement validation of config file and prompt for exit or using defaults if error.
        - Consider adding flag in microfiche-config.toml to indicate whether it's default or custom.
        - Implement validation checks for configuration values.
        - Consider adding logging for configuration loading and processing.
        - Review target_file as nothing in the codebase calls it with a literal file path, only the directory form is ever used
    """
    target_file = config_path if config_path.is_file() else config_path / CONFIG_FILENAME

    config = _load_toml(target_file)
    return MicroficheConfig(
        library_structure=LibraryStructureConfig(**config.get("library_structure", {})),
        exclusions=ExclusionsConfig(**config.get("exclusions", {})),
        obsidian=ObsidianConfig(**config.get("obsidian", {})),
        category_hints=CategoryHintsConfig(**config.get("category_hints", {})),
        filing_rules=FilingRulesConfig(**config.get("filing_rules", {})),
        naming_rules=NamingRulesConfig(**config.get("naming_rules", {})),
        classification=ClassificationConfig(**config.get("classification", {})),
    )
