"""Applies naming convention rules to filenames before filing."""

from __future__ import annotations

import re


def apply_naming_rules(filename: str, rules: dict[str, str]) -> str:
    """Apply simple find/replace naming rules (regex pattern -> replacement) to a filename.

    ``rules`` maps a regex pattern to its replacement, applied in iteration order. An empty
    ``rules`` mapping (the MVP default, the ``[naming_rules]`` table in the config) leaves the filename
    untouched.

    Args:
        filename: The file or folder name to rewrite.
        rules: Regex patterns mapped to their replacements.

    Returns:
        The rewritten name.
    """

    for pattern, replacement in rules.items():
        filename = re.sub(pattern, replacement, filename)
    return filename
