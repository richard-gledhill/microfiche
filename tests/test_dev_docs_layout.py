import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
DEV_DOCS = ROOT / "docs" / "development"
SUBFOLDERS = ["requirements", "plan", "plan/archive", "rfcs", "adr", "architecture", "testing", "operations"]


def test_dev_docs_index_readme_exists() -> None:
    assert (DEV_DOCS / "README.md").is_file()


@pytest.mark.parametrize("folder", SUBFOLDERS)
def test_dev_docs_subfolder_readme_exists(folder: str) -> None:
    assert (DEV_DOCS / folder / "README.md").is_file()


@pytest.mark.parametrize("old_path", ["SPEC.md", "tasks"])
def test_dev_docs_old_layout_absent(old_path: str) -> None:
    assert not (DEV_DOCS / old_path).exists()


def test_mkdocs_excludes_development_folder() -> None:
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "exclude_docs: |\n  development/" in text.replace("\r\n", "\n")


def test_adr_dir_points_at_adr_folder() -> None:
    assert (ROOT / ".adr-dir").read_text(encoding="utf-8").strip() == "docs/development/adr"


def test_claude_md_imports_agents_and_conventions() -> None:
    lines = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").split()
    assert lines == ["@AGENTS.md", "@docs/development/conventions.md"]


def test_conventions_md_exists() -> None:
    assert (DEV_DOCS / "conventions.md").is_file()


def test_constraints_md_exists() -> None:
    assert (DEV_DOCS / "constraints.md").is_file()


def test_agents_md_points_at_conventions_without_copying_them() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Read [`docs/development/conventions.md`](docs/development/conventions.md)" in text
    assert "reference `conventions.md` instead of restating code style" in text
    # The conventions live in one place; a summary copy in AGENTS.md would drift.
    assert "**Module layout**" not in text
    assert "**Module layout**" in (DEV_DOCS / "conventions.md").read_text(encoding="utf-8")


def test_contributing_links_to_conventions() -> None:
    assert "docs/development/conventions.md" in (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


def test_agents_md_documents_dev_docs_paths() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Development docs location" in text
    assert "`docs/development/plan/SPEC.md`" in text
    assert "`docs/development/plan/archive/<YYYY-MM-feature>/`" in text
    assert "live in `docs/development/requirements/`" in text
    assert "don't create or copy RFCs into" in text
    assert "`docs/development/constraints.md`" in text
    assert "You may edit and add MkDocs pages" in text


def test_hook_settings_register_guard_script() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    (entry,) = settings["hooks"]["PreToolUse"]
    assert entry["matcher"] == "Write|Edit|MultiEdit"
    assert "guard_docs.py" in entry["hooks"][0]["command"]
    assert (ROOT / ".claude" / "hooks" / "guard_docs.py").is_file()


def test_agents_md_ties_repo_to_its_own_issue_tracking() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Tracking work" in text
    assert "`issue`, `bugfix` or `rfc`" in text
    assert "including the `scratch-cookiecutter-uv` template or any cookiecutter-uv fork" in text
