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

from pydantic import BaseModel, Field

CONFIG_FILENAME = "microfiche-config.toml"


class LibraryStructureConfig(BaseModel):
    """Depth and naming of the library's group/category hierarchy."""

    depth: int = 2
    levels: list[str] = Field(default_factory=lambda: ["group", "category"])
    file_target_level: int = 2


class ExclusionsConfig(BaseModel):
    """Folder name/glob patterns never treated as a category, never descended into."""

    exclude: list[str] = Field(default_factory=list)


class ObsidianConfig(BaseModel):
    """Obsidian integration: index.md generation and TagIndex.md governance."""

    enabled: bool = True
    tag_index_path: str = "TagIndex.md"
    tag_mode: Literal["suggest", "strict", "off"] = "suggest"


class CategoryHintsConfig(BaseModel):
    """
    Represents the configuration for category hints.

    Keyword hints per *existing* category name, used by the rules engine - not the category
    list itself, which is discovered from the library's folders (see core.library.taxonomy).

    This class is used to define and manage a mapping between category names and their
    associated hints. The primary purpose of this configuration is to store and organize
    categories while allowing easy access to their related hints. It serves as a data
    structure for categorization-related functionality.

    :ivar categories: A dictionary mapping category names to a list of associated hints.
    :type categories: dict[str, list[str]]
    """

    categories: dict[str, list[str]] = Field(default_factory=dict)


class FilingRulesConfig(BaseModel):
    """
    Represents the configuration for filing rules.
    Filename-glob -> category rules, checked before keyword hints.

    This class is used to define the configuration for filing rules, which are
    represented as a list of dictionaries mapping strings to strings. It provides
    a structure to easily store and access the filing rules for various applications.

    :ivar rules: List of filing rules, where each rule is represented as a dictionary
        mapping strings to strings.
    :type rules: list[dict[str, str]]
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
    """

    library_structure: LibraryStructureConfig
    exclusions: ExclusionsConfig
    obsidian: ObsidianConfig
    category_hints: CategoryHintsConfig
    filing_rules: FilingRulesConfig
    naming_rules: NamingRulesConfig


class TomlConfigParseError(ValueError):
    """Raised when TOML configuration parsing fails."""

    def __init__(self, path: Path | str, error: Exception | str) -> None:
        super().__init__(f"Failed to parse TOML configuration at {path}: {error}")
        self.path = Path(path)
        self.error = error


def _load_toml(path: Path) -> dict[str, Any]:
    """
    Loads and parses a TOML file from the specified path. If the file does not exist
    or cannot be parsed due to format errors, appropriate handling is performed.

    :param path: The path to the TOML file to be loaded.
    :type path: Path
    :return: A dictionary representing the parsed TOML configuration if the file
        is valid, or an empty dictionary if the file does not exist.
    :rtype: dict[str, Any]
    :raises ValueError: If the TOML file cannot be parsed due to a decoding error.
    """
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as err:
        raise TomlConfigParseError(path, err) from err


def load_config(config_path: Path) -> MicroficheConfig:
    """
    Loads the configuration file from the given path and creates a MicroficheConfig
    object based on the loaded configuration. This function evaluates the provided
    path, determines the existence of a file, reads the TOML configuration, and
    processes various sub-configurations to assemble a complete MicroficheConfig
    object.

    :param config_path: The path to the base configuration directory or a specific
        configuration file. If a directory is provided, the function tries to locate
        the configuration file using a predefined filename.
    :type config_path: Path

    :return: An instance of MicroficheConfig containing the parsed configurations
        with details for library structure, exclusions, Obsidian, category hints,
        filing rules, and naming rules.
    :rtype: MicroficheConfig
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
    )
