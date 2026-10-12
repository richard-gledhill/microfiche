# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`microfiche` scans a "library" folder (e.g. an Obsidian vault of `group/category` subfolders) for
loose documents dropped into a `_sorting/` inbox, classifies each one (group, then category),
and files it — recording every move so it can be rolled back. No file is ever deleted. Full
design rationale: [docs/development/architecture.md](docs/development/architecture.md)
(supersedes the earlier concept docs archived under `docs/development/archive/` where they conflict).
Domain language (library, group, category, unit, job, ledger, ...) is defined in
[CONTEXT.md](CONTEXT.md) — use those terms.

**Before assuming a described feature is fully wired, check
[docs/development/mvp-roadmap.md](docs/development/mvp-roadmap.md)** — it tracks what's
actually implemented vs. still stubbed (e.g. `review`/`index` are stub commands). See
[docs/development/README.md](docs/development/README.md) for the full doc index, including
[data-model.md](docs/development/data-model.md) (ledger/audit/rollback schemas) and
[mvp-build-plan.md](docs/development/mvp-build-plan.md) (staged build-from-scratch plan).

## Commands

```bash
make install    # uv sync across the workspace + install pre-commit hooks
make check      # uv lock --locked, pre-commit run -a, mypy, deptry (core, then cli)
make test       # pytest --doctest-modules --cov=core --cov=cli --cov-report=term-missing
make docs       # mkdocs serve
make library-schema   # regenerate microfiche/microfiche-library.schema.json from the model
make module-diagram   # regenerate the import graph in docs/development/module-diagram.md from the source
```

Single test / narrower run:

```bash
uv run pytest tests/core/test_rules.py -k some_case
```

Run one workspace package's own checks (e.g. what `make check` does per-package for deptry):

```bash
cd packages/core && uv run deptry src
```

`tox.ini` runs the same pytest + mypy pass across Python 3.11–3.14; `make check`/`make test` on
your local interpreter are what you want day to day.

## Architecture

uv workspace, two packages, `core` has no dependency on `cli`:

```
packages/core/src/core/   # scanning, classification, filing, library/Obsidian logic — the engine
packages/cli/src/cli/     # Typer CLI (app.py registers commands from commands.py) — thin wrapper
tests/core/, tests/cli/   # mirror the packages/ layout 1:1
tests/mock_library/       # hand-built library fixture for integration-style tests
```

Coverage/mypy config (in the root `pyproject.toml`) targets `core`/`cli` as **package names**,
not `packages/*/src` paths — this works because both are installed editable into the shared
workspace `.venv`.

### The sort pipeline (`core/organizer.py::run_sort`)

1. **`library/library.py::Library`** is the one place that knows the library's layout: the inbox and
   state folder, what is excluded, where a unit is filed, and the taxonomy. `Library.taxonomy()` walks the
   library tree (skipping the inbox, `.microfiche/`, and anything in `microfiche-config.toml`'s
   `[exclusions]` table — matched against the path *inside* the library, never its parent folders) and builds
   `{group_name: [category_name]}` fresh on every call. Public functions take a `Library` (`Library(path)`;
   its config loads lazily from `.microfiche/`). **The library's own folder structure is the taxonomy — nothing is
   persisted or configured separately.** `.microfiche/microfiche-library.json` (`library/library_file.py`) only supplies
   keyword *hints* and filename rules for matching against categories that already exist as folders.
2. **`scanner.py::scan_sorting_inbox`** finds `SortableUnit`s (readable `documents`, plus any `unreadable`
   files) in the library's inbox (`_sorting/` unless the
   config's `[library_structure] library_inbox` says otherwise) — either a loose file
   or (by default; `[sorting] keep_folders`) a whole folder treated as one unit. Names matching `[sorting] ignore` are
   skipped silently and symlinks/junctions (`utils/filesystem.py::is_link`, which checks the Windows reparse *tag* so
   OneDrive placeholders still count as files) are skipped and listed in `InboxScan.skipped_links`. With `keep_folders` off, each
   supported file in a folder is its own unit, with `origin_folder` set so `file_batch` can remove the folder
   once it is empty (recorded in the job, so rollback recreates it).
3. **`classifier.py::Classifier`** runs two-stage classification per document over `Resolver`s —
   the rules (`rules/rules_engine.py::RulesEngine`) first, then an optional AI fallback
   (`ai/llm_classifier.py::LLMClassifier`). It owns the flow, the confidence threshold and the
   taxonomy check; the resolvers only propose:
   - **Group** (`rules/group_rules.py`): keyword + fuzzy match (`rapidfuzz`) against known group
     names.
   - **Category** (`rules/keyword_rules.py`, `rules/metadata_rules.py`): filename-glob rules
     checked first, then keyword hints — scoped to the resolved group's existing category
     folders.
   - Overall confidence is `combine_confidence` (`rules/confidence.py`) of both stages — **min,
     not average**, so a confident category guess under an unconfident group guess still reads
     as unconfident.
   - The AI fallback is per stage: for the group, then the category within the resolved group,
     the rules answer first; only if that answer is missing or below the threshold is the
     `LLMClassifier` (backed by `ai/ollama_provider.py` or `ai/openai_provider.py`) asked to pick
     one (or "none") from the same taxonomy. A confident rules answer is never overridden, and
     an AI "none" keeps the rules' weak suggestion. The `ai` extra (`ollama`, `openai`) isn't
     installed by a plain `uv sync` — see the `core` package's `pyproject.toml`.
   - Any group/category a resolver names is checked against the taxonomy; one that isn't an
     existing folder counts as unresolved, so nothing is ever filed into an invented folder.
   - A result is `confident` when both stages resolved and the overall confidence reaches the
     threshold: `[classification] confidence_threshold` in the library's config, defaulting to
     0.75 (in the packaged `core/defaults/microfiche-config.toml`, chosen by measurement — see
     `docs/development/calibration.md`). At the default, keyword-hint matches (0.75) file but AI-only
     answers (0.70) go to review; a higher threshold files less without filing more accurately.
     `classified_by` names which resolver(s) decided: `rules_engine`, `ai_fallback` or
     `rules_engine+ai_fallback`.
   - A folder unit is classified document-by-document; the whole folder is filed under whichever
     `(group, category)` pair got the most votes across its documents (dominant-category rule),
     represented by that pair's most confident document. A tie for the most votes is not guessed:
     the folder goes to review with the disagreement as its reason.
4. Before filing, two checks can hold a classified unit in the inbox (`organizer.py::run_sort`), in this order:
   - **Duplicate** (`duplicates.py::DuplicateIndex`): a file unit whose content already exists in the library, or
     is being filed earlier in the run, goes to `SortReport.duplicates` with a reason that also says where the
     classifier would have filed it. Only new files are checked, never copies already in the library, so there is
     no setting. The index walks the library once, reading sizes only, and hashes only same-size files.
   - **Collision** (`filer.py::DestinationClaims`, shared with `reclassify`): the destination name is taken, so the
     unit goes to `needs_review` with the reason.
   Nothing is renamed, overwritten or deleted; `file_batch` still refuses to overwrite as the last line of defence.
5. Anything `confident` that passed both is filed as one job (`filer.py::file_batch`: move, ledger record,
   audit line, rollback job, and removal of an inbox folder left empty); everything else goes to
   `SortReport.needs_review` for the `review` command instead of being moved. A move is a plain rename
   (`utils/filesystem.py::safe_move`, never `shutil.move`, which falls back to copy-then-delete), so a unit
   that can't be moved (a file open in Word) stays put and comes back in `FilingResult.failed`; `run_sort`
   turns it into a `needs_review` entry. A provider failure switches the AI fallback off for the rest of the run
   (`SortReport.ai_unavailable`).
6. `sort --dry-run` runs the same pipeline with `file_batch` left out (`run_sort(dry_run=True)`): no job, ledger
   or audit line, no lock, no state folder. `sort`, `reclassify --apply` and `rollback` take `.microfiche/lock`
   (`runlock.py::run_lock`, at the CLI level) so only one changing run is active; a lock from a dead process is
   cleared, an unreadable one counts as held. Never use `os.kill(pid, 0)` to test a process on Windows.

### Everything else keys off that same taxonomy/classification core

- **`tests/calibration/`** — a labelled corpus (five small libraries, 136 documents) and a harness that
  measures what each confidence threshold does to auto-filing and misfiling, plus saved AI-fallback
  answers. `uv run python tests/calibration/report.py` prints the report; `test_calibration.py` pins
  the findings behind the default threshold, so changing the classifier or the default means
  re-running it and updating `docs/development/calibration.md`.
- **`reclassify.py`** (the `reclassify` command) re-runs the two-stage classifier against
  already-filed documents and plans each one: `move` / `keep` (already under the right category) /
  `review` (unresolved or below threshold) / `conflict` (destination taken). Dry-run by default;
  `--apply` files the `move`s through `filer.py::file_batch` as one rollback-able job — how
  classification drift gets reconciled after rule changes.
- **`library/category_suggester.py`** proposes new category names from term frequency across a
  scope; never creates folders itself (requires explicit `--apply` at the CLI layer).
- **`obsidian/`** — `index_writer.py` regenerates a folder's `index.md` (folder note) after every
  touch; `tag_index.py`/`tag_mapper.py` fuzzy-match extracted keywords against the library's root
  `TagIndex.md` and append unmatched ones to a `## Proposed` section rather than silently merging
  them in (suggest-only tag governance).
- **`filer.py::rollback_job`** replays a job's recorded `AuditEvent`s in reverse. Jobs are saved as
  `.microfiche/rollback/job_<id>.json` (`Job` model in `core/models/job.py`); rollback is driven purely
  by that JSON, not by re-deriving anything from the filesystem. `file_batch` writes the job, so
  `sort` and `reclassify --apply` are both rollback-able.
- **`ledger.py`** — `.microfiche/ledger.jsonl`, an append-only record of every filing (path,
  content hash, group, category, reasons, confidence, `classified_by`) and rollback. Keyed by
  path + content hash; `Ledger.current()` replays it to get what's filed now. It replaced the old
  per-file `*.metadata.json` sidecars — don't reintroduce files next to the user's documents.
  Schema: `docs/development/data-model.md`.

### Config resolution

Each library has its own `.microfiche/` — its *state folder* (dot-prefixed to stay out of Obsidian's file
explorer); `microfiche/` at the repo root is the template copied into a new library.
`core/config.py::load_config` deep-merges the library's `microfiche-config.toml` over the packaged defaults
(`core/defaults/microfiche-config.toml`, the only place a default lives) and validates the result into
`MicroficheConfig`. The library's hints and filename rules are a separate file, `microfiche-library.json`
(`core/library/library_file.py`, reached through `Library.library_file`). See the table in
[README.md](README.md#configuration) for what each config section governs.

### Parsers (`core/parsers/`)

One module per input format (`.docx`, `.eml`/`.msg`, `.pdf`, `.md`, `.txt`), each implementing
`parsers/base.py`'s interface and returning extracted text for the classifier. `parsers/registry.py` is
the dispatcher (re-exported from `core.parsers`): `is_supported(path)`, `parse_document(path)` and
`read_documents(paths, max_bytes=...)`; a file over `[parsing] max_file_mb` is refused unread, as unreadable. A parser failure never escapes as a raw library exception —
`parse_document` raises `UnreadableDocumentError` (or `UnsupportedFormatError`), and `read_documents`
collects unreadable files instead of stopping, so one corrupt file can't abort a `sort` or `reclassify`:
it becomes a unit (or proposal) left for review, with the reason.

## Conventions

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
- Use the [CONTEXT.md](CONTEXT.md) terms in code, docs and commits; add a term there when you
  introduce a domain concept.
- `ruff` config lives only in the root `pyproject.toml`; per-package `pyproject.toml` files carry
  just their own dependencies. mypy is strict and covers `packages/*/src` (not tests).

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
  [docs/how-to-use.md](docs/how-to-use.md) (the command in both its Bash and PowerShell tabs,
  plus its "Current limitations" list) and the Usage section of [README.md](README.md#usage).
- [docs/cli-reference.md](docs/cli-reference.md) is generated from the Typer app (command docstrings and
  option `help=` text): run `make docs-cli` after changing either. `make docs`/`make docs-test` do it for you,
  and a test fails if the file is stale. Write command docstrings for users, not as API docs - Typer
  prints them as `--help`.
- `microfiche/microfiche-library.schema.json` is generated from the library file model (`json_schema()` in
  `core/library/library_file.py`): run `make library-schema` after changing a field or its description. A test
  fails if the committed file is stale.
- `README.md` and `docs/how-to-use.md` are published; `docs/development/` is not, so link to it
  by GitHub URL.
- After a rename or behaviour change, grep the docs for the old name or number.
  `architecture.md`, `mvp-roadmap.md` and `module-diagram.md` go stale first. Run `make module-diagram` when
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

## Verifying your work

Verify any change to code, tests, config, or dependencies before reporting the task complete.
Docs-only changes and questions don't need the full suite.

### While developing: targeted checks

Run the narrowest check that exercises what you changed, e.g.:
```bash
uv run pytest tests/core/test_rules.py -k <test_name>
uv run --directory packages/core deptry src
```
These are for fast iteration; they don't replace full verification.

### Before reporting complete: full verification

```bash
make check   # uv lock --locked, pre-commit run -a, mypy, deptry (core, then cli)
make test    # pytest --doctest-modules with coverage for core and cli
```

- If pre-commit auto-fixes files, review the changes and rerun `make check`.
  If it still isn't clean after two reruns, stop and report.
- If `uv lock --locked` fails because you changed dependencies, run `uv lock` and include the lockfile in your change.

### Rules

- Fix the code, not the check. Never skip, delete, or weaken a test, and never silence a check:
  no `# type: ignore`, `# noqa`, `SKIP=`, `--no-verify`, or loosened mypy/deptry/pre-commit config,
  unless I've asked for it.
- If you believe a test is wrong, explain why in your final response before changing it.
- Add or update tests for any behavior you change.
- If a failure persists that you can't fix, or that existed before your change, or is caused by the
  environment (network, missing tools), stop. Don't report the task as complete. Say what failed and why.

### Final report

List each verification command you ran with pass/fail. For any failure, include the relevant output.
Don't report a command as passing unless you ran it after your last change.
