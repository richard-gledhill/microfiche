# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`microfiche` scans a "library" folder (e.g. an Obsidian vault of `group/category` subfolders) for
loose documents dropped into a `_sorting/` inbox, classifies each one (group, then category),
and files it — recording every move so it can be rolled back. No file is ever deleted. Full
design rationale: [docs/development/architecture/overview.md](docs/development/architecture/overview.md)
(supersedes the earlier concept docs archived under `docs/development/requirements/archive/` where they conflict).
Domain language (library, group, category, unit, job, ledger, ...) is defined in
[CONTEXT.md](CONTEXT.md) — use those terms.

**Before assuming a described feature is fully wired, check
[docs/development/requirements/mvp-roadmap.md](docs/development/requirements/mvp-roadmap.md)** — it tracks what's
actually implemented vs. still partial or deferred. See
[docs/development/README.md](docs/development/README.md) for the full doc index, including
[data-model.md](docs/development/architecture/data-model.md) (ledger/audit/rollback schemas) and
[MVP build plan](docs/development/plan/archive/2026-10-mvp/plan.md) (staged build-from-scratch plan).

## Development docs location

All development documentation lives under `docs/development/`, which is excluded from the MkDocs site;
[docs/development/README.md](docs/development/README.md) says where each kind of doc goes. These paths override any
default paths in skills or commands:

- Constraints: `docs/development/constraints.md` — project-wide; read before writing code; do not weaken it to make a
  change pass
- Conventions: `docs/development/conventions.md` — the style guide. The hook blocks agent edits to both
  `conventions.md` and `constraints.md`; describe the change you want in your summary and let the user make or
  approve it
- Requirements (PRDs, product briefs, user stories) live in `docs/development/requirements/`. Don't edit an existing
  requirements doc without asking. Create a new one only when the user asks. The exception is
  `requirements/mvp-roadmap.md`, a living status doc kept current as commands change (see `conventions.md`, Docs)
- Spec: `docs/development/plan/SPEC.md` (not root SPEC.md)
- Plan: `docs/development/plan/plan.md`
- Task list: `docs/development/plan/todo.md`
- SPEC.md is the technical spec for the current work. Link to its source in `requirements/`, and reference
  `conventions.md`, `constraints.md` and `testing/` instead of restating them. Record only what's specific to this work.
- ADRs: `docs/development/adr/`, format `ADR-NNN-title.md`; continue the existing sequence
- When work ships, move `SPEC.md`, `plan.md` and `todo.md` together into
  `docs/development/plan/archive/<YYYY-MM-feature>/`, and update the requirement's Status.
  If `plan/` already has an unfinished plan for different work, stop and ask.
- RFCs: no tracker is set up yet, so RFCs are local `docs/development/rfcs/RFC-NNN-title.md` files; continue the
  existing sequence. [`docs/development/rfcs/README.md`](docs/development/rfcs/README.md) says which mode the project
  uses. Once a GitHub Project is the tracker, it is the single source of truth: don't create or copy RFCs into
  `docs/development/rfcs/` then; refer to the issue instead. When an RFC is decided, record it as an ADR and link the
  two both ways.
- Never write development docs into the MkDocs content under `docs/` outside `development/`
- You may edit and add MkDocs pages (user-facing docs under `docs/`, outside `development/`) and `mkdocs.yml`
  when a change needs it. Add new pages to `nav:` and run `make docs-test` to check the site still builds.
- A hook (`.claude/hooks/guard_docs.py`) enforces the development paths and protects `conventions.md`,
  `constraints.md` (and existing files in any directory listed in its `PROTECTED_DIRS`, empty by default, as in the
  template). The hook does not block existing requirements docs, so nothing enforces the "don't edit without asking"
  rule above: follow it. If a write is blocked, follow the redirect in the hook's message, or ask the user if the file is
  protected. Don't use shell commands to get around it.

## Tracking work

This repository is tied only to the `microfiche` project. Don't link to, reference, or create issues or pull requests
in any other repository, including the `scratch-cookiecutter-uv` template or any cookiecutter-uv fork.

- Track work as GitHub issues in this repository. Label each one `issue`, `bugfix` or `rfc` (a request for change,
  discussed before it is built).
- Create, edit or close issues only when the user asks.
- No GitHub Project is linked yet (check with `gh repo view --json projectsV2`). Until one is, RFCs stay as local
  files (above) and there is no board to update.
- A decided RFC is recorded as an ADR in `docs/development/adr/`; link the RFC (or its issue) and the ADR to each other.
- Reference the issue in commits and PRs (`Closes #N`).

## Commands

```bash
make install    # uv sync across the workspace + install pre-commit hooks
make check      # uv lock --locked, pre-commit run -a, mypy (Linux, then Windows), deptry (core, then cli)
make test       # pytest --doctest-modules --cov (the packages come from [tool.coverage.run]) --cov-report=term-missing
make docs       # mkdocs serve
make library-schema   # regenerate microfiche/microfiche-library.schema.json from the model
make module-diagram   # regenerate the import graph in docs/development/architecture/module-diagram.md from the source
make build            # build the core and cli release wheels into dist/ and check them (scripts/check_wheels.py)
make smoke-wheels     # ...then install them in a clean environment and run them (scripts/smoke_wheels.sh)
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
packages/core/src/microfiche/core/   # scanning, classification, filing, library logic — the engine
packages/cli/src/microfiche/cli/     # Typer CLI (app.py registers commands from commands.py) — thin wrapper
tests/core/, tests/cli/              # mirror the packages/ layout 1:1
tests/scripts/                       # tests of scripts/ (module diagram, wheel checks, the sample library builder)
tests/mock_library/       # hand-built library fixture for integration-style tests
tests/mock_flat_library/  # the same for a flat (depth 1) library
```

**Names.** The two distributions are called `core` and `cli`, but they import as `microfiche.core` and
`microfiche.cli`: each package's `[tool.uv.build-backend] module-name` puts its code in the shared `microfiche`
namespace (a PEP 420 namespace package). **`packages/*/src/microfiche/` must never contain an `__init__.py`**: it
would make one wheel own the namespace and hide the other (a test and `scripts/check_wheels.py` guard this). In these
docs, `core/organizer.py` and `core.filer` are shorthand for `microfiche/core/organizer.py` and `microfiche.core.filer`.
Write `from microfiche.core.filer import ...` in code and in `monkeypatch.setattr` strings. How to set this up:
the libCoding vault note "Namespace Packages in a uv Workspace".

Coverage config (in the root `pyproject.toml`) targets `microfiche.core`/`microfiche.cli` as **package names**, not
paths — this works because both are installed editable into the shared workspace `.venv`. mypy needs `mypy_path`,
`namespace_packages` and `explicit_package_bases` for the same reason, and each package's deptry config maps the
`microfiche` import to the right distribution.

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
     `docs/development/testing/calibration.md`). At the default, keyword-hint matches (0.75) file but AI-only
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
   or audit line, no lock, no state folder. `sort`, `reclassify --apply`, `rollback`, `config --sync` and `review` (when it files) take `.microfiche/lock`
   (`runlock.py::run_lock`, at the CLI level) so only one changing run is active; a lock from a dead process is
   cleared, an unreadable one counts as held. Never use `os.kill(pid, 0)` to test a process on Windows.

### Everything else keys off that same taxonomy/classification core

- **`tests/calibration/`** — a labelled corpus (five small libraries, 136 documents) and a harness that
  measures what each confidence threshold does to auto-filing and misfiling, plus saved AI-fallback
  answers. `uv run python tests/calibration/report.py` prints the report; `test_calibration.py` pins
  the findings behind the default threshold, so changing the classifier or the default means
  re-running it and updating `docs/development/testing/calibration.md`.
- **`reclassify.py`** (the `reclassify` command) re-runs the two-stage classifier against
  already-filed documents and plans each one: `move` / `keep` (already under the right category) /
  `review` (unresolved or below threshold) / `conflict` (destination taken). Dry-run by default;
  `--apply` files the `move`s through `filer.py::file_batch` as one rollback-able job — how
  classification drift gets reconciled after rule changes. A folder the ledger records as filed whole
  (`Ledger.folder_units()`) is one unit, proposed whole and never split; other folders are read file by file,
  and `[exclusions]` keeps a folder out.
- **`review.py`** (the `review` command) is a `ReviewSession` over what a preview sort leaves in the inbox:
  `decide` checks a choice as it is made (a place that exists or is planned, the name free, not a duplicate),
  `commit` re-checks and files the chosen units as one `file_batch` job with `classified_by = "user"`. Nothing is
  created or moved before `commit`; the prompts live in `cli/review.py`.
- **`library/category_suggester.py`** proposes new category names from term frequency across a
  scope; never creates folders itself. `propose-categories` only prints, over the inbox; it has no `--apply`, no `--use-ai` and no
  scope option yet (see `docs/development/architecture/overview.md` §6).
- **No Obsidian code.** `index.md` folder notes and `TagIndex.md` tag governance were removed from the MVP and are
  parked in [docs/development/rfcs/RFC-002-obsidian-integration.md](docs/development/rfcs/RFC-002-obsidian-integration.md), with where to restore them
  from. Don't reintroduce an `[obsidian]` config section or an `index` command; the integration is to be designed as
  a plugin after the MVP.
- **`filer.py::rollback_job`** replays a job's recorded `AuditEvent`s in reverse. Jobs are saved as
  `.microfiche/rollback/job_<id>.json` (`Job` model in `core/models/job.py`); rollback is driven purely
  by that JSON, not by re-deriving anything from the filesystem. `file_batch` writes the job, so
  `sort` and `reclassify --apply` are both rollback-able.
- **`ledger.py`** — `.microfiche/ledger.jsonl`, an append-only record of every filing (path,
  content hash, group, category, reasons, confidence, `classified_by`) and rollback. Keyed by
  path + content hash; `Ledger.current()` replays it to get what's filed now. It replaced the old
  per-file `*.metadata.json` sidecars — don't reintroduce files next to the user's documents.
  Schema: `docs/development/architecture/data-model.md`.

### Config resolution

Each library has its own `.microfiche/` — its *state folder* (dot-prefixed to stay out of Obsidian's file
explorer); `microfiche init` (`core/library_init.py`) writes the packaged defaults into a new library and edits an
existing config, and `microfiche/` at the repo root holds example config and library files.
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

Read [`docs/development/conventions.md`](docs/development/conventions.md) (design, code, module layout, tests, docs
and git) and [`docs/development/constraints.md`](docs/development/constraints.md) (the enforced quality bar) before
writing code. Don't change either without asking, and never to make them match code you just wrote.

In a `SPEC.md`, reference `conventions.md` instead of restating code style. Only record feature-specific deviations.

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
make check   # uv lock --locked, pre-commit run -a, mypy (Linux, then Windows), deptry (core, then cli)
make test    # pytest --doctest-modules with coverage for core and cli
```

- If pre-commit auto-fixes files, review the changes and rerun `make check`.
  If it still isn't clean after two reruns, stop and report.
- If `uv lock --locked` fails because you changed dependencies, run `uv lock` and include the lockfile in your change.

### Rules

- The quality bar, including what never to silence or weaken, is in
  [`docs/development/constraints.md`](docs/development/constraints.md). Fix the code, not the check.
- If you believe a test is wrong, explain why in your final response before changing it.
- If a failure persists that you can't fix, or that existed before your change, or is caused by the
  environment (network, missing tools), stop. Don't report the task as complete. Say what failed and why.

### Final report

List each verification command you ran with pass/fail. For any failure, include the relevant output.
Don't report a command as passing unless you ran it after your last change.
