"""Applies naming convention rules to filenames before filing."""

from __future__ import annotations

import re


def apply_naming_rules(filename: str, rules: dict[str, str]) -> str:
    """Apply simple find/replace naming rules (regex pattern -> replacement) to a filename.

    ``rules`` maps a regex pattern to its replacement, applied in iteration order. An empty
    ``rules`` mapping (the MVP default, see microfiche-config/naming_rules.yaml) leaves the filename
    untouched.
    """

    for pattern, replacement in rules.items():
        filename = re.sub(pattern, replacement, filename)
    return filename
