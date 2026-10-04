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
| `review` | Stub | Exits with a "not implemented" message (`cli/commands.py:49-53`); the real interaction loop is parked, unwritten, in `cli/review.py`. |
| `propose-categories` | Partial | Works, but only scoped to the sorting inbox — scoping to an existing library folder isn't implemented. Print-only by design (never applies); that part is not a gap. |
| `resort` | Done (for MVP scope) | Dry run previews each document's action (`move` / `keep` / `review` / `conflict`); `--apply` files the `move`s through `core.filer.file_batch` as one rollback-able job (`core/reclassify.py`). `--folder` must be inside the library. No AI fallback in `resort` yet. |
| `index` | Stub | Exits with a "not implemented" message (`cli/commands.py:89-93`). The Obsidian modules it would call (`index_writer.py`) exist and are unit-tested in isolation — only the wiring is missing. |
| `audit` | Done | Shows `.microfiche/audit.log`, which `sort` and `rollback` append to (one line per move). |
| `rollback` | Done | Reverses a `sort` job by id, newest move first; refuses a job already rolled back; safe to retry if it stopped part-way. Failures print a message and exit 1. `resort --apply` will reuse it once wired. |

## Cross-cutting feature status

- **AI fallback** — Ollama is wired via `--use-ai` (`cli/commands.py`). `OpenAIProvider`
  (`core/ai/openai_provider.py`) is fully implemented but never imported anywhere else —
  unreachable from the CLI despite `core`'s `ai` extra advertising `openai` support.
- **Obsidian tag governance** (`tag_index.py`, `tag_mapper.py`) — implemented, unit-tested,
  not called from the sort pipeline.
- **Naming rules** (`library/naming.py`) — wired; `filer.py` applies them before filing.
- **Classification ledger** (`core/ledger.py`) — wired; replaces the per-file `*.metadata.json`
  sidecars. Records path, content hash, group, category, reasons, confidence and `classified_by`
  per filing. Not yet recorded: `tags`, and the per-document breakdown for folder units.
- **Folder dominant-category voting** — wired, in `classifier.py::Classifier.classify_unit`.

## Must-fix before MVP

Ranked by how central they are to the product's core promise, not by ease of implementation.

1. ~~Wire audit/rollback persistence into `run_sort` and `resort --apply`.~~ **Done for
   `sort`:** `core.filer.file_batch` saves the job, appends the ledger and writes
   `.microfiche/audit.log`, and `rollback` undoes it. `resort --apply` uses the same path — see 3.
2. ~~Reconcile the `.logs` vs `logs` path inconsistency.~~ **Resolved, then further
   consolidated.** `core/models/job.py`'s docstring and the CLI agree on a dot-prefixed
   convention — and that convention now shares one `.microfiche/` folder with
   `microfiche-config.toml` (`core.config.MICROFICHE_DIRNAME`, used by both `core` and the CLI),
   rather than living in a separate `.microfiche-logs/` folder.
3. ~~Wire `resort --apply` to the filer.~~ **Done:** `core.reclassify.apply_reclassification`
   files the previewed `move`s via `core.filer.file_batch`, reusing the job/ledger/audit
   persistence from (1).
4. **Open decision — not resolved here:** are `review` and `index` in MVP scope, or should
   they be explicitly descoped (removed from `cli/app.py` and marked "planned" in the README)
   rather than shipping as a stub that exits 1? This doc surfaces the question; the
   maintainer decides.

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
