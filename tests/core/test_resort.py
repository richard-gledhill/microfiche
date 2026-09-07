"""Tests for the resort (re-review already-filed documents) pipeline."""

from pathlib import Path

from core.config import load_config
from core.resort import run_resort

_REPO_CONFIG_DIR = Path(__file__).resolve().parents[2] / "microfiche-config"


def test_resort_never_scans_the_library_s_own_config_or_logs_folders(tmp_path: Path) -> None:
    """Regression test: .microfiche-config/ and .logs/ are operational folders, not sortable content.

    Uses the actual shipped default exclusions (microfiche-config/exclusions.yaml), not a
    synthetic one, so this catches a regression in the defaults themselves.
    """

    (tmp_path / "Project Phoenix" / "01 Requirements").mkdir(parents=True)
    config_dir = tmp_path / ".microfiche-config"
    config_dir.mkdir()
    (config_dir / "README.md").write_text("Not a project document.", encoding="utf-8")
    (tmp_path / ".logs").mkdir()
    (tmp_path / ".logs" / "notes.md").write_text("Not a project document either.", encoding="utf-8")

    config = load_config(_REPO_CONFIG_DIR)
    proposals = run_resort(tmp_path, config)

    assert proposals == []
