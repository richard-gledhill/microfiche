"""Check that a folder of built wheels is a release microfiche can ship, before it is attached to a GitHub release.

microfiche releases two wheels in lockstep: ``core`` (the engine) and ``cli`` (the command line, which needs it).
A release is only installable if both are there, carry the same version, ``cli`` pins ``core`` to exactly that
version, ``core`` contains the packaged defaults file (without it every library would start with no settings) and
``cli`` installs the ``microfiche`` command. A wheel built from a checkout that gets any of these wrong still builds,
so this script is the check.

Run it on the folder ``uv build --all-packages --wheel -o <dir>`` wrote to::

    python scripts/check_wheels.py <dir> [--tag v0.1.6]

``--tag`` also requires the wheels' version to be the tag's, so a release cannot be cut from the wrong commit. The
exit code is 0 when every check passes and 1 otherwise, with one line per problem.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections.abc import Sequence
from email.parser import Parser
from pathlib import Path

# region Constants and types

DEFAULTS_FILE = "core/defaults/microfiche-config.toml"
RELEASE_PACKAGES = ("core", "cli")
_WHEEL_NAME = re.compile(r"^(?P<name>[A-Za-z0-9_.]+)-(?P<version>[^-]+)-.*\.whl$")

# endregion


# region Public API


def check_wheels(dist: Path, tag: str | None = None) -> list[str]:
    """Return one message per problem with the wheels in ``dist``; an empty list means they can be released.

    Args:
        dist: The folder the wheels were built into.
        tag: The release tag (``v0.1.6``). When given, the wheels' version must be the tag without its ``v``.

    Returns:
        The problems found, in the order they were checked.
    """

    wheels = _find_wheels(dist)
    problems = [f"no {name} wheel in {dist}" for name in RELEASE_PACKAGES if name not in wheels]
    problems += [f"more than one {name} wheel in {dist}" for name in RELEASE_PACKAGES if len(wheels.get(name, [])) > 1]
    if problems:
        return problems

    core, cli = (wheels[name][0] for name in RELEASE_PACKAGES)
    versions = {name: _wheel_version(wheels[name][0]) for name in RELEASE_PACKAGES}
    if versions["core"] != versions["cli"]:
        problems.append(f"core is {versions['core']} but cli is {versions['cli']}: they must release together")
    version = versions["cli"]
    if tag is not None and tag != f"v{version}":
        problems.append(f"the wheels are version {version}, which is not the tag {tag}")
    if f"core=={version}" not in _requirements(cli):
        problems.append(f"cli does not require core=={version} exactly (requires: {', '.join(_requirements(cli))})")
    if DEFAULTS_FILE not in _names(core):
        problems.append(f"the core wheel does not contain {DEFAULTS_FILE}")
    if "microfiche=cli:main" not in _entry_points(cli):
        problems.append("the cli wheel does not install a `microfiche` command (microfiche = cli:main)")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Check the wheels named on the command line, print any problems and return the exit code."""

    parser = argparse.ArgumentParser(description="Check built wheels before they are attached to a release.")
    parser.add_argument("dist", type=Path, help="The folder containing the built wheels.")
    parser.add_argument("--tag", help="The release tag the wheels' version must match, such as v0.1.6.")
    args = parser.parse_args(argv)

    problems = check_wheels(args.dist, args.tag)
    for problem in problems:
        print(f"error: {problem}")
    if not problems:
        released = (path.name for paths in _find_wheels(args.dist).values() for path in paths)
        print(f"ok: {', '.join(sorted(released))}")
    return 1 if problems else 0


# endregion


# region Helpers


def _find_wheels(dist: Path) -> dict[str, list[Path]]:
    """The release packages' wheels in ``dist``, by package name (other wheels, such as the root one, are ignored)."""

    found: dict[str, list[Path]] = {}
    for path in sorted(dist.glob("*.whl")):
        match = _WHEEL_NAME.match(path.name)
        if match and match["name"] in RELEASE_PACKAGES:
            found.setdefault(match["name"], []).append(path)
    return found


def _names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        return archive.namelist()


def _read(wheel: Path, filename: str) -> str:
    """The text of ``<name>-<version>.dist-info/<filename>`` inside ``wheel``, or an empty string if it is missing."""

    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            parts = name.split("/")
            if len(parts) == 2 and parts[0].endswith(".dist-info") and parts[1] == filename:
                return archive.read(name).decode("utf-8")
    return ""


def _wheel_version(wheel: Path) -> str:
    return Parser().parsestr(_read(wheel, "METADATA")).get("Version", "")


def _requirements(wheel: Path) -> list[str]:
    """The wheel's ``Requires-Dist`` entries with spaces removed, so ``core == 0.1.6`` and ``core==0.1.6`` compare equal."""

    return [
        value.replace(" ", "") for value in Parser().parsestr(_read(wheel, "METADATA")).get_all("Requires-Dist", [])
    ]


def _entry_points(wheel: Path) -> list[str]:
    """The wheel's entry-point lines with spaces removed, like ``microfiche=cli:main``."""

    return [line.replace(" ", "") for line in _read(wheel, "entry_points.txt").splitlines()]


# endregion


if __name__ == "__main__":
    sys.exit(main())
