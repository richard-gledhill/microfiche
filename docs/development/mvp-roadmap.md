# MVP roadmap

What's actually implemented vs. what `architecture.md` describes, and what's still blocking
a real MVP. Edit this in place as commands move from stub → partial → done — it's a living
doc, not a dated snapshot (same convention as `architecture.md`). When a command's status
changes here, update the "Current limitations" list and usage steps in the user-facing
[how-to-use.md](../how-to-use.md) in the same change.

## CLI command status

| Command | Status | Notes |
|---|---|---|
| `sort` | Done (for MVP scope) | Classifies and files, and records each run as one job: a rollback job, ledger records and `audit.log` lines under `.microfiche/` (`core/filer.py::file_batch`). Prints the job id. Items below the confidence threshold stay in `_sorting/` for `review`, which is still a stub. |
| `review` | Stub | Exits with a "not implemented" message (`cli/commands.py::review`); the real interaction loop is parked, unwritten, in `cli/review.py`. |
| `propose-categories` | Partial | Works, but only scoped to the sorting inbox — scoping to an existing library folder isn't implemented. Print-only by design (never applies); that part is not a gap. |
| `reclassify` | Done (for MVP scope) | Dry run previews each document's action (`move` / `keep` / `review` / `conflict`); `--apply` files the `move`s through `core.filer.file_batch` as one rollback-able job (`core/reclassify.py`). `--folder` must be inside the library. No AI fallback in `reclassify` yet. |
| `index` | Stub | Exits with a "not implemented" message (`cli/commands.py::index`). The Obsidian modules it would call (`index_writer.py`) exist and are unit-tested in isolation — only the wiring is missing. |
| `audit` | Done | Shows `.microfiche/audit.log`, which `sort` and `rollback` append to (one line per move). |
| `rollback` | Done | Reverses a `sort` job by id, newest move first; refuses a job already rolled back; safe to retry if it stopped part-way. Failures print a message and exit 1. Also undoes `reclassify --apply` jobs, which go through the same `file_batch` path. |
| `config` | Done | Prints the library's loaded configuration (`cli/display.py::render_config`). |

## Cross-cutting feature status

- **AI fallback** — Ollama is wired via `--use-ai` (`cli/commands.py`), applied per stage by
  `Classifier`. At the default confidence threshold (0.75) an AI-only answer (0.70) is left for
  review, not filed — lower `[classification] confidence_threshold` to 0.7 to let it file. Measured at
  98% precision on one local model (see [calibration.md](calibration.md)), but only consulted where
  the rules are unsure, so it adds little as built.
  `OpenAIProvider`
  (`core/ai/openai_provider.py`) is fully implemented but never imported anywhere else —
  unreachable from the CLI despite `core`'s `ai` extra advertising `openai` support.
- **Obsidian tag governance** (`tag_index.py`, `tag_mapper.py`) — implemented, unit-tested,
  not called from the sort pipeline.
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
  it up front and exit 1 (`cli/commands.py::_open_library`); `audit` and `rollback` never read it, so a job can
  still be undone while the config is broken. A missing file or section still means defaults, silently;
  asking first is under Future work ("Ask before running on defaults").
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
4. **Open decision — not resolved here:** are `review` and `index` in MVP scope, or should
   they be explicitly descoped (removed from `cli/app.py` and marked "planned" in the README)
   rather than shipping as a stub that exits 1? This doc surfaces the question; the
   maintainer decides.

## Future work

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
  names file with full confidence on a substring (0 of 2 right on the corpus).
- **Use the AI where the rules are ambiguous or hint-level, and make its score configurable.** Today it is
  asked only when the rules are unsure, never about their confident mistakes, and always scores 0.70
  whatever model is behind it. Also: `OllamaProvider` doesn't disable the model's "thinking", so a call
  took about 5 s against about 2 s with it off on the model measured; its default model (`llama3`) may
  not be installed.
- **Review the other signal strengths** (hint 0.75, AI 0.70, and the other "move to config" constants in
  `rules/`), now that there is a harness to check them against.
- **Ask before running on defaults.** A missing `.microfiche/microfiche-config.toml`, or one that leaves out
  sections, silently falls back to the defaults (pinned by `test_load_config_missing_files_fall_back_to_defaults`
  and the CLI test for a library with no config folder). A misnamed config file or the wrong `--library` path
  therefore looks like a normal run on settings the user never chose. Instead, `sort`, `reclassify` and
  `propose-categories` should say which config was not found or which sections are being defaulted, and ask
  whether to proceed. Open questions: a non-interactive switch for scripts (for example `--use-defaults` or
  `--yes`), a non-zero exit when there is no terminal to ask on, whether a partial file warrants a prompt or
  only a notice, and how this fits a future `init` command that writes the default config. Today's
  invalid-config behaviour (an error, not a prompt) is unchanged.

## Deferred beyond MVP

Pulled forward from `architecture.md` §9 so it isn't confused with an unplanned gap: no
database, no vector store, no semantic search. `ai/` stays a fallback path for group/category
resolution and `propose-categories --use-ai`, not an always-on classification pass. ChromaDB,
RAG, and knowledge-graph work are future-roadmap items, not MVP scope.

## See also

- [architecture.md](architecture.md) — the current design this status is measured against.
- [data-model.md](data-model.md) — the ledger/audit/rollback schemas referenced above.
- [mvp-build-plan.md](mvp-build-plan.md) — a staged, from-scratch process for building to MVP
  (Plan/Design/Build/Test/Deploy per stage), if you're sequencing the work in this doc rather
  than just tracking status.
