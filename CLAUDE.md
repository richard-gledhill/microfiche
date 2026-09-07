# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`microfiche` scans a "library" folder (an Obsidian vault of `group/category` subfolders) for
loose documents dropped into a `sorting/` inbox, classifies each one (group, then category),
and files it — recording every move so it can be rolled back. Nothing is ever deleted. Full
design rationale: [docs/prd/20260907_microfiche_architecture_v2.md](docs/prd/20260907_microfiche_architecture_v2.md)
(supersedes the earlier `docs/prd/2026070*` concept docs where they conflict).

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

1. **`library/taxonomy.py::discover_taxonomy`** walks the library tree (skipping `sorting/` and
   anything in `microfiche-config/exclusions.yaml`) and builds `{group_name: [category_name]}`
   fresh on every run. **The library's own folder structure is the taxonomy — nothing is
   persisted or configured separately.** `microfiche-config/categories.yaml` only supplies
   keyword *hints* for matching against categories that already exist as folders.
2. **`scanner.py::scan_sorting_inbox`** finds `SortableUnit`s in `sorting/` — either a loose file
   or (with `--keep-folders`) a whole folder treated as one unit.
3. **`classifier.py::Classifier`** runs two-stage classification per document, via
   `rules/rules_engine.py`:
   - **Group** (`rules/group_rules.py`): keyword + fuzzy match (`thefuzz`) against known group
     names.
   - **Category** (`rules/keyword_rules.py`, `rules/metadata_rules.py`): filename-glob rules
     checked first, then keyword hints — scoped to the resolved group's existing category
     folders.
   - Overall confidence is `combine_confidence` (`rules/confidence.py`) of both stages — **min,
     not average**, so a confident category guess under an unconfident group guess still reads
     as unconfident.
   - If rules score below `Classifier.CONFIDENCE_THRESHOLD` (0.6) and an `LLMClassifier`
     (`ai/llm_classifier.py`, backed by `ai/ollama_provider.py` or `ai/openai_provider.py`) was
     passed in, it's asked to pick a group/category (or "none") from the same taxonomy. The
     `ai` extra (`ollama`, `openai`) isn't installed by a plain `uv sync` — see the `core`
     package's `pyproject.toml`.
   - A folder unit is classified document-by-document; the whole folder is filed under whichever
     `(group, category)` pair got the most votes across its documents (dominant-category rule).
4. Anything at/above threshold is filed (`filer.py`) and audited; everything else goes to
   `SortReport.needs_review` for the `review` command instead of being moved.

### Everything else keys off that same taxonomy/classification core

- **`resort.py`** re-runs the two-stage classifier against already-filed documents (dry-run by
  default, `--apply` to move) — how classification drift gets reconciled after rule changes.
- **`library/category_suggester.py`** proposes new category names from term frequency across a
  scope; never creates folders itself (requires explicit `--apply` at the CLI layer).
- **`obsidian/`** — `index_writer.py` regenerates a folder's `index.md` (folder note) after every
  touch; `tag_index.py`/`tag_mapper.py` fuzzy-match extracted keywords against the library's root
  `TagIndex.md` and append unmatched ones to a `## Proposed` section rather than silently merging
  them in (suggest-only tag governance).
- **`rollback.py`** replays a job's recorded `AuditEvent`s in reverse. Jobs are saved as
  `logs/rollback/job_<id>.json` (`Job` model in `core/models/job.py`); rollback is driven purely
  by that JSON, not by re-deriving anything from the filesystem.

### Config resolution

Each library has its own `.microfiche-config/` (dot-prefixed to stay out of Obsidian's file
explorer); `microfiche-config/` at the repo root is the template copied into a new library.
`core/config.py::MicroficheConfig` loads and validates all of it. See the table in
[README.md](README.md#configuration) for what each YAML file governs.

### Parsers (`core/parsers/`)

One module per input format (`.docx`, `.eml`/`.msg`, `.pdf`, `.md`, `.txt`), each implementing
`parsers/base.py`'s interface and returning extracted text for the classifier — `extractor.py` is
the dispatcher that picks a parser by file extension.

## Conventions

- Docstrings: Google style (`Args:`/`Returns:`/`Raises:`) — `mkdocstrings` renders them for the
  published docs.
- `ruff` config lives entirely in the root `pyproject.toml`; per-package `pyproject.toml` files
  carry only that package's own dependencies, not tool config.
- mypy is strict (`disallow_untyped_defs`, `warn_return_any`, etc.) and runs from the repo root
  against both `packages/*/src` trees at once.
