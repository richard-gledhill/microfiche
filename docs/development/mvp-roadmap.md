# MVP roadmap

What's actually implemented vs. what `architecture.md` describes, and what's still blocking
a real MVP. Edit this in place as commands move from stub → partial → done — it's a living
doc, not a dated snapshot (same convention as `architecture.md`).

## CLI command status

| Command | Status | Notes |
|---|---|---|
| `sort` | Partial | Classifies and files correctly, but doesn't persist anything to `.microfiche/` — `filer.py`/`organizer.py` never call `save_job`, so `audit` and `rollback` have nothing to act on. |
| `review` | Stub | Exits with a "not implemented" message (`cli/commands.py:49-53`); the real interaction loop is parked, unwritten, in `cli/review.py`. |
| `propose-categories` | Partial | Works, but only scoped to the sorting inbox — scoping to an existing library folder isn't implemented. Print-only by design (never applies); that part is not a gap. |
| `resort` | Partial | Dry run works end-to-end. `--apply` is accepted but not wired to `core.filer.file_unit` (`cli/commands.py:85-86`) — it just prints a warning and does nothing. |
| `index` | Stub | Exits with a "not implemented" message (`cli/commands.py:89-93`). The Obsidian modules it would call (`index_writer.py`) exist and are unit-tested in isolation — only the wiring is missing. |
| `audit` | Partial | Reads `.microfiche/audit.log` if present, but nothing in the codebase ever writes that file. |
| `rollback` | Partial | `rollback_job`/`load_job` work correctly *if* a job file exists — but nothing ever calls `save_job` to create one, so there's currently no job to roll back. |

## Cross-cutting feature status

- **AI fallback** — Ollama is wired via `--use-ai` (`cli/commands.py`). `OpenAIProvider`
  (`core/ai/openai_provider.py`) is fully implemented but never imported anywhere else —
  unreachable from the CLI despite `core`'s `ai` extra advertising `openai` support.
- **Obsidian tag governance** (`tag_index.py`, `tag_mapper.py`) — implemented, unit-tested,
  not called from the sort pipeline.
- **Naming rules** (`library/naming.py`) — wired; `filer.py` applies them before filing.
- **Folder dominant-category voting** — wired, in `classifier.py::Classifier.classify_unit`.

## Must-fix before MVP

Ranked by how central they are to the product's core promise, not by ease of implementation.

1. **Wire audit/rollback persistence into `run_sort` and `resort --apply`.** The README's
   central safety claim — "every move is recorded and reversible" — isn't true yet. This is
   the single highest-priority gap: `sort` needs to call `core.rollback.save_job` after
   filing, and something needs to write `.microfiche/audit.log`.
2. ~~Reconcile the `.logs` vs `logs` path inconsistency.~~ **Resolved, then further
   consolidated.** `core/models/job.py`'s docstring and `cli/commands.py::_LOGS_DIRNAME` agree
   on a dot-prefixed convention — and that convention now shares one `.microfiche/` folder with
   `microfiche-config.toml` (`cli/commands.py::_CONFIG_DIRNAME`), rather than living in a
   separate `.microfiche-logs/` folder.
3. **Wire `resort --apply` to the filer**, reusing whatever persistence path (1) establishes.
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
- [data-model.md](data-model.md) — the sidecar/audit/rollback schemas referenced above.
- [mvp-build-plan.md](mvp-build-plan.md) — a staged, from-scratch process for building to MVP
  (Plan/Design/Build/Test/Deploy per stage), if you're sequencing the work in this doc rather
  than just tracking status.
