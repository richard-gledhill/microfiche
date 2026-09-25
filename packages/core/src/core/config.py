"""Loads microfiche's YAML configuration files into typed settings objects.

These live at ``<library_root>/.microfiche-config/`` for the library microfiche is managing -
not inside this repository. Dot-prefixed so it's hidden from Obsidian's file explorer by
default. The ``microfiche-config/`` folder shipped in this repo is the set of defaults a new
library should start from, copied in as ``.microfiche-config/`` (see microfiche-config/README.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
import tomlib

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
    """Keyword hints per *existing* category name, used by the rules engine - not the category
    list itself, which is discovered from the library's folders (see core.library.taxonomy)."""

    categories: dict[str, list[str]] = Field(default_factory=dict)


class FilingRulesConfig(BaseModel):
    """Filename-glob -> category rules, checked before keyword hints."""

    rules: list[dict[str, str]] = Field(default_factory=list)


class NamingRulesConfig(BaseModel):
    """Regex pattern -> replacement rules applied to filenames before filing."""

    rules: dict[str, str] = Field(default_factory=dict)


class MicroficheConfig(BaseModel):
    """Every config file for one library, bundled together."""

    library_structure: LibraryStructureConfig
    exclusions: ExclusionsConfig
    obsidian: ObsidianConfig
    category_hints: CategoryHintsConfig
    filing_rules: FilingRulesConfig
    naming_rules: NamingRulesConfig


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError(f"Expected a mapping at the top of {path}, got {type(data).__name__}")  # noqa: TRY003
    return data


def load_config(config_dir: Path) -> MicroficheConfig:
    """Load every microfiche config file from ``config_dir``, defaulting anything that's missing."""

    return MicroficheConfig(
        library_structure=LibraryStructureConfig(**_load_yaml(config_dir / "library_structure.yaml")),
        exclusions=ExclusionsConfig(**_load_yaml(config_dir / "exclusions.yaml")),
        obsidian=ObsidianConfig(**_load_yaml(config_dir / "obsidian.yaml")),
        category_hints=CategoryHintsConfig(
            categories=_load_yaml(config_dir / "categories.yaml").get("categories", {}),
        ),
        filing_rules=FilingRulesConfig(rules=_load_yaml(config_dir / "filing_rules.yaml").get("rules", [])),
        naming_rules=NamingRulesConfig(rules=_load_yaml(config_dir / "naming_rules.yaml").get("rules", {})),
    )
