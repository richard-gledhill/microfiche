"""Loads microfiche's TOML configuration files into typed settings objects.

These live at ``<library_root>/.microfiche/`` for the library microfiche is managing -
not inside this repository. Dot-prefixed so it's hidden from Obsidian's or similar file explorer by
default. ``microfiche init`` writes the packaged defaults there for a new library, and checks and
edits an existing one (``microfiche.core.library_init``).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# region Constants and types

CONFIG_FILENAME = "microfiche-config.toml"
# Per-library folder holding the config and everything microfiche writes about its own work
# (ledger, audit log, rollback jobs). Dot-prefixed so Obsidian's file explorer hides it.
MICROFICHE_DIRNAME = ".microfiche"
# The library depths (levels of folders) the code supports: 1 is groups only, 2 is group then category.
SUPPORTED_DEPTHS = (1, 2)
# The levels a log file can be set to. Not NOTSET (it means "no level") or the aliases WARN and FATAL.
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
# The names of microfiche's own files and folder in the state folder, in lower case: the log file may be none of them,
# because writing log lines to one would corrupt it. Compared without regard to case, since Windows and macOS file
# systems do not tell "Audit.log" from "audit.log". They are written out here because importing the constants that
# own them (filer, ledger, runlock, library_file) would be circular; a test keeps the two in step.
_STATE_FILE_NAMES = frozenset({
    "microfiche-config.toml",
    "microfiche-library.json",
    "microfiche-library.schema.json",
    "readme.md",
    "ledger.jsonl",
    "audit.log",
    "lock",
    "rollback",
})
# What an environment variable name looks like. Real API keys contain characters this rejects.
_ENV_VAR_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class ConfigProblem:
    """One thing wrong with a config file, located so ``init`` can put just that right.

    Attributes:
        section: The top-level name the problem is in, such as ``"classification"``.
        setting: The setting inside it, or ``None`` when the problem is the section as a whole (it is not a table,
            it is not a known section, or a rule across its settings fails).
        kind: ``"unknown"`` for a name that is not a section or setting, ``"invalid"`` for anything else.
        message: The problem as the error message words it, such as ``"classification.depth: unknown setting"``.
    """

    section: str
    setting: str | None
    kind: Literal["invalid", "unknown"]
    message: str

    @property
    def place(self) -> str:
        """``section.setting``, or the section alone."""

        return self.section if self.setting is None else f"{self.section}.{self.setting}"


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
        depth (int): How many levels of folders the library has: 1 is groups only (a flat library), 2 is group
            then category.
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
        model (str): The model to ask. Required with ``--use-ai``; there is no default. Ollama: a model you have
            pulled, such as ``"llama3.1"`` (``ollama list`` shows them, ``ollama pull <name>`` installs one).
            OpenAI: a model name, such as ``"gpt-4o-mini"``.
        host (str): Where the Ollama server is. Empty means Ollama's default address,
            ``http://localhost:11434``. Set it for a server on another machine, such as
            ``"http://gpu-box:11434"``. Ollama only.
        timeout (float): Seconds to wait for one answer. Greater than 0. A first call can be slow while Ollama
            loads the model: raise it if that times out.
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


class LoggingConfig(_ConfigSection):
    """How microfiche writes its diagnostic log, ``.microfiche/microfiche.log`` by default.

    The log is for people finding out what a run did. It is separate from the audit log and the
    ledger, which ``rollback`` reads. The console's level is set by the ``-v`` and ``-q`` options alone.

    Attributes:
        level (str): The log file's level when ``-v`` is not given: ``"DEBUG"``, ``"INFO"``,
            ``"WARNING"``, ``"ERROR"`` or ``"CRITICAL"``.
        file (str): The log file's name, kept inside the library's ``.microfiche/`` folder. A plain
            file name, not a path, and not the name of one of microfiche's own files there (the audit
            log, the ledger, the config and so on).
        max_bytes (int): Greater than 0. The size at which the log file is rotated to a backup.
        backup_count (int): At least 0. How many rotated backups to keep. At 0 the file is never
            rotated and grows without limit, because Python's rotating handler only rotates when
            this is above 0.
    """

    level: str
    file: str
    max_bytes: int = Field(gt=0)
    backup_count: int = Field(ge=0)

    @field_validator("level")
    @classmethod
    def _level_is_a_level_name(cls, value: str) -> str:
        level = value.upper()
        if level not in _LOG_LEVELS:
            raise InvalidLogLevelError(value)
        return level

    @field_validator("file")
    @classmethod
    def _file_is_a_file_name(cls, value: str) -> str:
        if not value.strip():
            raise InvalidLogFileNameError(value, "it is empty")
        if "/" in value or "\\" in value:
            raise InvalidLogFileNameError(value, "it must be a single file name, not a path")
        if value in (".", ".."):
            raise InvalidLogFileNameError(value, "it must name a file inside the state folder")
        if ":" in value:
            raise InvalidLogFileNameError(value, "it cannot contain ':', which Windows reads as a drive")
        if value.casefold() in _STATE_FILE_NAMES:
            raise InvalidLogFileNameError(value, "that is one of microfiche's own files in the state folder")
        return value


class MicroficheConfig(_ConfigSection):
    """Configuration container for Microfiche.

    Represents the configuration settings for the Microfiche system, which
    defines the structure and behavior of file management, organization, and
    categorization. This class holds detailed settings for library structure,
    file exclusions, classification, the AI fallback,
    sorting and naming conventions. The library's category hints and filing rules are not
    here: they live in ``microfiche-library.json`` (see ``microfiche.core.library.library_file``).

    Attributes:
        library_structure (LibraryStructureConfig): Configuration for the library structure.
        exclusions (ExclusionsConfig): Configuration for file and folder exclusions.
        naming_rules (NamingRulesConfig): Configuration for rules governing file naming.
        classification (ClassificationConfig): Configuration for how confident a
            classification must be before a document is filed automatically.
        ai (AIConfig): Configuration for the AI fallback.
        sorting (SortingConfig): Configuration for how the inbox is sorted.
        parsing (ParsingConfig): Configuration for how documents are read.
        logging (LoggingConfig): Configuration for the diagnostic log file.
    """

    library_structure: LibraryStructureConfig
    exclusions: ExclusionsConfig
    naming_rules: NamingRulesConfig
    classification: ClassificationConfig
    ai: AIConfig
    sorting: SortingConfig
    parsing: ParsingConfig
    logging: LoggingConfig


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
            f"depth {depth} is not supported yet: libraries are group folders, or group and category folders, "
            f"so only {supported} is supported"
        )


class ConfigError(ValueError):
    """The library's configuration can't be used; the message says why and where.

    Attributes:
        problems: Each problem as data, when the file was read and failed validation; empty otherwise (it is not
            TOML, or the error is not about the config's settings).
    """

    def __init__(self, message: str, problems: tuple[ConfigProblem, ...] = ()) -> None:
        super().__init__(message)
        self.problems = problems


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


class EmptyModelError(ConfigError):
    """Raised when the AI is wanted but ``[ai] model`` is empty: microfiche picks no model for you."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        if provider == "openai":
            how = "set it to an OpenAI model name, for example gpt-4o-mini"
        else:
            how = "set it to a model installed in Ollama (`ollama list` shows them, `ollama pull <name>` installs one)"
        super().__init__(f"[ai] model is empty: {how}.")


class InvalidLogFileNameError(ValueError):
    """Raised when ``[logging] file`` isn't a usable log file name."""

    def __init__(self, value: str, reason: str) -> None:
        self.value = value
        super().__init__(f"[logging] file {value!r} is not a valid log file name: {reason}")


class InvalidLogLevelError(ValueError):
    """Raised when ``[logging] level`` isn't a log level name."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(f"[logging] level {value!r} is not a log level: use DEBUG, INFO, WARNING, ERROR or CRITICAL")


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
    return validate_config(_load_toml(target_file), target_file)


def validate_config(settings: dict[str, Any], target_file: Path) -> MicroficheConfig:
    """Merge ``settings`` over the packaged defaults and validate the result, as ``load_config`` does for a file.

    Args:
        settings: What a config file sets, as plain data.
        target_file: The file the settings are (or will be) in, for the error message.

    Returns:
        The validated configuration.

    Raises:
        ConfigError: If the settings are not a valid configuration, with every problem in ``problems``.
    """

    try:
        return MicroficheConfig.model_validate(_deep_merge(_load_packaged_defaults(), settings))
    except ValidationError as err:
        raise ConfigError(describe_validation_errors(target_file, err), _problems(err)) from err


def packaged_defaults_text() -> str:
    """The packaged defaults file (``core/defaults/microfiche-config.toml``) as it is, comments included."""

    return resources.files("microfiche.core").joinpath("defaults", CONFIG_FILENAME).read_text(encoding="utf-8")


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
    lines.extend(f"  {_describe(error['loc'], error['type'], error['msg'], unknown)}" for error in err.errors())
    return "\n".join(lines)


# endregion


# region Helpers


def _load_packaged_defaults() -> dict[str, Any]:
    """Read the defaults file shipped inside the ``microfiche.core`` package (``microfiche/core/defaults/``)."""
    return tomllib.loads(packaged_defaults_text())


def _describe(loc: tuple[str | int, ...], kind: str, msg: str, unknown: tuple[str, str]) -> str:
    """One validation error (its ``loc``, ``type`` and ``msg``) as ``location: reason``, worded for a person."""

    location = _loc_to_dot_sep(loc)
    match kind, len(loc):
        case "extra_forbidden", 1:
            reason = f"unknown {unknown[0]}"
        case "extra_forbidden", _:
            reason = f"unknown {unknown[1]}"
        case _:
            reason = msg.removeprefix("Value error, ")
    return f"{location}: {reason}" if location else reason


def _problems(err: ValidationError) -> tuple[ConfigProblem, ...]:
    """Each validation error of a whole config as a ``ConfigProblem``."""

    return tuple(
        ConfigProblem(
            section=str(error["loc"][0]),
            setting=str(error["loc"][1]) if len(error["loc"]) > 1 else None,
            kind="unknown" if error["type"] == "extra_forbidden" else "invalid",
            message=_describe(error["loc"], error["type"], error["msg"], ("section", "setting")),
        )
        for error in err.errors()
    )


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
