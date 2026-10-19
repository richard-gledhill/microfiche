# Constraints

The measured, tool-enforced quality bar for microfiche. Read it before writing code. The judgement-based style guide is
[conventions.md](conventions.md); a rule a tool checks belongs here.

Don't change this file without asking, and never weaken it to make a change pass.

## Gates

A change is done only when both pass on a clean tree:

- `make check`: `uv lock --locked`, `pre-commit run -a` (file hygiene, `ruff check`, `ruff format`), mypy for Linux and
  then Windows (`--platform linux`, `--platform win32`), and `deptry src` in `packages/core` and then `packages/cli`.
- `make test`: `pytest --doctest-modules --cov --cov-report=term-missing` over `microfiche.core` and `microfiche.cli`,
  with the coverage floor below.

`make check` only sees tracked files: `git add -N` new files first. CI runs the suite on Linux and Windows, and `tox`
runs pytest and mypy across Python 3.11 to 3.14.

## Type checking

mypy covers `packages/core/src` and `packages/cli/src` (not tests), configured in the root `pyproject.toml`:
`disallow_untyped_defs`, `disallow_any_unimported`, `no_implicit_optional`, `check_untyped_defs`, `warn_return_any`,
`warn_unused_ignores`. `mypy_path`, `namespace_packages` and `explicit_package_bases` are set because `microfiche` is a
namespace package shared by two source folders.

Code must import and type-check on Linux (CI) and Windows. Some names exist on one only: `stat.IO_REPARSE_TAG_*`,
`ctypes.WinDLL`, `PermissionError.winerror`. Write such constants out, import platform modules inside the function
that uses them, and guard the body with `if sys.platform == "win32":` so mypy skips it elsewhere. `make check` runs
mypy for both platforms for this reason.

## Lint and security

`ruff` config lives only in the root `pyproject.toml`; per-package `pyproject.toml` files carry just their own
dependencies. Line length 120, target Python 3.11. Rule families: `YTT`, `S` (bandit security), `B`, `A`, `C4`, `T10`,
`LOG`, `G`, `SIM`, `I`, `C90` (complexity), `E`, `W`, `F`, `PGH`, `UP`, `RUF`, `TRY`. The only ignores are `E501` and
`E731`, plus `S101` in `tests/`.

## Generated files

A test fails if one of these is stale, so regenerate it after changing its source:

| File | Source | Regenerate with |
|---|---|---|
| `docs/cli-reference.md` | The Typer app's command docstrings and option `help=` text | `make docs-cli` |
| `microfiche/microfiche-library.schema.json` | The library file model (`json_schema()` in `core/library/library_file.py`) | `make library-schema` |

The import graph in [architecture/module-diagram.md](architecture/module-diagram.md) is also generated, by
`make module-diagram`, but no test checks it is current: run it when imports change (`--check` only reports).

## Never silence a check

- Fix the code, not the check.
- No `# type: ignore`, `# noqa`, `SKIP=` or `--no-verify`, and no loosening the mypy, deptry, ruff or pre-commit
  config, unless the owner asks for it.
- Never skip, delete or weaken a test.
- Add or update tests for any behaviour you change.

## Coverage

- Coverage is measured with `pytest-cov`, configured in the root `pyproject.toml` (`[tool.coverage.run]`: the
  `microfiche.core` and `microfiche.cli` packages by name, branch coverage).
- The floor is `fail_under = 95` on the whole of `core` and `cli`, enforced by `make test` and a CI coverage job. The
  measured baseline was 97.6% on Windows. Raise the floor, never lower it, once the Linux figure is known
  ([mvp-followups-prd.md](requirements/mvp-followups-prd.md#release-close-out-stage-6), R3).
