"""The interactive side of ``microfiche init``: walking through the settings, and the choices it offers.

``microfiche.core.library_init`` does the work (checking the config, editing it, writing it). This module only asks
and shows. Nothing is written while asking.
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import groupby
from typing import Any, Literal

import typer
from microfiche.core.library_init import (
    CLEAR,
    COMMON_SETTINGS,
    ConfigEditor,
    InvalidSettingValueError,
    Setting,
    SettingChange,
)
from rich.console import Console
from rich.markup import escape

# region Constants and types

RevertChoice = Literal["invalid", "all", "leave"]

# endregion


# region Public API


def walk_through(console: Console, editor: ConfigEditor) -> None:
    """Ask about the common settings, then, if wanted, every other setting section by section.

    Each answer is checked as it is given and asked again if it is not valid; Enter keeps the current value. The
    changes are made on ``editor``; the caller shows them and asks before writing.

    Args:
        console: Where to print.
        editor: The config being edited.
    """

    console.print(f"Press Enter to keep a value. Type {CLEAR} to clear a text or list setting.")
    for section, name in COMMON_SETTINGS:
        _ask(console, editor, editor.setting(section, name))
    if not typer.confirm("\nGo through all the other settings?", default=False):
        return
    others = [setting for setting in editor.settings() if (setting.section, setting.name) not in COMMON_SETTINGS]
    for section, settings in groupby(others, key=lambda setting: setting.section):
        if not typer.confirm(f"\nChange settings in [{section}]?", default=False):
            continue
        for setting in settings:
            _ask(console, editor, editor.setting(setting.section, setting.name))


def render_changes(console: Console, changes: Iterable[SettingChange]) -> None:
    """List what would change, one setting per line.

    Args:
        console: Where to print.
        changes: The changes, as ``ConfigEditor.changes`` lists them.
    """

    console.print("\nChanges:")
    for change in changes:
        console.print(f"  {escape(change.key)}: {escape(change.old)} -> {escape(change.new)}", soft_wrap=True)


def ask_revert(console: Console, *, can_keep_valid: bool) -> RevertChoice:
    """Ask how to put an invalid config right.

    Args:
        console: Where to print.
        can_keep_valid: Whether reverting only what is wrong is possible. It is not for a file that is not TOML.

    Returns:
        ``"invalid"`` to revert only the invalid and unknown settings, ``"all"`` to revert everything, or
        ``"leave"`` to change nothing.
    """

    options: dict[str, tuple[str, RevertChoice]] = {}
    if can_keep_valid:
        options["i"] = ("revert only the invalid and unknown settings to their defaults, keeping the rest", "invalid")
    options["a"] = ("revert all settings to the defaults", "all")
    options["l"] = ("leave the file as it is", "leave")
    for key, (label, _) in options.items():
        console.print(f"  ({key}) {label}")
    while True:
        answer = str(typer.prompt("What now?", default="l")).strip().lower()
        if answer in options:
            return options[answer][1]
        console.print(f"  Please answer one of: {', '.join(options)}")


# endregion


# region Helpers


def _ask(console: Console, editor: ConfigEditor, setting: Setting) -> None:
    """Show one setting and ask for a new value until a valid one is given or Enter keeps the current one."""

    console.print(f"\n[bold]{escape(setting.key)}[/bold]: {escape(setting.help)}", soft_wrap=True)
    if not setting.editable:
        console.print(f"  Now {escape(_show(setting.value))}. Edit this one in the file itself.", soft_wrap=True)
        return
    if setting.value != setting.default:
        console.print(f"  The default is {escape(_show(setting.default))}.", soft_wrap=True)
    while True:
        raw = str(typer.prompt(f"  {setting.name} [{_show(setting.value)}]", default="", show_default=False))
        if not raw.strip():
            return
        try:
            editor.set(setting.section, setting.name, editor.parse(setting, raw))
        except InvalidSettingValueError as err:
            console.print(f"  [yellow]{escape(str(err))}[/yellow]", soft_wrap=True)
            continue
        return


def _show(value: Any) -> str:
    """A value as it is typed at a prompt: ``yes``/``no``, a comma-separated list, or ``(empty)``."""

    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "(empty)"
    if value == "":
        return "(empty)"
    return str(value)


# endregion
