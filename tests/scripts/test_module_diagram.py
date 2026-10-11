"""Tests for the module diagram generator: it rebuilds the import graph from the source and leaves the rest alone."""

import importlib.util
import re
import sys
from datetime import date
from pathlib import Path

import pytest

# region Test helpers


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "module_diagram.py"
_TODAY = date(2026, 10, 11)

_spec = importlib.util.spec_from_file_location("module_diagram", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
module_diagram = importlib.util.module_from_spec(_spec)
sys.modules["module_diagram"] = module_diagram  # dataclasses look their module up here
_spec.loader.exec_module(module_diagram)


def _project(tmp_path: Path, files: dict[str, str]) -> dict[str, Path]:
    """Write ``files`` (paths like ``core/filer.py``) under ``tmp_path`` and return the package roots."""

    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return {"core": tmp_path / "core", "cli": tmp_path / "cli"}


_DIAGRAM = """# Module diagram

Two diagrams, as of 2026-10-08. If this drifts, regenerate it.

## 1. Module import graph

```mermaid
flowchart TD
    subgraph CLI["packages/cli/src/cli"]
        cli_app["app.py"]
    end

    subgraph CORE["core (top level)"]
        core_organizer["organizer.py"]
        core_filer["filer.py (file_batch + rollback_job)"]
    end

    subgraph AI["core/ai"]
        a_llm["llm_classifier.py"]
    end

    cli_app --> core_organizer

    core_organizer --> core_filer
    core_organizer --> a_llm
```

## 2. Data flow

```mermaid
flowchart TD
    Start --> Finish
```

Some closing prose.
"""

_FILES = {
    "cli/app.py": "from core.organizer import run_sort\n",
    "core/organizer.py": "from core.ai.llm_classifier import LLMClassifier\nfrom core.filer import file_batch\n",
    "core/filer.py": "import os\n",
    "core/ai/llm_classifier.py": "from __future__ import annotations\n",
}


def _update(
    tmp_path: Path, files: dict[str, str] | None = None, diagram: str = _DIAGRAM
) -> tuple[str, "module_diagram.Changes"]:
    roots = _project(tmp_path, files if files is not None else _FILES)
    return module_diagram.update_diagram(diagram, roots, _TODAY)


def _edges(text: str) -> set[tuple[str, str]]:
    graph = text.split("```mermaid")[1].split("```")[0]
    return set(re.findall(r"^\s+(\w+) --> (\w+)$", graph, re.MULTILINE))


# endregion


# region import_edges


def test_import_edges_from_import_of_a_module(tmp_path: Path) -> None:
    roots = _project(
        tmp_path, {"core/a.py": "from core.models.document import Document\n", "core/models/document.py": ""}
    )

    assert module_diagram.import_edges(roots) == {"core/a.py": {"core/models/document.py"}}


def test_import_edges_from_package_import_of_a_submodule(tmp_path: Path) -> None:
    roots = _project(tmp_path, {"core/a.py": "from core.models import document\n", "core/models/document.py": ""})

    assert module_diagram.import_edges(roots) == {"core/a.py": {"core/models/document.py"}}


def test_import_edges_from_package_import_of_a_name_targets_the_package_init(tmp_path: Path) -> None:
    roots = _project(
        tmp_path,
        {
            "core/a.py": "from core.parsers import is_supported\n",
            "core/parsers/__init__.py": "def is_supported(): ...\n",
        },
    )

    assert module_diagram.import_edges(roots) == {"core/a.py": {"core/parsers/__init__.py"}}


def test_import_edges_plain_import_statement(tmp_path: Path) -> None:
    roots = _project(tmp_path, {"cli/a.py": "import core.config\n", "core/config.py": ""})

    assert module_diagram.import_edges(roots) == {"cli/a.py": {"core/config.py"}}


def test_import_edges_ignores_external_standard_library_and_missing_modules(tmp_path: Path) -> None:
    roots = _project(
        tmp_path,
        {"core/a.py": "import os\nfrom pathlib import Path\nimport pydantic\nfrom core.missing import thing\n"},
    )

    assert module_diagram.import_edges(roots) == {}


def test_import_edges_counts_imports_inside_functions_and_type_checking(tmp_path: Path) -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from core.b import B\n"
        "def f():\n    from core.c import C\n"
    )
    roots = _project(tmp_path, {"core/a.py": source, "core/b.py": "", "core/c.py": ""})

    assert module_diagram.import_edges(roots) == {"core/a.py": {"core/b.py", "core/c.py"}}


def test_import_edges_ignores_a_module_importing_itself_and_repeats(tmp_path: Path) -> None:
    roots = _project(
        tmp_path,
        {"core/a.py": "from core.a import x\nfrom core.b import y\nfrom core.b import z\n", "core/b.py": ""},
    )

    assert module_diagram.import_edges(roots) == {"core/a.py": {"core/b.py"}}


# endregion


# region update_diagram: edges


def test_update_diagram_current_diagram_has_no_changes(tmp_path: Path) -> None:
    text, changes = _update(tmp_path)

    assert not changes
    assert _edges(text) == _edges(_DIAGRAM)


def test_update_diagram_adds_a_missing_edge(tmp_path: Path) -> None:
    files = {**_FILES, "core/ai/llm_classifier.py": "from core.filer import file_batch\n"}

    text, changes = _update(tmp_path, files)

    assert changes.added_edges == [("a_llm", "core_filer")]
    assert ("a_llm", "core_filer") in _edges(text)


def test_update_diagram_removes_a_stale_edge(tmp_path: Path) -> None:
    files = {**_FILES, "core/organizer.py": "from core.filer import file_batch\n"}

    text, changes = _update(tmp_path, files)

    assert changes.removed_edges == [("core_organizer", "a_llm")]
    assert ("core_organizer", "a_llm") not in _edges(text)


def test_update_diagram_keeps_existing_order_and_appends_new_edges_sorted(tmp_path: Path) -> None:
    files = {**_FILES, "core/ai/llm_classifier.py": "from core.filer import f\nfrom core.organizer import o\n"}

    text, _ = _update(tmp_path, files)

    graph = text.split("```mermaid")[1].split("```")[0]
    ordered = re.findall(r"^\s+(\w+) --> (\w+)$", graph, re.MULTILINE)
    assert ordered == [
        ("cli_app", "core_organizer"),
        ("core_organizer", "core_filer"),
        ("core_organizer", "a_llm"),
        ("a_llm", "core_filer"),
        ("a_llm", "core_organizer"),
    ]


def test_update_diagram_separates_each_importing_modules_edges_with_a_blank_line(tmp_path: Path) -> None:
    text, _ = _update(tmp_path)

    assert "    cli_app --> core_organizer\n\n    core_organizer --> core_filer\n    core_organizer --> a_llm\n" in text


# endregion


# region update_diagram: nodes


def test_update_diagram_keeps_a_nodes_annotated_label(tmp_path: Path) -> None:
    text, _ = _update(tmp_path)

    assert 'core_filer["filer.py (file_batch + rollback_job)"]' in text


def test_update_diagram_adds_a_node_for_a_new_module_inside_its_subgraph(tmp_path: Path) -> None:
    files = {**_FILES, "core/ledger.py": "", "core/filer.py": "from core.ledger import Ledger\n"}

    text, changes = _update(tmp_path, files)

    assert changes.added_nodes == ["core_ledger"]
    assert ("core_filer", "core_ledger") in _edges(text)
    core_start = text.index("subgraph CORE[")
    node = text.index('core_ledger["ledger.py"]')
    assert core_start < node < text.index("subgraph AI[")


def test_update_diagram_node_id_is_the_folders_prefix_and_the_file_name(tmp_path: Path) -> None:
    files = {**_FILES, "core/ai/factory.py": "", "core/organizer.py": "from core.ai.factory import build\n"}

    text, changes = _update(tmp_path, files)

    assert changes.added_nodes == ["a_factory"]
    assert 'a_factory["factory.py"]' in text


def test_update_diagram_package_init_gets_a_node_only_when_something_imports_it(tmp_path: Path) -> None:
    files = {**_FILES, "core/parsers/__init__.py": "", "core/parsers/txt_parser.py": ""}
    unused, _ = _update(tmp_path / "unused", files)
    used, changes = _update(tmp_path / "used", {**files, "core/filer.py": "from core.parsers import read\n"})

    assert "p_init" not in unused
    assert changes.added_nodes == ["p_init", "p_txt_parser"]
    assert 'p_init["__init__.py"]' in used


def test_update_diagram_a_subgraph_missing_from_the_diagram_is_created_before_the_edges(tmp_path: Path) -> None:
    files = {**_FILES, "core/parsers/txt_parser.py": ""}

    text, _ = _update(tmp_path, files)

    assert 'subgraph PARSERS["core/parsers"]' in text
    assert text.index("subgraph PARSERS[") < text.index("    cli_app --> core_organizer")


def test_update_diagram_drops_the_node_and_edges_of_a_deleted_module(tmp_path: Path) -> None:
    files = {key: value for key, value in _FILES.items() if key != "core/filer.py"}
    files["core/organizer.py"] = "from core.ai.llm_classifier import LLMClassifier\n"

    text, changes = _update(tmp_path, files)

    assert changes.removed_nodes == ["core_filer"]
    assert "core_filer" not in text.split("```mermaid")[1].split("```")[0]


def test_update_diagram_a_folder_with_no_configured_subgraph_is_an_error(tmp_path: Path) -> None:
    files = {**_FILES, "core/newpkg/thing.py": ""}

    with pytest.raises(module_diagram.UnknownFolderError, match="core/newpkg"):
        _update(tmp_path, files)


# endregion


# region update_diagram: the rest of the document


def test_update_diagram_sets_the_as_of_date_when_the_graph_changes(tmp_path: Path) -> None:
    text, _ = _update(tmp_path, {**_FILES, "core/ai/llm_classifier.py": "from core.filer import f\n"})

    assert "as of 2026-10-11." in text
    assert "2026-10-08" not in text


def test_update_diagram_keeps_the_as_of_date_when_nothing_changed(tmp_path: Path) -> None:
    text, changes = _update(tmp_path)

    assert not changes
    assert text == _DIAGRAM


def test_update_diagram_leaves_the_other_diagram_and_the_prose_untouched(tmp_path: Path) -> None:
    text, _ = _update(tmp_path, {**_FILES, "core/ai/llm_classifier.py": "from core.filer import f\n"})

    assert text.endswith(
        "## 2. Data flow\n\n```mermaid\nflowchart TD\n    Start --> Finish\n```\n\nSome closing prose.\n"
    )
    assert text.startswith("# Module diagram\n\nTwo diagrams, as of ")


def test_update_diagram_second_run_changes_nothing(tmp_path: Path) -> None:
    files = {**_FILES, "core/ledger.py": "", "core/filer.py": "from core.ledger import Ledger\n"}
    first, _ = _update(tmp_path, files)

    second, changes = _update(tmp_path, files, diagram=first)

    assert second == first
    assert not changes


def test_update_diagram_keeps_windows_line_endings(tmp_path: Path) -> None:
    crlf = _DIAGRAM.replace("\n", "\r\n")
    files = {**_FILES, "core/ai/llm_classifier.py": "from core.filer import f\n"}

    text, _ = _update(tmp_path, files, diagram=crlf)

    assert "\r\n" in text
    assert re.search(r"(?<!\r)\n", text) is None


def test_update_diagram_without_a_mermaid_block_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(module_diagram.NoGraphError):
        _update(tmp_path, diagram="# Module diagram\n\nNo graph here.\n")


# endregion


# region main


def _write_diagram(tmp_path: Path, text: str = _DIAGRAM) -> Path:
    path = tmp_path / "module-diagram.md"
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_main_writes_the_regenerated_diagram(tmp_path: Path) -> None:
    roots = _project(tmp_path, {**_FILES, "core/ai/llm_classifier.py": "from core.filer import f\n"})
    diagram = _write_diagram(tmp_path)

    status = module_diagram.main([], roots=roots, diagram=diagram, today=_TODAY)

    assert status == 0
    assert ("a_llm", "core_filer") in _edges(diagram.read_text(encoding="utf-8"))


def test_main_check_passes_a_current_diagram_and_does_not_write(tmp_path: Path) -> None:
    roots = _project(tmp_path, _FILES)
    diagram = _write_diagram(tmp_path)

    status = module_diagram.main(["--check"], roots=roots, diagram=diagram, today=_TODAY)

    assert status == 0
    assert diagram.read_text(encoding="utf-8") == _DIAGRAM  # the old date is still there: nothing was written


def test_main_check_fails_a_stale_diagram_names_the_difference_and_does_not_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    roots = _project(tmp_path, {**_FILES, "core/ai/llm_classifier.py": "from core.filer import f\n"})
    diagram = _write_diagram(tmp_path)

    status = module_diagram.main(["--check"], roots=roots, diagram=diagram, today=_TODAY)

    assert status == 1
    assert "a_llm --> core_filer" in capsys.readouterr().out
    assert diagram.read_text(encoding="utf-8") == _DIAGRAM


def test_main_prints_what_it_changed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    roots = _project(tmp_path, {**_FILES, "core/ai/llm_classifier.py": "from core.filer import f\n"})
    diagram = _write_diagram(tmp_path)

    module_diagram.main([], roots=roots, diagram=diagram, today=_TODAY)

    assert "+ a_llm --> core_filer" in capsys.readouterr().out


# endregion


# region The real repository


def test_real_source_regenerates_into_a_valid_graph() -> None:
    diagram = (_REPO_ROOT / "docs" / "development" / "module-diagram.md").read_text(encoding="utf-8")

    text, _ = module_diagram.update_diagram(diagram, module_diagram.PACKAGE_ROOTS, _TODAY)

    graph = text.split("```mermaid")[1].split("```")[0]
    nodes = set(re.findall(r'^\s+(\w+)\["', graph, re.MULTILINE))
    assert {name for edge in _edges(text) for name in edge} <= nodes
    assert len(re.findall(r"^\s+subgraph ", graph, re.MULTILINE)) == len(re.findall(r"^\s+end$", graph, re.MULTILINE))


def test_real_source_every_diagram_node_is_a_real_file() -> None:
    diagram = (_REPO_ROOT / "docs" / "development" / "module-diagram.md").read_text(encoding="utf-8")
    text, _ = module_diagram.update_diagram(diagram, module_diagram.PACKAGE_ROOTS, _TODAY)

    graph = text.split("```mermaid")[1].split("```")[0]
    folder = None
    for line in graph.splitlines():
        subgraph = re.match(r'\s+subgraph (\w+)\["', line)
        node = re.match(r'\s+\w+\["([^" ]+)', line)
        if subgraph:
            folder = module_diagram.SUBGRAPHS_BY_NAME[subgraph.group(1)]
        elif node and folder:
            path = _REPO_ROOT / "packages" / folder.split("/")[0] / "src" / folder / node.group(1)
            assert path.is_file(), path


# endregion
