"""A library's own description of its folders: the keyword hints and filename rules that help the rules engine.

This lives in ``<library>/.microfiche/microfiche-library.json``, apart from ``microfiche-config.toml``: the
config holds *settings* (how sure to be, which AI to ask), this file holds *data about this library's folders*.

The folders stay the authority on what exists (docs/development/architecture.md, section 1). An entry with no
folder is never filed into, and the file never creates or removes a folder.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

from microfiche.core.config import ConfigError, describe_validation_errors
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

# region Constants and types

LIBRARY_FILENAME = "microfiche-library.json"
# A node with this name stands for any folder at its level. It is illegal in a Windows file name and very rare
# elsewhere, so it cannot be mistaken for a real folder.
WILDCARD = "*"

# Text from a hand-edited file: surrounding space is dropped and an empty value is refused (an empty hint
# would match every document).
_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# A folder name: no path separators.
_FolderName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[^/\\]+$")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FilingRule(_Model):
    """A filename rule: a file whose name matches ``pattern`` belongs in the folder that holds the rule."""

    pattern: _Text = Field(
        description="A glob matched against the file name only (never the folder path), ignoring case. "
        "'requirements*.docx' matches one kind of file; 'meeting-notes*' matches any extension."
    )


class FolderNode(_Model):
    """One folder in the library, and what helps match it.

    A top-level node is a group; its children are that group's categories, and so on down to the library's
    depth. A node named ``*`` stands for any folder at its level and only holds children.
    """

    name: _FolderName = Field(
        description="The folder's name exactly as it is on disk, including any number prefix, such as "
        "'Project Phoenix' or '01 Requirements'. Case is ignored when matching. "
        "'*' means any folder at this level, so what it holds applies to all of them."
    )
    description: _Text | None = Field(
        default=None,
        description="A note about what belongs in this folder, for people reading the file. It is not used for "
        "matching and is not sent to any AI.",
    )
    hints: list[_Text] = Field(
        default_factory=list,
        description="Keywords whose appearance in a document (any case) suggests this folder. "
        "Hints are not inherited by the folders below.",
    )
    rules: list[FilingRule] = Field(
        default_factory=list,
        description="Filename rules for this folder, checked before the keyword hints.",
    )
    children: list[FolderNode] = Field(
        default_factory=list,
        description="The folders one level down.",
    )

    @model_validator(mode="after")
    def _wildcard_holds_only_children(self) -> FolderNode:
        if self.name == WILDCARD and (self.hints or self.rules):
            raise WildcardWithDataError
        _reject_duplicates(child.name for child in self.children)
        return self

    def height(self) -> int:
        """How many levels this node and everything below it span (1 for a node with no children)."""

        return 1 + max((child.height() for child in self.children), default=0)


class LibraryFile(_Model):
    """The contents of ``microfiche-library.json``.

    A missing file means no hints and no rules: documents are then matched on folder names alone.
    """

    schema_ref: str | None = Field(
        default=None,
        alias="$schema",
        description="The JSON Schema for this file, so an editor can validate and complete it.",
    )
    groups: list[FolderNode] = Field(
        default_factory=list,
        description="The library's top-level folders. Their children are the categories, and so on.",
    )

    @model_validator(mode="after")
    def _group_names_are_unique(self) -> LibraryFile:
        _reject_duplicates(group.name for group in self.groups)
        return self

    def height(self) -> int:
        """How many levels the file describes (0 for an empty file); it may not exceed the library's depth."""

        return max((group.height() for group in self.groups), default=0)

    def hints_for(self, group: str, category: str) -> list[str]:
        """The keyword hints for ``group``/``category``, most specific first.

        That is the entry for the group and category by name, then a ``*`` group's entry for the category,
        then the group's ``*`` category entry, then ``*`` for both. Repeats are dropped.
        """

        hints = (hint for node, _ in _matching(self.groups, (group, category)) for hint in node.hints)
        return list(dict.fromkeys(hints))

    def group_hints_for(self, group: str) -> list[str]:
        """The keyword hints for the group folder ``group`` itself, which a flat library matches on."""

        hints = (hint for node, _ in _matching(self.groups, (group,)) for hint in node.hints)
        return list(dict.fromkeys(hints))

    def group_rules_for(self, groups: list[str]) -> list[dict[str, str]]:
        """The filename rules held by the group entries of ``groups``, in the shape ``RulesEngine`` takes.

        Each rule's ``target`` is the group, in the order the entries have in the file.
        """

        return [
            {"pattern": rule.pattern, "target": group}
            for node in self.groups
            for group in groups
            if node.name.casefold() == group.casefold()
            for rule in node.rules
        ]

    def rules_for(self, group: str, categories: list[str]) -> list[dict[str, str]]:
        """The filename rules that apply within ``group``, in the shape ``RulesEngine`` takes.

        Each rule's ``target`` is the category it files into. The most specific entry's rules come first; within
        the same specificity they keep the order they have in the file, as the old single list of rules did.
        """

        position = {id(node): index for index, node in enumerate(_walk(self.groups))}
        found = [
            (tier, position[id(node)], rule, category)
            for category in categories
            for node, tier in _matching(self.groups, (group, category))
            for rule in node.rules
        ]
        found.sort(key=lambda item: (item[0], item[1]))  # stable, so a node's own rules stay in order
        return [{"pattern": rule.pattern, "target": category} for _, _, rule, category in found]


# endregion


# region Errors


class DuplicateFolderError(ValueError):
    """Raised when two sibling entries name the same folder, so it is unclear which one applies."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"folder {name!r} is listed more than once at the same level")


class WildcardWithDataError(ValueError):
    """Raised when a ``*`` entry carries hints or rules: it stands for many folders, so they would match all."""

    def __init__(self) -> None:
        super().__init__(
            f"an entry named {WILDCARD!r} stands for many folders, so it cannot hold hints or rules; "
            "put them on the folders inside it"
        )


class LibraryFileNotUtf8Error(ConfigError):
    """Raised when the library file cannot be read as UTF-8 text."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"Library file error: {path}: the file is not valid UTF-8 text")


class LibraryFileTooDeepError(ConfigError):
    """Raised when the file describes more levels of folders than the library's ``depth`` allows."""

    def __init__(self, path: Path, levels: int, depth: int) -> None:
        self.levels = levels
        self.depth = depth
        super().__init__(
            f"Library file error: {path}: it describes {levels} levels of folders, but the library's "
            f"depth is {depth} ([library_structure] depth in microfiche-config.toml); "
            "remove the entries below the top level, or raise the depth"
        )


# endregion


# region Public API


def load_library_file(state_dir: Path, depth: int) -> LibraryFile:
    """Read the library file in ``state_dir`` (the library's ``.microfiche/`` folder).

    A missing file is an empty one, so documents are matched on folder names alone. Anything that is
    present is validated, so a misspelt key or a folder entry nested too deep is an error rather than
    being ignored.

    Args:
        state_dir: The folder holding ``microfiche-library.json``.
        depth: How many levels the library has, from ``[library_structure] depth``.

    Returns:
        The validated file.

    Raises:
        ConfigError: If the file is not valid UTF-8 JSON, is not a valid library file, or describes more
            levels than ``depth``. The message names the file and every problem.
    """

    path = state_dir / LIBRARY_FILENAME
    if not path.is_file():
        return LibraryFile()
    try:
        library_file = LibraryFile.model_validate_json(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as err:
        raise LibraryFileNotUtf8Error(path) from err
    except ValidationError as err:
        raise ConfigError(
            describe_validation_errors(path, err, title="Library file error", unknown=("key", "key"))
        ) from err
    if library_file.height() > depth:
        raise LibraryFileTooDeepError(path, library_file.height(), depth)
    return library_file


def json_schema() -> dict[str, Any]:
    """The JSON Schema for the library file, for editors to validate and complete it.

    ``microfiche/microfiche-library.schema.json`` is this, written out; a test fails if it goes stale.

    Returns:
        The schema as plain data.
    """

    schema = LibraryFile.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "microfiche library file"
    return schema


# endregion


# region Helpers


def _reject_duplicates(names: Iterator[str]) -> None:
    seen: set[str] = set()
    for name in names:
        key = name.casefold()  # folders differ only by case on some file systems
        if key in seen:
            raise DuplicateFolderError(name)
        seen.add(key)


def _walk(nodes: list[FolderNode]) -> Iterator[FolderNode]:
    """Every node in file order, each parent before its children."""

    for node in nodes:
        yield node
        yield from _walk(node.children)


def _matching(
    nodes: list[FolderNode], path: tuple[str, ...], tier: tuple[bool, ...] = ()
) -> Iterator[tuple[FolderNode, tuple[bool, ...]]]:
    """The nodes at the end of ``path`` with how specific each match is, a folder's own entry before ``*``.

    The tier has one flag per level, ``False`` where the entry names the folder and ``True`` where it is ``*``,
    so sorting tiers puts the most specific first.
    """

    head, *rest = path
    for is_wildcard, wanted in ((False, head.casefold()), (True, WILDCARD)):
        for node in nodes:
            if node.name.casefold() == wanted:
                if rest:
                    yield from _matching(node.children, tuple(rest), (*tier, is_wildcard))
                else:
                    yield node, (*tier, is_wildcard)


# endregion
