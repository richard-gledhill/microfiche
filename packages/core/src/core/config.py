"""Loads microfiche's TOML configuration files into typed settings objects.

These live at ``<library_root>/.microfiche/`` for the library microfiche is managing -
not inside this repository. Dot-prefixed so it's hidden from Obsidian's or similar file explorer by
default. The ``microfiche/`` folder shipped in this repo is the set of defaults a new
library should start from, copied in as ``.microfiche/`` (see microfiche/README.md).
"""

from __future__ import annotations

import re
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# region Constants and types

CONFIG_FILENAME = "microfiche-config.toml"
# Per-library folder holding the config and everything microfiche writes about its own work
# (ledger, audit log, rollback jobs). Dot-prefixed so Obsidian's file explorer hides it.
MICROFICHE_DIRNAME = ".microfiche"
# The library depths (levels of folders) the code supports. Stage 4.6 adds 1.
SUPPORTED_DEPTHS = (2,)
# What an environment variable name looks like. Real API keys contain characters this rejects.
_ENV_VAR_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


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
        depth (int): How many levels of folders the library has: 2 is group then category, the only depth
            supported today.
    """

    library_inbox: str
    depth: int

    @field_validator("depth")
    @classmethod
    def _depth_is_supported(cls, value: int) -> int:
        if value not in SUPPORTED_DEPTHS:
            raise UnsupportedDepthError(value)
        return value

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
            (a RapidFuzz partial-ratio score, rounded to a whole number) to count as that group.
    """

    confidence_threshold: float = Field(ge=0.0, le=1.0)
    name_match_confidence: float = Field(ge=0.0, le=1.0)
    filename_match_confidence: float = Field(ge=0.0, le=1.0)
    hint_match_confidence: float = Field(ge=0.0, le=1.0)
    fuzzy_group_threshold: int = Field(ge=0, le=100)


class AIConfig(_ConfigSection):
    """How the AI fallback is trusted and what it is sent.

    Attributes:
        provider (Literal["ollama", "openai"]): Who answers. ``"ollama"`` runs on your machine;
            ``"openai"`` sends the text of every document the AI is asked about to OpenAI.
        model (str): The model to ask. Empty means the provider's own default.
        host (str): Where the Ollama server is. Empty means Ollama's default address. Ollama only.
        timeout (float): Seconds to wait for one answer. Greater than 0.
        api_key_env (str): The *name* of the environment variable holding the OpenAI key. The key
            itself never goes in the file.
        ai_confidence (float): From 0 to 1. How sure any answer from the AI fallback is, whatever
            model gave it. Compared with ``[classification] confidence_threshold`` to decide whether
            an AI-only answer files or goes to review.
        max_document_chars (int): At least 0. How much of a document's text is sent to the AI;
            0 means all of it.
    """

    provider: Literal["ollama", "openai"]
    model: str
    host: str
    timeout: float = Field(gt=0)
    api_key_env: str
    ai_confidence: float = Field(ge=0.0, le=1.0)
    max_document_chars: int = Field(ge=0)

    @field_validator("api_key_env")
    @classmethod
    def _names_an_environment_variable(cls, value: str) -> str:
        if not _ENV_VAR_NAME.fullmatch(value):
            raise InvalidApiKeyEnvError(value)
        return value

    @model_validator(mode="after")
    def _host_is_for_ollama(self) -> AIConfig:
        if self.host and self.provider != "ollama":
            raise HostWithoutOllamaError(self.provider)
        return self


class SortingConfig(_ConfigSection):
    """How the inbox is sorted.

    Attributes:
        keep_folders (bool): Whether a folder in the inbox is filed whole, as one unit under its
            dominant category. If not, each document in it is filed on its own and the folder is
            removed once it is empty. The ``--keep-folders`` and ``--keep-folders-off`` options
            override it for one run.
        ignore (list[str]): File and folder name patterns (globs) the inbox scan skips without
            comment, such as Office lock files (``~$*``) and ``Thumbs.db``. A skipped file is never
            read or filed; a folder is not descended into.
    """

    keep_folders: bool
    ignore: list[str]


class ParsingConfig(_ConfigSection):
    """How documents are read.

    Attributes:
        max_file_mb (float): Greater than 0. A file bigger than this many megabytes is not parsed:
            it is left for review with the reason, so one huge file cannot exhaust memory or stall a run.
    """

    max_file_mb: float = Field(gt=0)

    @property
    def max_file_bytes(self) -> int:
        """``max_file_mb`` in bytes."""

        return int(self.max_file_mb * 1024 * 1024)


class MicroficheConfig(_ConfigSection):
    """Configuration container for Microfiche.

    Represents the configuration settings for the Microfiche system, which
    defines the structure and behavior of file management, organization, and
    categorization. This class holds detailed settings for library structure,
    file exclusions, integration with Obsidian, classification, the AI fallback,
    sorting and naming conventions. The library's category hints and filing rules are not
    here: they live in ``microfiche-library.json`` (see ``core.library.library_file``).

    Attributes:
        library_structure (LibraryStructureConfig): Configuration for the library structure.
        exclusions (ExclusionsConfig): Configuration for file and folder exclusions.
        obsidian (ObsidianConfig): Configuration for Obsidian integration.
        naming_rules (NamingRulesConfig): Configuration for rules governing file naming.
        classification (ClassificationConfig): Configuration for how confident a
            classification must be before a document is filed automatically.
        ai (AIConfig): Configuration for the AI fallback.
        sorting (SortingConfig): Configuration for how the inbox is sorted.
        parsing (ParsingConfig): Configuration for how documents are read.
    """

    library_structure: LibraryStructureConfig
    exclusions: ExclusionsConfig
    obsidian: ObsidianConfig
    naming_rules: NamingRulesConfig
    classification: ClassificationConfig
    ai: AIConfig
    sorting: SortingConfig
    parsing: ParsingConfig


# endregion


# region Errors


class InvalidInboxNameError(ValueError):
    """Raised when ``library_inbox`` isn't a usable folder name."""

    def __init__(self, value: str, reason: str) -> None:
        self.value = value
        super().__init__(f"library_inbox {value!r} is not a valid folder name: {reason}")


class UnsupportedDepthError(ValueError):
    """Raised when ``depth`` is a number of levels this version of microfiche cannot work with."""

    def __init__(self, depth: int) -> None:
        self.depth = depth
        supported = " or ".join(str(supported) for supported in SUPPORTED_DEPTHS)
        super().__init__(
            f"depth {depth} is not supported yet: libraries are group and category folders, "
            f"so only {supported} is supported"
        )


class ConfigError(ValueError):
    """The library's configuration can't be used; the message says why and where."""


class InvalidApiKeyEnvError(ValueError):
    """Raised when ``api_key_env`` isn't an environment variable name (it may be a pasted key)."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(
            f"{value!r} is not an environment variable name; give the name of the variable that holds "
            "the key (such as OPENAI_API_KEY), never the key itself"
        )


class HostWithoutOllamaError(ValueError):
    """Raised when ``host`` is set for a provider other than Ollama."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"host is only used by the ollama provider, not {provider!r}")


class MissingApiKeyError(ConfigError):
    """Raised when the environment variable named by ``api_key_env`` holds no key."""

    def __init__(self, variable: str) -> None:
        self.variable = variable
        super().__init__(
            f"[ai] provider is 'openai' but the environment variable {variable} is not set. "
            "Set it to your OpenAI API key, or use provider = 'ollama'."
        )


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
        raise ConfigError(describe_validation_errors(target_file, err)) from err


def describe_validation_errors(
    target_file: Path,
    err: ValidationError,
    *,
    title: str = "Config file error",
    unknown: tuple[str, str] = ("section", "setting"),
) -> str:
    """Format pydantic validation errors as one line per problem, under the file path.

    Args:
        target_file: The file that failed validation.
        err: The validation error.
        title: What the first line calls the file's kind of error.
        unknown: What an unrecognised name is called at the top level and below it.

    Returns:
        A message naming the file and every problem, located by its path in the file.
    """

    lines = [f"{title}: {target_file}:"]
    for error in err.errors():
        location = _loc_to_dot_sep(error["loc"])
        match error["type"], len(error["loc"]):
            case "extra_forbidden", 1:
                reason = f"unknown {unknown[0]}"
            case "extra_forbidden", _:
                reason = f"unknown {unknown[1]}"
            case _:
                reason = error["msg"].removeprefix("Value error, ")
        lines.append(f"  {location}: {reason}" if location else f"  {reason}")
    return "\n".join(lines)


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
    """Join an error location into a dotted path, such as ``exclusions.exclude[1]``."""
    path = ""
    for i, part in enumerate(loc):
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if i else part
    return path


# endregion
