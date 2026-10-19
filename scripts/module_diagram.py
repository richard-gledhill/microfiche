"""Regenerate the import graph in docs/development/architecture/module-diagram.md from the source.

The first Mermaid diagram in that file shows which module imports which. This script reads every ``import``
statement in ``packages/core/src/microfiche/core`` and ``packages/cli/src/microfiche/cli``, then rewrites only the graph's edges and
nodes: it keeps the labels and annotations already in the diagram, adds a node for each new module, drops the
node (and edges) of each deleted one, and updates the "as of" date when anything changed. The second diagram
(the runtime data flow) and all the prose are left alone.

Run it with ``make module-diagram``. ``--check`` reports what is out of date without writing anything.
"""

from __future__ import annotations

import argparse
import ast
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# region Constants and types

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_PATH = REPO_ROOT / "docs" / "development" / "architecture" / "module-diagram.md"
PACKAGE_ROOTS: dict[str, Path] = {
    "core": REPO_ROOT / "packages" / "core" / "src" / "microfiche" / "core",
    "cli": REPO_ROOT / "packages" / "cli" / "src" / "microfiche" / "cli",
}

# A source folder (relative to its package's src folder) -> the diagram subgraph that shows it, and the prefix of
# its node ids. A new folder needs an entry here before it can appear in the diagram.
SUBGRAPHS: dict[str, tuple[str, str]] = {
    "cli": ("CLI", "cli"),
    "core": ("CORE", "core"),
    "core/models": ("MODELS", "m"),
    "core/parsers": ("PARSERS", "p"),
    "core/rules": ("RULES", "r"),
    "core/ai": ("AI", "a"),
    "core/library": ("LIBRARY", "l"),
    "core/utils": ("UTILS", "u"),
}
SUBGRAPHS_BY_NAME: dict[str, str] = {name: folder for folder, (name, _) in SUBGRAPHS.items()}

_AS_OF = re.compile(r"as of \d{4}-\d{2}-\d{2}")
_EDGE = re.compile(r"^\s+(\w+) --> (\w+)$")
_NODE = re.compile(r'^\s+(\w+)\["([^"]*)"\]$')
_SUBGRAPH = re.compile(r'^\s+subgraph (\w+)\["([^"]*)"\]$')
_FENCE = "```"


@dataclass
class Changes:
    """What regenerating the graph changed, by node id."""

    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    added_edges: list[tuple[str, str]] = field(default_factory=list)
    removed_edges: list[tuple[str, str]] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.added_nodes or self.removed_nodes or self.added_edges or self.removed_edges)

    def describe(self) -> list[str]:
        """One line per change, ``+`` for something added and ``-`` for something removed."""

        return [
            *(f"+ node {node}" for node in self.added_nodes),
            *(f"- node {node}" for node in self.removed_nodes),
            *(f"+ {source} --> {target}" for source, target in self.added_edges),
            *(f"- {source} --> {target}" for source, target in self.removed_edges),
        ]


@dataclass
class _Node:
    id: str
    label: str
    folder: str

    @property
    def module(self) -> str:
        return f"{self.folder}/{self.label.split()[0]}"


# endregion


# region Errors


class UnknownFolderError(ValueError):
    """Raised when a source folder or diagram subgraph has no entry in ``SUBGRAPHS``."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"no diagram subgraph is configured for {name!r}: add it to SUBGRAPHS in scripts/module_diagram.py"
        )


class NoGraphError(ValueError):
    """Raised when the diagram file has no Mermaid block to update."""

    def __init__(self) -> None:
        super().__init__("the diagram file has no ```mermaid block to update")


# endregion


# region Public API


def import_edges(roots: Mapping[str, Path]) -> dict[str, set[str]]:
    """Find every import of one project module by another.

    Every ``import`` statement counts, wherever it sits (inside a function or under ``TYPE_CHECKING`` too). Imports of
    the standard library, other packages, or modules that don't exist are ignored, as is a module importing itself.

    Args:
        roots: Each package's name mapped to its source folder, such as ``core`` to ``packages/core/src/microfiche/core``.

    Returns:
        The importing module's path (like ``core/ai/factory.py``, relative to the ``microfiche`` folder both packages
        install into) mapped to
        the paths of the project modules it imports.
    """

    bases = {name: root.parent for name, root in roots.items()}
    edges: dict[str, set[str]] = {}
    for file in _source_files(roots):
        source = _relative(file, bases)
        targets = {target for target in _imports_of(file, bases) if target != source}
        if targets:
            edges[source] = targets
    return edges


def update_diagram(text: str, roots: Mapping[str, Path], today: date) -> tuple[str, Changes]:
    """Bring the first Mermaid diagram in ``text`` in step with the source.

    Args:
        text: The diagram file's contents.
        roots: Each package's name mapped to its source folder.
        today: The date to write in the "as of" line when the graph changed.

    Returns:
        The updated text, and what changed. If nothing changed in the graph the text is unchanged too.

    Raises:
        NoGraphError: If ``text`` has no Mermaid block.
        UnknownFolderError: If a module needs a node in a folder that has no entry in ``SUBGRAPHS``.
    """

    crlf = "\r\n" in text
    text = text.replace("\r\n", "\n")
    start = text.find(_FENCE + "mermaid")
    if start < 0:
        raise NoGraphError
    end = text.index(_FENCE, start + len(_FENCE))
    lines = text[start:end].split("\n")

    nodes, old_edges = _read_graph(lines)
    edges = import_edges(roots)
    existing = {node.module for node in nodes if _exists(node.module, roots)}
    gone = {node.id for node in nodes if node.module not in existing}
    new_modules = sorted(_wanted_modules(roots, edges) - existing)
    ids = {node.module: node.id for node in nodes if node.id not in gone}
    ids.update({module: _node_id(module) for module in new_modules})

    edges_by_id = {
        ids[source]: {ids[t] for t in targets if t in ids} for source, targets in edges.items() if source in ids
    }
    groups = _edge_groups(old_edges, edges_by_id)
    changes = _changes(old_edges, groups, gone, [ids[module] for module in new_modules])
    graph = "\n".join(_render(lines, gone, new_modules, ids, groups))

    updated = text[:start] + graph + text[end:]
    if changes:
        updated = _AS_OF.sub(f"as of {today.isoformat()}", updated, count=1)
    return (updated.replace("\n", "\r\n") if crlf else updated), changes


def main(
    argv: Sequence[str] | None = None,
    *,
    roots: Mapping[str, Path] = PACKAGE_ROOTS,
    diagram: Path = DIAGRAM_PATH,
    today: date | None = None,
) -> int:
    """Regenerate the diagram, or with ``--check`` only say whether it is out of date.

    Args:
        argv: Command-line arguments; ``--check`` reports without writing.
        roots: Each package's name mapped to its source folder.
        diagram: The diagram file.
        today: The date for the "as of" line; defaults to today.

    Returns:
        0 on success (and for ``--check`` when the diagram is current), 1 when ``--check`` finds it out of date.
    """

    parser = argparse.ArgumentParser(description="Regenerate the import graph in the module diagram.")
    parser.add_argument("--check", action="store_true", help="report what is out of date without writing")
    args = parser.parse_args(argv)

    original = diagram.read_bytes().decode("utf-8")
    updated, changes = update_diagram(original, roots, today or date.today())
    for line in changes.describe():
        print(line)
    if not changes:
        print(f"{diagram.name} is up to date")
        return 0
    if args.check:
        print(f"{diagram.name} is out of date: run `make module-diagram`")
        return 1
    diagram.write_bytes(updated.encode("utf-8"))
    print(f"Updated {diagram}")
    return 0


# endregion


# region Helpers


def _source_files(roots: Mapping[str, Path]) -> list[Path]:
    return sorted(file for root in roots.values() for file in root.rglob("*.py") if "__pycache__" not in file.parts)


def _relative(file: Path, bases: Mapping[str, Path]) -> str:
    return next(file.relative_to(base).as_posix() for base in bases.values() if base in file.parents)


def _exists(module: str, roots: Mapping[str, Path]) -> bool:
    package = module.split("/")[0]
    return package in roots and (roots[package].parent / module).is_file()


def _imports_of(file: Path, bases: Mapping[str, Path]) -> Iterable[str]:
    for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                # `from microfiche.core.models import document` names a module; `from microfiche.core.parsers import is_supported` a name in one
                target = _resolve(f"{node.module}.{alias.name}", bases) or _resolve(node.module, bases)
                if target:
                    yield target
        elif isinstance(node, ast.Import):
            yield from (target for alias in node.names if (target := _resolve(alias.name, bases)))


def _resolve(dotted: str, bases: Mapping[str, Path]) -> str | None:
    """The path of the project module a dotted name refers to, or ``None`` if it isn't one."""

    parts = dotted.split(".")
    if parts[0] == "microfiche":  # both packages install inside the microfiche namespace: microfiche.core.filer
        parts = parts[1:]
    base = bases.get(parts[0]) if parts else None
    if base is None:
        return None
    path = base.joinpath(*parts)
    for candidate in (path.with_suffix(".py"), path / "__init__.py"):
        if candidate.is_file():
            return candidate.relative_to(base).as_posix()
    return None


def _wanted_modules(roots: Mapping[str, Path], edges: Mapping[str, set[str]]) -> set[str]:
    """Modules that belong in the diagram: every module, but a package ``__init__`` only if something imports it."""

    bases = {name: root.parent for name, root in roots.items()}
    mentioned = set(edges) | {target for targets in edges.values() for target in targets}
    modules = {_relative(file, bases) for file in _source_files(roots)}
    return {module for module in modules if not module.endswith("/__init__.py") or module in mentioned}


def _node_id(module: str) -> str:
    folder, filename = module.rsplit("/", 1)
    if folder not in SUBGRAPHS:
        raise UnknownFolderError(folder)
    return f"{SUBGRAPHS[folder][1]}_{filename.removesuffix('.py').strip('_')}"


def _read_graph(lines: Sequence[str]) -> tuple[list[_Node], dict[str, list[str]]]:
    """The diagram's nodes, and its edges in the order they are written."""

    nodes: list[_Node] = []
    edges: dict[str, list[str]] = {}
    folder: str | None = None
    for line in lines:
        subgraph = _SUBGRAPH.match(line)
        if subgraph:
            folder = _folder_of(subgraph.group(1))
            continue
        node = _NODE.match(line)
        if node and folder is not None:
            nodes.append(_Node(node.group(1), node.group(2), folder))
        edge = _EDGE.match(line)
        if edge:
            edges.setdefault(edge.group(1), []).append(edge.group(2))
    return nodes, edges


def _folder_of(subgraph_name: str) -> str:
    if subgraph_name not in SUBGRAPHS_BY_NAME:
        raise UnknownFolderError(subgraph_name)
    return SUBGRAPHS_BY_NAME[subgraph_name]


def _edge_groups(old: Mapping[str, list[str]], current: Mapping[str, set[str]]) -> dict[str, list[str]]:
    """The edges to write: the existing order kept, new edges after it in sorted order."""

    groups: dict[str, list[str]] = {}
    for source in [*old, *sorted(set(current) - set(old))]:
        wanted = current.get(source, set())
        kept = [target for target in old.get(source, []) if target in wanted]
        targets = kept + sorted(wanted - set(kept))
        if targets:
            groups[source] = targets
    return groups


def _changes(
    old: Mapping[str, list[str]], groups: Mapping[str, list[str]], gone: set[str], added_nodes: list[str]
) -> Changes:
    before = [(source, target) for source, targets in old.items() for target in targets]
    after = [(source, target) for source, targets in groups.items() for target in targets]
    return Changes(
        added_nodes=added_nodes,
        removed_nodes=sorted(gone),
        added_edges=[edge for edge in after if edge not in set(before)],
        removed_edges=[edge for edge in before if edge not in set(after)],
    )


def _render(
    lines: Sequence[str],
    gone: set[str],
    new_modules: Sequence[str],
    ids: Mapping[str, str],
    groups: Mapping[str, list[str]],
) -> list[str]:
    """The graph's lines with removed nodes dropped, new nodes added, and the edges rewritten."""

    edge_rows = [i for i, line in enumerate(lines) if _EDGE.match(line)]
    first = edge_rows[0] if edge_rows else _end_of_body(lines)
    last = edge_rows[-1] if edge_rows else first - 1
    present = {_folder_of(match.group(1)) for line in lines if (match := _SUBGRAPH.match(line))}

    by_folder: dict[str, list[str]] = {}
    for module in new_modules:
        folder, filename = module.rsplit("/", 1)
        by_folder.setdefault(folder, []).append(f'        {ids[module]}["{filename}"]')

    head = _drop_and_add_nodes(lines[:first], gone, {f: rows for f, rows in by_folder.items() if f in present})
    head = _add_subgraphs(head, {f: rows for f, rows in by_folder.items() if f not in present})
    return [*head, *_edge_lines(groups), *lines[last + 1 :]]


def _end_of_body(lines: Sequence[str]) -> int:
    return len(lines) - 1 if lines and lines[-1] == "" else len(lines)


def _drop_and_add_nodes(head: Sequence[str], gone: set[str], additions: Mapping[str, list[str]]) -> list[str]:
    out: list[str] = []
    folder: str | None = None
    for line in head:
        subgraph = _SUBGRAPH.match(line)
        node = _NODE.match(line)
        if subgraph:
            folder = _folder_of(subgraph.group(1))
        elif node and node.group(1) in gone:
            continue
        elif line.strip() == "end" and folder is not None:
            out.extend(additions.get(folder, []))
            folder = None
        out.append(line)
    return out


def _add_subgraphs(head: list[str], missing: Mapping[str, list[str]]) -> list[str]:
    """Add a subgraph for each folder the diagram doesn't show yet, after the last one."""

    if not missing:
        return head
    blocks: list[str] = []
    for folder, rows in sorted(missing.items()):
        if folder not in SUBGRAPHS:
            raise UnknownFolderError(folder)
        blocks += ["", f'    subgraph {SUBGRAPHS[folder][0]}["{folder}"]', *rows, "    end"]
    ends = [i for i, line in enumerate(head) if line.strip() == "end"]
    at = ends[-1] + 1 if ends else len(head)
    return [*head[:at], *blocks, *head[at:]]


def _edge_lines(groups: Mapping[str, list[str]]) -> list[str]:
    rows: list[str] = []
    for index, (source, targets) in enumerate(groups.items()):
        if index:
            rows.append("")
        rows.extend(f"    {source} --> {target}" for target in targets)
    return rows


if __name__ == "__main__":
    raise SystemExit(main())


# endregion
