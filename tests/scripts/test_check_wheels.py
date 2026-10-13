"""Tests for the release wheel checker: it must refuse any set of wheels that could not be installed as a release."""

import importlib.util
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

# region Test helpers


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_wheels.py"

_spec = importlib.util.spec_from_file_location("check_wheels", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
check_wheels = importlib.util.module_from_spec(_spec)
sys.modules["check_wheels"] = check_wheels
_spec.loader.exec_module(check_wheels)


def _wheel(
    dist: Path, name: str, version: str = "0.1.6", *, requires: tuple[str, ...] = (), files: tuple[str, ...] = ()
) -> Path:
    """Write a minimal wheel: the metadata, the entry point for ``cli``, and any extra ``files``."""

    path = dist / f"{name}-{version}-py3-none-any.whl"
    metadata = f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n"
    metadata += "".join(f"Requires-Dist: {requirement}\n" for requirement in requires)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
        if name == "cli":
            archive.writestr(
                f"{name}-{version}.dist-info/entry_points.txt", "[console_scripts]\nmicrofiche = cli:main\n"
            )
        for filename in files:
            archive.writestr(filename, "")
    return path


def _release(dist: Path, version: str = "0.1.6") -> None:
    """A correct pair of wheels."""

    _wheel(dist, "core", version, files=(check_wheels.DEFAULTS_FILE,))
    _wheel(dist, "cli", version, requires=("typer", f"core=={version}"))


# endregion


# region check_wheels


def test_check_wheels_correct_pair_has_no_problems(tmp_path: Path) -> None:
    _release(tmp_path)

    assert check_wheels.check_wheels(tmp_path, "v0.1.6") == []


def test_check_wheels_ignores_the_root_wheel(tmp_path: Path) -> None:
    _release(tmp_path)
    _wheel(tmp_path, "microfiche", "0.0.1")  # the workspace root builds a wheel too; it is not released

    assert check_wheels.check_wheels(tmp_path) == []


def test_check_wheels_missing_wheel_reported(tmp_path: Path) -> None:
    _wheel(tmp_path, "core", files=(check_wheels.DEFAULTS_FILE,))

    assert check_wheels.check_wheels(tmp_path) == [f"no cli wheel in {tmp_path}"]


def test_check_wheels_two_wheels_of_one_package_reported(tmp_path: Path) -> None:
    _release(tmp_path)
    _wheel(tmp_path, "core", "0.1.5", files=(check_wheels.DEFAULTS_FILE,))  # left over from an earlier build

    assert check_wheels.check_wheels(tmp_path) == [f"more than one core wheel in {tmp_path}"]


def test_check_wheels_versions_differ_reported(tmp_path: Path) -> None:
    _wheel(tmp_path, "core", "0.1.5", files=(check_wheels.DEFAULTS_FILE,))
    _wheel(tmp_path, "cli", "0.1.6", requires=("core==0.1.6",))

    problems = check_wheels.check_wheels(tmp_path)

    assert any("must release together" in problem for problem in problems)


def test_check_wheels_unpinned_core_reported(tmp_path: Path) -> None:
    _wheel(tmp_path, "core", files=(check_wheels.DEFAULTS_FILE,))
    _wheel(tmp_path, "cli", requires=("core",))

    problems = check_wheels.check_wheels(tmp_path)

    assert len(problems) == 1
    assert "does not require core==0.1.6 exactly" in problems[0]


def test_check_wheels_spaced_pin_accepted(tmp_path: Path) -> None:
    _wheel(tmp_path, "core", files=(check_wheels.DEFAULTS_FILE,))
    _wheel(tmp_path, "cli", requires=("core == 0.1.6",))

    assert check_wheels.check_wheels(tmp_path) == []


def test_check_wheels_defaults_file_missing_reported(tmp_path: Path) -> None:
    _wheel(tmp_path, "core")
    _wheel(tmp_path, "cli", requires=("core==0.1.6",))

    assert check_wheels.check_wheels(tmp_path) == [f"the core wheel does not contain {check_wheels.DEFAULTS_FILE}"]


def test_check_wheels_tag_mismatch_reported(tmp_path: Path) -> None:
    _release(tmp_path)

    assert check_wheels.check_wheels(tmp_path, "v0.1.7") == [
        "the wheels are version 0.1.6, which is not the tag v0.1.7"
    ]


# endregion


# region main


def test_main_exit_code_follows_problems(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_wheels.main([str(tmp_path)]) == 1
    assert "error: no core wheel" in capsys.readouterr().out

    _release(tmp_path)

    assert check_wheels.main([str(tmp_path), "--tag", "v0.1.6"]) == 0
    assert "ok: cli-0.1.6" in capsys.readouterr().out


# endregion


# region Lockstep in the source


def _project_table(relative: str) -> dict[str, object]:
    document = tomllib.loads((_REPO_ROOT / relative).read_text(encoding="utf-8"))
    project = document["project"]
    assert isinstance(project, dict)
    return project


def test_package_versions_core_cli_root_all_equal() -> None:
    versions = {
        relative: _project_table(relative)["version"]
        for relative in ("pyproject.toml", "packages/core/pyproject.toml", "packages/cli/pyproject.toml")
    }

    assert len(set(versions.values())) == 1, f"core, cli and the root must release together: {versions}"


def test_cli_pins_core_to_its_own_version() -> None:
    cli = _project_table("packages/cli/pyproject.toml")
    dependencies = cli["dependencies"]
    assert isinstance(dependencies, list)

    pins = [
        dependency.replace(" ", "") for dependency in dependencies if dependency.replace(" ", "").startswith("core")
    ]

    assert pins == [f"core=={cli['version']}"]


# endregion
