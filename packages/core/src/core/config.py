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
    """
    Represents configuration for naming rules.

    This class is intended to store and manage Regex pattern naming rules defined as key-value pairs.
    These are applied to filenames before filing.
    It provides a way to structure and validate configuration data for naming conventions.

    :ivar rules: A dictionary containing naming rules, where the key is the name of the
        rule and the value is its corresponding pattern or configuration.
    :type rules: dict[str, str]
    """

    rules: dict[str, str] = Field(default_factory=dict)


class MicroficheConfig(BaseModel):
    """
    Configuration class for managing microfiche system settings.

    This class encapsulates the configuration settings required for the
    microfiche system. It provides a structured and centralized way to
    organize settings related to library structure, exclusions, Obsidian
    integration, category hints, filing rules, and naming rules.

    :ivar library_structure: Configuration for the structure of the library.
    :type library_structure: LibraryStructureConfig
    :ivar exclusions: Configuration for managing exclusions.
    :type exclusions: ExclusionsConfig
    :ivar obsidian: Configuration related to Obsidian integration.
    :type obsidian: ObsidianConfig
    :ivar category_hints: Configuration for category hint options.
    :type category_hints: CategoryHintsConfig
    :ivar filing_rules: Configuration for filing rules.
    :type filing_rules: FilingRulesConfig
    :ivar naming_rules: Configuration for naming rules.
    :type naming_rules: NamingRulesConfig
    """

    library_structure: LibraryStructureConfig
    exclusions: ExclusionsConfig
    obsidian: ObsidianConfig
    category_hints: CategoryHintsConfig
    filing_rules: FilingRulesConfig
    naming_rules: NamingRulesConfig


def _load_toml(path: Path) -> dict[str, Any]:
    """
    Load and parse a TOML file into a dictionary. This function processes the supplied
    file path, ensuring that the file exists before attempting to parse its content.
    If the file does not exist, an empty dictionary is returned allowing default values to be used.
    In case of a parsing failure, a ValueError is raised.

    :param path: The filesystem path to the TOML file to be loaded.
    :type path: Path
    :return: A dictionary containing the parsed TOML data, or an empty dictionary if the file
             does not exist.
    :rtype: dict[str, Any]
    :raises ValueError: If the TOML content is invalid and cannot be parsed.
    """
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as err:
        raise ValueError(f"Failed to parse TOML configuration at {path}: {err}") from err


def load_config(config_path: Path) -> MicroficheConfig:
    """
    Loads the configuration from a given file path. The method determines the target
    configuration file based on the provided path and loads the corresponding data
    from the TOML file. The loaded configuration is then used to initialize and return
    a `MicroficheConfig` object.

    :param config_path: Path to the configuration file or directory containing the
        configuration file.
    :type config_path: Path
    :return: An instance of `MicroficheConfig` containing the loaded configuration data.
    :rtype: MicroficheConfig
    """
    if config_path.is_file():
        target_file = config_path
    else:
        target_file = config_path / CONFIG_FILENAME

    config = _load_toml(target_file)
    return MicroficheConfig(
        library_structure=LibraryStructureConfig(**config.get("library_structure", {})),
        exclusions=ExclusionsConfig(**config.get("exclusions", {})),
        obsidian=ObsidianConfig(**config.get("obsidian", {})),
        category_hints=CategoryHintsConfig(**config.get("category_hints", {})),
        filing_rules=FilingRulesConfig(**config.get("filing_rules", {})),
        naming_rules=NamingRulesConfig(**config.get("naming_rules", {})),
    )
