"""The one-way rule between the packages: ``microfiche.core`` must never import ``microfiche.cli``.

deptry cannot enforce this. Both packages live in the one ``microfiche`` namespace, so it has to treat ``microfiche`` as
core's own code, and an import of ``microfiche.cli`` from core then looks like an import of itself.
"""

import ast
from pathlib import Path

import pytest

# region Test helpers


_CORE_SRC = Path(__file__).resolve().parents[2] / "packages" / "core" / "src" / "microfiche" / "core"


def _cli_imports(source: str) -> list[str]:
    """The names this source imports that are in ``microfiche.cli``, however the import is spelt."""

    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names if alias.name.split(".")[:2] == ["microfiche", "cli"]]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            parts = node.module.split(".")
            if parts[:2] == ["microfiche", "cli"]:
                found.append(node.module)
            elif parts == ["microfiche"]:
                found += [f"microfiche.{alias.name}" for alias in node.names if alias.name == "cli"]
    return found


# endregion


# region _cli_imports


@pytest.mark.parametrize(
    "source",
    [
        "import microfiche.cli",
        "import microfiche.cli.display as d",
        "from microfiche.cli import commands",
        "from microfiche.cli.display import render_config",
        "from microfiche import cli",
        "def f():\n    from microfiche.cli.app import app\n",
    ],
)
def test_cli_imports_every_spelling_found(source: str) -> None:
    assert _cli_imports(source) != []


@pytest.mark.parametrize(
    "source",
    [
        "import microfiche.core.filer",
        "from microfiche.core.library import library",
        "from microfiche import core",
        "from . import cli_like",
        "import click",
    ],
)
def test_cli_imports_other_imports_not_found(source: str) -> None:
    assert _cli_imports(source) == []


# endregion


# region The rule


def test_core_never_imports_cli() -> None:
    sources = sorted(_CORE_SRC.rglob("*.py"))
    assert sources  # the path is right, so an empty result below means something

    offenders = {
        path.relative_to(_CORE_SRC).as_posix(): imports
        for path in sources
        if (imports := _cli_imports(path.read_text(encoding="utf-8")))
    }

    assert offenders == {}


# endregion
