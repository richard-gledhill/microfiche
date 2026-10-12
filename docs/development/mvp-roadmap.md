# MVP roadmap

What's actually implemented vs. what `architecture.md` describes, and what's still blocking
a real MVP. Edit this in place as commands move from stub → partial → done — it's a living
doc, not a dated snapshot (same convention as `architecture.md`). When a command's status
changes here, update the "Current limitations" list and usage steps in the user-facing
[how-to-use.md](../how-to-use.md) in the same change.

## CLI command status

| Command | Status | Notes |
|---|---|---|
| `sort` | Done (for MVP scope) | Classifies and files, and records each run as one job: a rollback job, ledger records and `audit.log` lines under `.microfiche/` (`core/filer.py::file_batch`). Prints the job id. Items below the confidence threshold stay in `_sorting/` for `review`, which is still a stub. A name collision or an exact content duplicate is also left in the inbox, with the reason (Stage 4.2); `keep_folders = false` files a folder's documents one by one and removes the emptied folder, recorded so `rollback` recreates it. `--dry-run` previews a run without moving or recording anything, and a move that fails (a file open in Word) leaves that unit in review without stopping the run (Stage 4.3). `-v`/`-q` set how much is shown, and a run is explained in `.microfiche/microfiche.log` (Stage 4.4). |
| `review` | Stub (in the MVP: [Stage 5](mvp-build-plan.md#stage-5--review-workflow)) | Exits with a "not implemented" message (`cli/commands.py::review`); the real interaction loop is parked, unwritten, in `cli/review.py`. Until it is built, a unit left for review is filed by hand. |
| `propose-categories` | Partial | Works, but only scoped to the sorting inbox — scoping to an existing library folder isn't implemented. Print-only by design (never applies); that part is not a gap. |
| `reclassify` | Done (for MVP scope) | Dry run previews each document's action (`move` / `keep` / `review` / `conflict`); `--apply` files the `move`s through `core.filer.file_batch` as one rollback-able job (`core/reclassify.py`). `--folder` must be inside the library. No AI fallback in `reclassify` yet. |
| `audit` | Done | Shows `.microfiche/audit.log`, which `sort` and `rollback` append to (one line per move). |
| `rollback` | Done | Reverses a `sort` job by id, newest move first; refuses a job already rolled back; safe to retry if it stopped part-way. Failures print a message and exit 1. Also undoes `reclassify --apply` jobs, which go through the same `file_batch` path. |
| `config` | Done | Prints the library's loaded configuration (`cli/display.py::render_config`). `--sync` instead brings `microfiche-library.json` in step with the folders (Stage 4.10); it takes the run lock and, unlike plain `config`, writes. |

## Cross-cutting feature status

- **AI fallback** — wired via `--use-ai` (`cli/commands.py`), applied per stage by `Classifier`. The `[ai]`
  section picks the provider (`ollama` or `openai`), model, host, timeout and the OpenAI key variable;
  `core.ai.factory.build_provider` builds it, and `sort` says when document text goes to OpenAI. At the default confidence threshold (0.75) an AI-only answer (0.70) is left for
  review, not filed — lower `[classification] confidence_threshold` to 0.7 to let it file. Measured at
  98% precision on one local model (see [calibration.md](calibration.md)), but only consulted where
  the rules are unsure, so it adds little as built.
- **Obsidian integration** — removed from the MVP, along with the `index` command and the `[obsidian]` config section;
  it was never called from the sort pipeline. See [feature-backlog.md](feature-backlog.md#obsidian-integration).
- **Naming rules** (`library/naming.py`) — wired; `filer.py` applies them before filing.
- **Classification ledger** (`core/ledger.py`) — wired; replaces the per-file `*.metadata.json`
  sidecars. Records path, content hash, group, category, reasons, confidence and `classified_by`
  per filing. Not yet recorded: `tags`, and the per-document breakdown for folder units.
- **Document parsing** (`core/parsers/`) — wired. `read_documents` skips unsupported files and reports
  unreadable ones (corrupt, truncated) on their unit instead of raising, so one bad file no longer aborts a
  `sort` or `reclassify`. Not covered: a password-protected PDF is reported unreadable like any other bad
  file; OCR for scanned (image-only) PDFs isn't attempted, so they read as empty text and go to review.
- **Library layout** (`core/library/library.py`) — wired. `Library` owns the inbox (configurable via
  `[library_structure] library_inbox`), state folder, target folders, relative paths, exclusions and taxonomy. Exclusions
  are matched relative to the library root and always cover the inbox and `.microfiche/`. Not done: nested
  sub-libraries (the shipped exclusion patterns leave room for them).
- **Config validation** (`core/config.py`) — wired. `load_config` validates the whole file in one pass: an
  unknown section or setting, a value of the wrong type, or a section that isn't a table raises `ConfigError`,
  whose message names the file and every problem. `sort`, `reclassify`, `propose-categories` and `config` check
  it up front and exit 1 (`cli/commands.py::_open_library`); `sort` and `reclassify` also check the library file
  (`microfiche-library.json`) the same way. `audit` and `rollback` never read either, so a job can
  still be undone while the config is broken. A missing file or section still means defaults, silently;
  asking first is under [Future work](#future-work) ("Ask before running on defaults").
- **Classifier and resolver seam** (`core/classifier.py`) — wired. `Classifier` owns the two-stage flow,
  the confidence threshold (`[classification] confidence_threshold`, default 0.75, calibrated), the per-stage AI
  fallback and the taxonomy check; `RulesEngine` and `LLMClassifier` are its two resolvers.
- **Folder dominant-category voting** — wired, in `classifier.py::Classifier.classify_unit`. A tie for
  the most votes is left unresolved for review rather than guessed.

## Must-fix before MVP

Ranked by how central they are to the product's core promise, not by ease of implementation.

1. ~~Wire audit/rollback persistence into `run_sort` and `reclassify --apply`.~~ **Done for
   `sort`:** `core.filer.file_batch` saves the job, appends the ledger and writes
   `.microfiche/audit.log`, and `rollback` undoes it. `reclassify --apply` uses the same path — see 3.
2. ~~Reconcile the `.logs` vs `logs` path inconsistency.~~ **Resolved, then further
   consolidated.** `core/models/job.py`'s docstring and the CLI agree on a dot-prefixed
   convention — and that convention now shares one `.microfiche/` folder with
   `microfiche-config.toml` (`core.config.MICROFICHE_DIRNAME`, used by both `core` and the CLI),
   rather than living in a separate `.microfiche-logs/` folder.
3. ~~Wire `reclassify --apply` to the filer.~~ **Done:** `core.reclassify.apply_reclassification`
   files the previewed `move`s via `core.filer.file_batch`, reusing the job/ledger/audit
   persistence from (1).
4. ~~**Open decision:** are `review` and `index` in MVP scope?~~ **Decided:** `review` is in the MVP, as
   [Stage 5](mvp-build-plan.md#stage-5--review-workflow) (the only way out of the inbox for a unit below the
   confidence threshold), and still to build. `index` is out, with the Obsidian integration, and has been removed
   from the CLI rather than left as a stub that exits 1.

## Configuration consolidation (Stage 4.1)

Built. Reviewed in [config-review.md](config-review.md) and described in
[architecture.md §10](architecture.md#10-configuration-layout). In short: one packaged defaults file with a layered
loader; the match strengths and group fuzzy threshold as `[classification]` settings, and the AI score and
`max_document_chars` as `[ai]` settings; `[sorting] keep_folders` (default on) with `--keep-folders` and
`--keep-folders-off`; an `[ai]` provider section that makes `OpenAIProvider` reachable from `sort --use-ai`; category
hints and filing rules moved to `.microfiche/microfiche-library.json`; the unused `library_templates`, `levels` and
`file_target_level` removed and `depth` validated; and `thefuzz` replaced by `rapidfuzz`.

Not part of it: the library file was written by hand until
[Stage 4.10](mvp-build-plan.md#stage-410--library-file-sync) (built, below) created it from the folders and kept it in step.

[Stage 4.2](mvp-build-plan.md#stage-42--folder-handling--name-collisions) is built, from
[operations-review.md](operations-review.md). A name collision no longer crashes `sort`: the unit stays in the inbox
for review with the reason (`core.filer.DestinationClaims`, shared with `reclassify`). An inbox file whose content is
identical to a file already in the library, or to one filed earlier in the same run, is classified but held in the
inbox and listed under Duplicates, with the reason saying where the copy is and where this one would have gone
(`core/duplicates.py`). Only new files are checked, so copies already in the library are never reported and the check
has no setting. `keep_folders = false` descends into inbox folders, files each document on its own, and removes a
folder once it is empty, recorded as a `remove_folder` event so `rollback` recreates it. Still open: duplicates
are not checked for folders kept whole, and a duplicate is not moved out of the inbox for you.

[Stage 4.3](mvp-build-plan.md#stage-43--safe-runs--input-hardening) is built. `sort --dry-run` previews a run
(`run_sort(dry_run=True)`), writing nothing and taking no lock. `sort`, `reclassify --apply` and `rollback` take
`.microfiche/lock` (`core/runlock.py`) so a second changing run refuses to start; a lock from a dead process is
cleared. A move is now a plain rename, so a file another program has open fails cleanly and, like any other
per-unit failure, goes to review with the reason while the rest of the batch is filed (`file_batch` returns a
`FilingResult`). A failing AI provider switches the AI off for the rest of the run, with one warning. The inbox
scan skips `[sorting] ignore` names, symlinks and junctions, and a file over `[parsing] max_file_mb` is left for
review unread. Still open: a lock timeout or `--force`, nested-library detection, and `reclassify` does not apply
the inbox's `ignore` and link rules.

[Stage 4.4](mvp-build-plan.md#stage-44--logging--diagnostics) is built. `core` emits records through module loggers
(`_logger = logging.getLogger(__name__)`) and installs no handlers; `core/__init__.py` puts a `NullHandler` on its
package logger. The CLI configures them (`cli/logging.py`): a Rich console handler on stderr (WARNING and above, INFO
with `-v`, errors only with `-q`, which wins) and, for a command that holds the run lock, a rotating UTF-8
`.microfiche/microfiche.log` (the `[logging]` settings; DEBUG with `-v`). The commands enter `_locked` before
`_logging`, so a run the lock refuses leaves no trace. A `FILE_ONLY` marker keeps a record off the screen when the user
was already told: the OpenAI and unlimited-size notices stay direct prints, so `-q` cannot hide them, and are also
logged to the file. The AI fallback logs its first failure at WARNING, and the sort report no longer prints a line of
its own for it. Decisions are logged without document text (a test checks it). `sort` and `reclassify` show a
progress bar (`cli/progress.py`) on a terminal, for 20 or more units or when the AI is used, fed by an optional
`progress(done, total)` callback so `core` does not import Rich. Ruff's `LOG` and `G` rules are on. The run lock logs
nothing itself, because it is taken before logging is set up and released after it is torn down; instead `run_lock`
yields the holder of a stale lock it cleared, `_locked` passes that on, and `_logging` logs it as a WARNING once logging
is on. Still open: `-q` hides the AI-unavailable warning, and the stale-lock warning, on screen.

One further step follows it, and it is not built:
[Stage 4.5](mvp-build-plan.md#stage-45--decision-model-classifier) (a second AI resolver, a decision model such as
Jev, Clef or Nimble, whose own probability replaces the flat `0.70`; adopted only if it beats the chat model on the
calibration corpus; see [ai-classifier-options.md](ai-classifier-options.md)).

Four more concern the library's shape, from [library-depth.md](library-depth.md); none is built:
[Stage 4.6](mvp-build-plan.md#stage-46--flat-libraries-depth-1) (depth 1, group only),
[Stage 4.7](mvp-build-plan.md#stage-47--subcategories-depth-3-provisional) (depth 3 with subcategories,
provisional and deferred if it hits a practical limit), [Stage 4.8](mvp-build-plan.md#stage-48--non-library-folders)
(folders that aren't part of the taxonomy, such as bundles filed by `keep_folders`; today `reclassify` would split
them) and [Stage 4.9](mvp-build-plan.md#stage-49--filing-target-mode-optional) (an optional `[sorting] file_at`
setting: `leaf_only` or `best_level`).

[Stage 4.10](mvp-build-plan.md#stage-410--library-file-sync) is built. `Library.structure()` is the sorted,
exclusion-aware, link-skipping walk of the folders to `depth`, and `taxonomy()` is a view of it. `sync_library_file`
(`core/library/library_sync.py`) diffs it against the library file: the first real `sort` creates the file, later
ones append an entry (no hints) for each new folder and report it once, and `config --sync` does the same without
sorting. Entries with no folder are reported every run and kept; one gone and one new in the same place is flagged as
a possible rename. Nothing the user wrote is changed, a `*` entry covers the folders at its level, and the file is
written through a temporary file and a rename, only when something was added. A preview and plain `config` write
nothing; a file that can't be written is a warning for `sort` and exit 1 for `config --sync`. Still open: a preview
doesn't show what would be added, a `name_pattern` and the filed-bundle signal wait for
[Stage 4.8](mvp-build-plan.md#stage-48--non-library-folders), and the walk reads two levels until Stages 4.6 and 4.7.

## Future work and deferred beyond MVP

This section holds two kinds of item. **Future work** improves what is already built: calibration, matching and AI
behaviour, and safer defaults. **Deferred beyond MVP** is left out of the MVP on purpose, listed so it isn't mistaken
for an unplanned gap. Features with a design to keep, or code removed from the MVP, are in
[feature-backlog.md](feature-backlog.md) instead, which also says where each kind of item goes.

### Future work

- ~~**Calibrate the confidence threshold against test documents, and tell users how to set it.**~~ **Done**
  — see [calibration.md](calibration.md). Default changed from 0.8 to 0.75; user guidance is in
  `how-to-use.md`. It was measured on a synthetic corpus of short documents, so it still wants a pass
  on real ones (below).
- **Calibrate on real, longer documents.** Add them to `tests/calibration/corpus/` (or point
  `report.py` at a library you trust) and re-check the default. The bundled corpus is synthetic,
  short, and written knowing the rules, so its absolute error rates are not predictive.
- **Ambiguity check.** Hold a document when more than one group is named in its text, or more than one
  category has evidence. Prototype on the corpus: misfires 24 → 8 at the default, correct filings
  89 → 87. Needs measuring on long documents before it is built.
- **Match group names on word boundaries.** `Car` matches `carrier` and `card`; short or common group
  names file with full confidence on a substring (0 of 2 right on the corpus). The exact check needs a
  regular expression with `\b`; once Stage 4.1 switches to `rapidfuzz`, its `partial_ratio_alignment` can apply
  the same boundary test to fuzzy matches (see [fuzzy-matching-options.md](fuzzy-matching-options.md)).
- **Use the AI where the rules are ambiguous or hint-level.** Today it is asked only when the rules are unsure,
  never about their confident mistakes, and its score is one value (`[ai] ai_confidence`, 0.70) whatever model is
  behind it. Also: `OllamaProvider` doesn't disable the model's "thinking", so a call
  took about 5 s against about 2 s with it off on the model measured; its default model (`llama3`) may
  not be installed.
- **Review the signal strengths' values** (hint 0.75, AI 0.70 and the others). They are `[classification]` and `[ai]`
  settings now; what is left is checking the values against the calibration harness.
- **Ask before running on defaults.** A missing `.microfiche/microfiche-config.toml`, or one that leaves out
  sections, silently falls back to the defaults (pinned by `test_load_config_missing_files_fall_back_to_defaults`
  and the CLI test for a library with no config folder). A misnamed config file or the wrong `--library` path
  therefore looks like a normal run on settings the user never chose. Instead, `sort`, `reclassify` and
  `propose-categories` should say which config was not found or which sections are being defaulted, and ask
  whether to proceed. Open questions: a non-interactive switch for scripts (for example `--use-defaults` or
  `--yes`), a non-zero exit when there is no terminal to ask on, whether a partial file warrants a prompt or
  only a notice, and how this fits a future `init` command that writes the default config. Today's
  invalid-config behaviour (an error, not a prompt) is unchanged.

### Deferred beyond MVP

No database, vector store or semantic search, and `ai/` stays a fallback rather than an always-on pass
([architecture.md](architecture.md) §9). Postponed after the review in [operations-review.md](operations-review.md):

- **OCR** for scanned (image-only) PDFs, which read as empty text and go to review today.
- **A lock timeout or `--force` override** for the run lock, and nested-library detection.
- **Moving duplicates** to a `_sorting/duplicates/` folder to leave the inbox tidier, checking folders kept whole for duplicates, and a persistent hash cache. Content-duplicate detection itself is built (Stage 4.2).
- **Renaming on collision** (a suffix setting). Collisions go to review instead.
- **`doctor` / `verify` command** to detect drift between the ledger and the filesystem after files are moved outside microfiche.
- **Watch mode**, a daemon that sorts as files arrive.
- **`--json` output** for scripting.
- **Rotation or compaction** of the append-only ledger and `audit.log`.
- **Structured (JSON) log output** and log shipping.
- **Showing a failed move once.** A unit that can't be moved (a file open in Word) is reported twice on screen: as a
  WARNING when it happens, which is also written to the log file, and again as its reason in the `sort` summary. The
  warning could carry `extra=FILE_ONLY` so the screen shows only the summary; it is left as it is because the early
  warning is useful on a long run. The same applies to `reclassify --apply`.
- **Dependency and security scanning** (`pip-audit`, CodeQL) and a `SECURITY.md`; Dependabot is already configured.
- **Telemetry:** none, and none is planned.
- **Depth 4 and above.** Library creation functions are capped at depth 3, and Stage 4.7 may itself be deferred.
- **Training a classifier on the library's own ledger**, and chaining AI models (see [ai-classifier-options.md](ai-classifier-options.md)).

## See also

- [architecture.md](architecture.md) — the current design this status is measured against.
- [data-model.md](data-model.md) — the ledger/audit/rollback schemas referenced above.
- [mvp-build-plan.md](mvp-build-plan.md) — a staged, from-scratch process for building to MVP
  (Plan/Design/Build/Test/Deploy per stage), if you're sequencing the work in this doc rather
  than just tracking status.
