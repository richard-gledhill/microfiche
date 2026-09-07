"""Parses and updates the library's canonical TagIndex.md tag vocabulary."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_TAG_LINE_RE = re.compile(r"^\s*-\s*#(\S+)")
_PROPOSED_HEADING = "## Proposed"


@dataclass
class TagIndex:
    """The canonical tag vocabulary defined in a library's TagIndex.md, plus any tags proposed
    (but not yet promoted) by microfiche itself - see the "suggest-only" tag governance decision
    in docs/prd/20260907_microfiche_architecture_v2.md."""

    path: Path
    canonical_tags: set[str] = field(default_factory=set)
    proposed_tags: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, path: Path) -> TagIndex:
        if not path.exists():
            return cls(path=path)

        canonical: set[str] = set()
        proposed: set[str] = set()
        in_proposed_section = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("## "):
                in_proposed_section = line.strip() == _PROPOSED_HEADING
                continue
            match = _TAG_LINE_RE.match(line)
            if match:
                (proposed if in_proposed_section else canonical).add(match.group(1))

        return cls(path=path, canonical_tags=canonical, proposed_tags=proposed)

    def add_proposed(self, tag: str) -> None:
        """Record a new tag with no close canonical match, for later human review/promotion."""

        if tag not in self.canonical_tags:
            self.proposed_tags.add(tag)

    def save(self) -> None:
        lines = ["# Tag Index", "", *[f"- #{tag}" for tag in sorted(self.canonical_tags)]]
        if self.proposed_tags:
            lines += ["", _PROPOSED_HEADING, "", *[f"- #{tag}" for tag in sorted(self.proposed_tags)]]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
