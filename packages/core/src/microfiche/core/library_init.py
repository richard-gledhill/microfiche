"""Setting up, checking and editing a library's configuration: the engine behind ``microfiche init``.

A library with no config gets the packaged defaults written as they are. An existing config is checked with the same
validation ``load_config`` uses, and edited through ``ConfigEditor``, which keeps the file as a ``tomlkit`` document so
the user's comments and layout survive and a changed setting rewrites only its value. Nothing here asks a question;
the prompts are in ``microfiche.cli.init``. Nothing here creates, moves or deletes a user's folder or document: the one
folder it may create is the inbox, which is microfiche's own.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import tomlkit
from microfiche.core.config import (
    CONFIG_FILENAME,
    ConfigError,
    ConfigProblem,
    load_config,
    packaged_defaults_text,
    validate_config,
)
from microfiche.core.library.library import Library
from microfiche.core.library.library_file import LIBRARY_FILENAME
from microfiche.core.library.library_sync import LibrarySync, sync_library_file
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

# region Constants and types

# The settings most people change, asked first; the rest are behind one "go through all the others?".
COMMON_SETTINGS: tuple[tuple[str, str], ...] = (
    ("classification", "confidence_threshold"),
    ("library_structure", "depth"),
    ("library_structure", "library_inbox"),
    ("sorting", "keep_folders"),
    ("ai", "provider"),
    ("ai", "model"),
)
# What a value of "-" means: clear the setting (an empty string or an empty list).
CLEAR = "-"
BACKUP_SUFFIX = ".bak"
# For a rule across a section's settings that fails, the settings put back to their defaults to satisfy it.
_RULE_SETTINGS: dict[str, tuple[str, ...]] = {"ai": ("host",)}
_TRUE = frozenset({"y", "yes", "true", "on"})
_FALSE = frozenset({"n", "no", "false", "off"})
# Stands for a setting the file did not have, when comparing it before and after.
_MISSING = object()


class InstallState(StrEnum):
    """What ``init`` finds in a library's state folder."""

    MISSING = "missing"
    VALID = "valid"
    INVALID = "invalid"


@dataclass(frozen=True)
class InstallCheck:
    """The result of ``inspect_install``.

    Attributes:
        state: Whether there is a config, and whether it is valid.
        error: Why it is invalid, or ``None``.
    """

    state: InstallState
    error: ConfigError | None = None

    @property
    def problems(self) -> tuple[ConfigProblem, ...]:
        """Each problem as data. Empty for a valid config, and for a file that is not TOML."""

        return self.error.problems if self.error is not None else ()


@dataclass(frozen=True)
class Setting:
    """One setting, as the walk-through shows it.

    Attributes:
        section: Its section, such as ``"classification"``.
        name: Its name in the section, such as ``"confidence_threshold"``.
        value: What it is now: the file's value, or the default when the file does not set it.
        default: The packaged default.
        help: The one-line explanation, from the comment above it in the packaged defaults.
    """

    section: str
    name: str
    value: Any
    default: Any
    help: str

    @property
    def key(self) -> str:
        """``section.name``."""

        return f"{self.section}.{self.name}"

    @property
    def editable(self) -> bool:
        """Whether it can be typed in at a prompt. A table (``naming_rules.rules``) is edited in the file."""

        return not isinstance(self.default, dict)


@dataclass(frozen=True)
class SettingChange:
    """One difference between the file as it was read and as it would be written, for the summary.

    Attributes:
        key: ``section.name``, or a section's name when the whole section changed.
        old: The old value as TOML-like text, or ``"(not set)"``.
        new: The new value as TOML-like text, or ``"(removed)"``.
    """

    key: str
    old: str
    new: str


# endregion


# region Errors


class InvalidSettingValueError(ValueError):
    """Raised when a value typed for a setting is the wrong type or fails validation. The message says why."""

    def __init__(self, key: str, reason: str) -> None:
        self.key = key
        super().__init__(f"{key}: {reason}")


class ConfigExistsError(FileExistsError):
    """Raised when writing the defaults would replace a config the library already has."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{path} already exists")


class NotTomlError(ConfigError):
    """Raised when editing a config that is not TOML, which only reverting all settings can fix."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{path} is not valid TOML; only reverting all settings can fix it")


class ConfigChangedError(RuntimeError):
    """Raised when the config file changed on disk after ``ConfigEditor`` read it, so writing would lose that."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{path} changed since it was read, so it was not overwritten. Run init again.")


class BackupExistsError(FileExistsError):
    """Raised when a backup is already there and replacing it was not agreed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"a backup already exists at {path}")


# endregion


# region Public API


def inspect_install(state_dir: Path) -> InstallCheck:
    """Say whether the state folder has a config, and whether it is valid.

    Args:
        state_dir: The library's ``.microfiche/`` folder.

    Returns:
        The state, with the error when the config is invalid (including a file that is not TOML).
    """

    if not (state_dir / CONFIG_FILENAME).is_file():
        return InstallCheck(InstallState.MISSING)
    try:
        load_config(state_dir)
    except ConfigError as err:
        return InstallCheck(InstallState.INVALID, err)
    return InstallCheck(InstallState.VALID)


def install_defaults(state_dir: Path) -> Path:
    """Write the packaged defaults file, as it is, as the library's config.

    Args:
        state_dir: The library's ``.microfiche/`` folder. Created if missing.

    Returns:
        The config file's path.

    Raises:
        ConfigExistsError: If the library already has a config. It is left alone.
    """

    path = state_dir / CONFIG_FILENAME
    if path.exists():
        raise ConfigExistsError(path)
    state_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, packaged_defaults_text().encode("utf-8"))
    return path


def create_inbox(library: Library) -> Path | None:
    """Create the library's inbox folder if it is missing.

    Args:
        library: The library, with a valid config (the inbox's name comes from it).

    Returns:
        The inbox's path if it was created, or ``None`` if something by that name was already there.
    """

    inbox = library.inbox
    if inbox.exists():
        return None
    inbox.mkdir(parents=True)
    return inbox


def rebuild_library_file(library: Library) -> tuple[Path, LibrarySync]:
    """Move an unloadable library file aside and write a new one from the folders.

    Args:
        library: The library, with a valid config.

    Returns:
        Where the old file now is, and what the sync wrote.
    """

    path = library.state_dir / LIBRARY_FILENAME
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    os.replace(path, backup)
    return backup, sync_library_file(library)


class ConfigEditor:
    """The library's config file, open for editing.

    Changes are made to a ``tomlkit`` document in memory; nothing is written until ``save``. A setting the file
    does not have is added to its section (the section added at the end when the file has none).
    """

    def __init__(self, state_dir: Path) -> None:
        """Read the config in ``state_dir``. A file that is not TOML can only be replaced (``revert_all``).

        Args:
            state_dir: The library's ``.microfiche/`` folder.
        """

        self.path = state_dir / CONFIG_FILENAME
        self._original = self.path.read_bytes() if self.path.is_file() else b""
        self._original_text = self._original.decode("utf-8", errors="replace")
        self._defaults = tomllib.loads(packaged_defaults_text())
        self._help = _help_lines(packaged_defaults_text())
        self._document: TOMLDocument | None
        try:
            self._document = tomlkit.parse(self._original_text)
        except tomlkit.exceptions.ParseError:
            self._document = None
        self._original_settings = _flatten(self._document.unwrap()) if self._document is not None else {}

    @property
    def backup_path(self) -> Path:
        """Where ``save`` keeps a copy of the file as it was read."""

        return self.path.with_name(self.path.name + BACKUP_SUFFIX)

    @property
    def parsed(self) -> bool:
        """Whether there is a TOML document to edit (the file was TOML, or has been replaced by the defaults)."""

        return self._document is not None

    @property
    def text(self) -> str:
        """The file as it would be written now, with the file's own line endings."""

        if self._document is None:
            return self._original_text
        text = tomlkit.dumps(self._document)
        return re.sub(r"(?<!\r)\n", "\r\n", text) if "\r\n" in self._original_text else text

    @property
    def changed(self) -> bool:
        """Whether ``save`` would write anything."""

        return self.text.encode("utf-8") != self._original

    def settings(self) -> list[Setting]:
        """Every setting the packaged defaults have, in their order, with its current value."""

        current = self._effective()
        return [
            Setting(section, name, current[section][name], default, self._help.get(f"{section}.{name}", ""))
            for section, table in self._defaults.items()
            for name, default in table.items()
        ]

    def setting(self, section: str, name: str) -> Setting:
        """One setting, as ``settings`` lists it.

        Raises:
            KeyError: If there is no such setting.
        """

        for setting in self.settings():
            if (setting.section, setting.name) == (section, name):
                return setting
        raise KeyError(f"{section}.{name}")

    def parse(self, setting: Setting, raw: str) -> Any:
        """Turn what was typed into a value of the setting's type (taken from its default).

        A list is typed comma-separated, and ``-`` clears a list or a text setting.

        Raises:
            InvalidSettingValueError: If ``raw`` is not a value of that type.
        """

        raw = raw.strip()
        default = setting.default
        if isinstance(default, bool):
            if raw.lower() in _TRUE:
                return True
            if raw.lower() in _FALSE:
                return False
            raise InvalidSettingValueError(setting.key, "answer yes or no")
        if isinstance(default, int | float):
            for kind in (int, float):
                try:
                    return kind(raw)
                except ValueError:
                    continue
            raise InvalidSettingValueError(setting.key, f"{raw!r} is not a number")
        if isinstance(default, list):
            return [] if raw == CLEAR else [part.strip() for part in raw.split(",") if part.strip()]
        return "" if raw == CLEAR else raw

    def set(self, section: str, name: str, value: Any) -> None:
        """Change a setting, if ``value`` is valid with every change made so far. Setting the current value does nothing.

        Raises:
            InvalidSettingValueError: If the config would then be invalid at this setting or its section.
        """

        document = self._require_document()
        if self._effective()[section][name] == value:
            return
        candidate = document.unwrap()
        table = candidate.get(section)
        candidate[section] = {**(table if isinstance(table, dict) else {}), name: value}
        try:
            validate_config(candidate, self.path)
        except ConfigError as err:
            here = [
                p.message.removeprefix(f"{p.place}: ")
                for p in err.problems
                if p.section == section and p.setting in (name, None)
            ]
            if here:
                raise InvalidSettingValueError(f"{section}.{name}", "; ".join(here)) from err
        container = document.get(section)
        if not isinstance(container, Table):
            container = tomlkit.table()
            document[section] = container
        container[name] = value

    def problems(self) -> tuple[ConfigProblem, ...]:
        """What is wrong with the config as it would be written now. Empty when it is valid."""

        settings = self._require_document().unwrap()
        try:
            validate_config(settings, self.path)
        except ConfigError as err:
            return err.problems
        return ()

    def revert_invalid(self, problems: tuple[ConfigProblem, ...]) -> None:
        """Put right only what ``problems`` names, keeping every other setting, comment and line.

        An invalid setting is set to its default; an unknown setting or section is removed; a section that is not
        a table is removed (so its settings take their defaults); and a failed rule across a section's settings
        puts the settings that rule names back to their defaults.
        """

        document = self._require_document()
        for problem in problems:
            container = document.get(problem.section)
            if problem.setting is None:
                if problem.kind == "invalid" and isinstance(container, Table) and problem.section in _RULE_SETTINGS:
                    for name in _RULE_SETTINGS[problem.section]:
                        container[name] = self._defaults[problem.section][name]
                elif problem.section in document:
                    del document[problem.section]
            elif isinstance(container, Table) and problem.setting in container:
                if problem.kind == "unknown":
                    del container[problem.setting]
                else:
                    container[problem.setting] = self._defaults[problem.section][problem.setting]

    def revert_all(self) -> None:
        """Replace the whole file with the packaged defaults."""

        self._document = tomlkit.parse(packaged_defaults_text())

    def changes(self) -> list[SettingChange]:
        """What differs between the file as read and as it would be written, setting by setting."""

        if self._document is None:
            return []
        now = _flatten(self._document.unwrap())
        found = [
            SettingChange(
                key,
                _show(self._original_settings[key]) if key in self._original_settings else "(not set)",
                _show(value),
            )
            for key, value in now.items()
            if self._original_settings.get(key, _MISSING) != value
        ]
        found.extend(
            SettingChange(key, _show(value), "(removed)")
            for key, value in self._original_settings.items()
            if key not in now
        )
        return found

    def save(self, *, replace_backup: bool = False) -> Path | None:
        """Write the changes, after keeping a copy of the file as it was read.

        Args:
            replace_backup: Whether an existing backup may be replaced.

        Returns:
            The backup's path, or ``None`` when nothing changed (nothing is written, and no backup is made).

        Raises:
            ConfigChangedError: If the file on disk is no longer what was read. Nothing is written.
            BackupExistsError: If a backup is already there and ``replace_backup`` is false. Nothing is written.
        """

        if not self.changed:
            return None
        on_disk = self.path.read_bytes() if self.path.is_file() else b""
        if on_disk != self._original:
            raise ConfigChangedError(self.path)
        if self.backup_path.exists() and not replace_backup:
            raise BackupExistsError(self.backup_path)
        _write_atomic(self.backup_path, self._original)
        _write_atomic(self.path, self.text.encode("utf-8"))
        return self.backup_path

    def _effective(self) -> dict[str, Any]:
        """The packaged defaults with the document's settings merged over them, section by section."""

        current = self._document.unwrap() if self._document is not None else {}
        return {
            section: {**table, **_table_or_empty(current.get(section))} for section, table in self._defaults.items()
        }

    def _require_document(self) -> TOMLDocument:
        if self._document is None:
            raise NotTomlError(self.path)
        return self._document


# endregion


# region Helpers


def _help_lines(text: str) -> dict[str, str]:
    """``{"section.name": explanation}``, the explanation being the comment lines just above each setting, joined."""

    found: dict[str, str] = {}
    section = ""
    comments: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.strip("[]")
            comments = []
        elif stripped.startswith("#"):
            comments.append(stripped.lstrip("#").strip())
        elif "=" in stripped:
            found[f"{section}.{stripped.split('=')[0].strip()}"] = " ".join(comments)
            comments = []
        else:
            comments = []
    return found


def _flatten(settings: dict[str, Any]) -> dict[str, Any]:
    """``{"section.name": value}`` for every setting in a table, and ``{"section": value}`` for anything else."""

    flat: dict[str, Any] = {}
    for section, value in settings.items():
        if isinstance(value, dict):
            flat.update({f"{section}.{name}": item for name, item in value.items()})
        else:
            flat[section] = value
    return flat


def _table_or_empty(value: Any) -> dict[str, Any]:
    """``value`` if it is a table, else an empty one (a section set to a plain value has no settings to keep)."""

    return value if isinstance(value, dict) else {}


def _show(value: Any) -> str:
    """A value as TOML-like text: ``true``, ``0.8``, ``"text"``, ``["a", "b"]``."""

    return json.dumps(value, ensure_ascii=False)


def _write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` through a temporary file in the same folder, renamed into place."""

    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


# endregion
