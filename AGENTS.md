# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`microfiche` scans a "library" folder (e.g. an Obsidian vault of `group/category` subfolders) for
loose documents dropped into a `_sorting/` inbox, classifies each one (group, then category),
and files it — recording every move so it can be rolled back. Nothing is ever deleted. Full
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
```

Single test / narrower run:

```bash
uv run pytest tests/core/test_rules.py -k some_case
```

Run one workspace package's own checks (e.g. what `make check` does per-package for deptry):

```bash
cd packages/core && uv run deptry src
```

`tox.ini` runs the same pytest + mypy pass across Python 3.10–3.14; `make check`/`make test` on
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
   persisted or configured separately.** `microfiche-config.toml`'s `[category_hints.categories]` table only supplies
   keyword *hints* for matching against categories that already exist as folders.
2. **`scanner.py::scan_sorting_inbox`** finds `SortableUnit`s (readable `documents`, plus any `unreadable`
   files) in the library's inbox (`_sorting/` unless the
   config's `[library_structure] library_inbox` says otherwise) — either a loose file
   or (with `--keep-folders`) a whole folder treated as one unit.
3. **`classifier.py::Classifier`** runs two-stage classification per document over `Resolver`s —
   the rules (`rules/rules_engine.py::RulesEngine`) first, then an optional AI fallback
   (`ai/llm_classifier.py::LLMClassifier`). It owns the flow, the confidence threshold and the
   taxonomy check; the resolvers only propose:
   - **Group** (`rules/group_rules.py`): keyword + fuzzy match (`thefuzz`) against known group
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
     `DEFAULT_CONFIDENCE_THRESHOLD` (0.75, in `rules/confidence.py`, chosen by measurement — see
     `docs/development/calibration.md`). At the default, keyword-hint matches (0.75) file but AI-only
     answers (0.70) go to review; a higher threshold files less without filing more accurately.
     `classified_by` names which resolver(s) decided: `rules_engine`, `ai_fallback` or
     `rules_engine+ai_fallback`.
   - A folder unit is classified document-by-document; the whole folder is filed under whichever
     `(group, category)` pair got the most votes across its documents (dominant-category rule),
     represented by that pair's most confident document. A tie for the most votes is not guessed:
     the folder goes to review with the disagreement as its reason.
4. Anything `confident` is filed as one job (`filer.py::file_batch`: move, ledger record,
   audit line, rollback job); everything else goes to
   `SortReport.needs_review` for the `review` command instead of being moved.

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
`core/config.py::MicroficheConfig` loads and validates all of it. See the table in
[README.md](README.md#configuration) for what each section governs.

### Parsers (`core/parsers/`)

One module per input format (`.docx`, `.eml`/`.msg`, `.pdf`, `.md`, `.txt`), each implementing
`parsers/base.py`'s interface and returning extracted text for the classifier. `parsers/registry.py` is
the dispatcher (re-exported from `core.parsers`): `is_supported(path)`, `parse_document(path)` and
`read_documents(paths)`. A parser failure never escapes as a raw library exception —
`parse_document` raises `UnreadableDocumentError` (or `UnsupportedFormatError`), and `read_documents`
collects unreadable files instead of stopping, so one corrupt file can't abort a `sort` or `reclassify`:
it becomes a unit (or proposal) left for review, with the reason.

## Conventions

- Docstrings: Google style (`Args:`/`Returns:`/`Raises:`) — `mkdocstrings` renders them for the
  published docs.
- `ruff` config lives entirely in the root `pyproject.toml`; per-package `pyproject.toml` files
  carry only that package's own dependencies, not tool config.
- mypy is strict (`disallow_untyped_defs`, `warn_return_any`, etc.) and runs from the repo root
  against both `packages/*/src` trees at once.
- User docs track the CLI: any change to a command, an option, or a command's status in
  `docs/development/mvp-roadmap.md` must also update
  [docs/how-to-use.md](docs/how-to-use.md) (the command in both its Bash and PowerShell tabs,
  plus its "Current limitations" list) and the Usage section of [README.md](README.md#usage).
- Branches follow `<type>/<short-description>`, `<type>` being a Conventional Commits type
  (`feat`/`feature`, `fix`, `chore`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`,
  `revert`) — e.g. `feature/config-command`, `chore/refactor-configs`. Checked, advisory-only,
  by `.github/workflows/branch-naming.yml`.

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
