# Conventions

The judgement-based style guide for microfiche. Read it before writing code (see [AGENTS.md](../../AGENTS.md)).

[constraints.md](constraints.md) is the measured, enforced bar (gates, type checking, lint, coverage). This file is
the style guide that tools can't check. A new rule belongs here if it is a judgement call, and in `constraints.md` if a
tool enforces it. Don't change either file without asking, and never to make it match code you just wrote.

**Design**
- Prefer deep modules: a small interface with a lot of behaviour behind it.
- Before adding a module, apply the deletion test: if removing it would just move one line into its callers,
  don't add it.
- Locality: each concern lives in one place, so a fix is made once.
- Add a seam (a `Protocol` or swappable adapter) only where something actually varies. One implementation is not a seam.
- Test through the interface and fake at the seams (resolvers, the AI provider). If a test needs to reach past the
  interface, the module is probably the wrong shape.

**Code**
- Docstrings: Google style (`Args:`/`Returns:`/`Raises:`) — `mkdocstrings` renders them for the
  published docs.
- Use the [CONTEXT.md](../../CONTEXT.md) terms in code, docs and commits; add a term there when you
  introduce a domain concept.
- Name a module's logger `_logger = logging.getLogger(__name__)`, among the module's constants below the imports.
  The underscore marks it private: never import another module's logger, so a record is always attributed to the
  module that emitted it. Only `cli` configures logging (handlers and levels); `core` just emits, and
  `core/__init__.py` adds a `NullHandler` to the `microfiche.core` logger and nothing else.
- Lint, type-check and platform rules (`ruff` and mypy config, Linux and Windows) are enforced by tools, so they
  live in [constraints.md](constraints.md).

**Module layout**
- Order a module like this, omitting what it doesn't have:
  1. Module docstring.
  2. Imports: `from __future__`, then standard library, third-party, local (`ruff` sorts them).
  3. Module dunders (`__all__`, `__version__`). These go after the imports, unlike PEP 8, which puts them
     before; it matches `cli/app.py` and `parsers/__init__.py`.
  4. Constants and types: constants, type aliases, `TypeVar`s, `Protocol`s and plain data models (dataclasses,
     Pydantic). Code further down uses them in signatures.
  5. Errors: custom exceptions.
  6. Public API: the functions and classes other modules import. High up, so a reader sees what the module offers first.
  7. Helpers: `_`-prefixed, module-private functions, kept last as implementation detail.
- Order matters only for names used at import time (constants, decorators, default arguments, class bodies):
  those must be defined above their use. A function body can call a helper defined below it.
- In a module of about 150+ lines with at least three of sections 4-7, wrap each in `# region <name>` ...
  `# endregion` (PyCharm and VS Code fold them), using exactly these names: `Constants and types`, `Errors`,
  `Public API`, `Helpers`. Shorter modules get no regions. Don't use `# ---` divider comments.
- A test file mirrors its module. It opens with a `Test helpers` region (shared constants, builders, fakes,
  fixtures; a helper used by one section stays in that section). Then come regions in the module's order with
  the module's names. Inside `Public API`, nest one region per function or class under test, or per behaviour
  when one class has many tests. If the module has no regions, use one top-level region per function, class or
  behaviour. Keep a decorator (`@pytest.mark.parametrize`) with its test, never a region marker between them.

**Tests**
- Use `tmp_path` and `Library(path)`; copy `tests/mock_library` for integration tests. Use fake
  resolvers/providers: no network or Ollama in the suite.
- Lay test files out as described under Module layout.
- Name tests `test_<subject>_<scenario>_<result>`, in the present tense:
  - `<subject>` is the function, class, command or behaviour under test (`file_batch`, `rollback_job`,
    `classify_unit`), so `pytest -k` and a failure's node id say what broke.
  - Leave out articles and filler (a, an, the, is, are, can, be, that, should) and keep it to about 50 characters
    after `test_`.
  - Leave out `<result>` when the scenario already implies it (`test_classify_document_threshold_boundary_inclusive`).
  - Put anything that doesn't fit in a short comment in the test body. A parametrized test's name describes
    the whole family.
  - Don't reuse a name within a file; pytest runs only the last one.

**Docs**
- User docs track the CLI: any change to a command, an option, or a command's status in
  `docs/development/mvp-roadmap.md` must also update
  [docs/how-to-use.md](../how-to-use.md) (the command in both its Bash and PowerShell tabs,
  plus its "Current limitations" list) and the Usage section of [README.md](../../README.md#usage).
- [docs/cli-reference.md](../cli-reference.md) is generated from the Typer app (command docstrings and
  option `help=` text): run `make docs-cli` after changing either. `make docs`/`make docs-test` do it for you,
  and a test fails if the file is stale. Write command docstrings for users, not as API docs - Typer
  prints them as `--help`.
- `microfiche/microfiche-library.schema.json` is generated from the library file model (`json_schema()` in
  `core/library/library_file.py`): run `make library-schema` after changing a field or its description. A test
  fails if the committed file is stale.
- `README.md` and `docs/how-to-use.md` are published; `docs/development/` is not, so link to it
  by GitHub URL.
- Core repository files use ALL-CAPS names (`README.md`, `AGENTS.md`, `CONTEXT.md`); topical docs use lowercase
  (`conventions.md`, `mvp-roadmap.md`). ADRs are `ADR-NNN-title.md` and the current spec is `SPEC.md`.
- Record a deferred or future item once, and link to it. A gap or small postponed item goes in
  [mvp-roadmap.md](mvp-roadmap.md); a feature outside the MVP, or code removed from it, goes in
  [feature-backlog.md](feature-backlog.md). The [README.md](README.md) here says where every other kind of doc goes.
- After a rename or behaviour change, grep the docs for the old name or number.
  `architecture/overview.md`, `mvp-roadmap.md` and `architecture/module-diagram.md` go stale first. Run `make module-diagram` when
  imports change: it rewrites the import graph's nodes and edges from the source (add `--check` to only report),
  and the second, data-flow diagram is still edited by hand.

**Git**
- Branches follow `<type>/<short-description>`, `<type>` being a Conventional Commits type
  (`feat`/`feature`, `fix`, `chore`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
  `revert`) — e.g. `feature/config-command`, `chore/refactor-configs`. Checked, advisory-only,
  by `.github/workflows/branch-naming.yml`. One concern per branch, from an up-to-date `main`.
- Commit subjects use Conventional Commits (`feat:` or `feature:`, `fix:`, `refactor:`, `docs:`, `test:`,
  `chore:`): the changelog is generated from them.
- Stage by explicit path, never `git add <dir>` or `-A`; untracked local files get swept in.
- `make check` only sees tracked files: `git add -N` new files first, or they go unchecked.
- Local scratch files go in `.temp/` (gitignored).
