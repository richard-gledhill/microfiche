# Architecture: library-aware sorting

This supersedes the folder/module layout in [20260707_microfiche_prd_concept_1b.md](archive/20260707_microfiche_prd_concept_1b.md)
for the points below. Concept 1b's core principle — **the filesystem is the source of truth, no database,
JSON sidecars + JSON rollback jobs** — is unchanged and still governs everything here.

## Why this revision exists

Concept 1b assumed the classifier files documents into a static, config-defined `CATEGORY_MAP` and that "the
library" is the destination being built from scratch. In practice the library already exists, already has its
own folder taxonomy, and already has a live inbox folder that developers drop things into. This ADR reconciles
the design with that reality.

***

## 1. The library is the taxonomy — categories are discovered, not configured

`microfiche-config.toml`'s `[category_hints.categories]` table no longer defines *what categories exist*. It only supplies keyword hints that help the
rules engine match content to a category that **already exists as a folder** in the library.

A new taxonomy discovery step walks the library tree (excluding `_sorting/` and anything in
`microfiche-config.toml`'s `[exclusions]` table) and builds an in-memory index of `{group_name: [category_name, ...]}` on every run.
No taxonomy is persisted — the walk is cheap because it only reads directory names at a fixed depth, not file
contents.

```
core/library/taxonomy.py       # walks the library, returns {group: [category, ...]}, respects exclusions
```

## 2. Fixed depth model: group → category

Default library shape, matching the existing example library:

```
Projects/
├── Project Phoenix/          ← level 1: "group"
│   ├── 01 Requirements/      ← level 2: "category" (files land here)
│   ├── 02 Architecture/
│   └── ...
└── Project Atlas/
    ├── 01 Requirements/
    └── ...
```

`.microfiche/microfiche-config.toml`'s `[library_structure]` table:
```toml
[library_structure]
depth = 2
levels = ["group", "category"]
file_target_level = 2   # loose files (and kept-whole folders) are filed at the leaf
```
Depth is configurable for future flexibility, but 2 is the only depth the MVP implements against.

## 3. Sorting is a single, library-wide inbox — two-stage classification

**Decision:** one `_sorting/` folder at the library root, not one per group. This is the harder classification
problem — every item in it could belong to *any* project — so the classifier runs in two stages:

```
core/classifier.py
    resolve_group(document, taxonomy)     → GroupMatch(name, confidence, reason)
    resolve_category(document, group, taxonomy) → CategoryMatch(name, confidence, reason)
```

**Stage 1 — group resolution** (`rules/group_rules.py`, new):
* Filename/content keyword match against known group names.
* Fuzzy match (via `thefuzz`, already a dependency — this is what it's for) to catch near-misses like
  "Phoenix Project" vs "Project Phoenix".
* AI fallback (existing `ai/llm_classifier.py` path) only if rules produce no confident match: given the
  document text and the list of known group names, ask the model to pick one or say "none".

**Stage 2 — category resolution** (`rules/keyword_rules.py`, extended): once the group is known, this is
exactly concept 1b's original single-stage classification, scoped to that group's existing category folders.

**Overall confidence** = combination (min, not average — a confident category guess under an unconfident group
guess is still an unconfident result) of both stages. Anything below threshold goes to the review queue, and
the review prompt must let the user pick group *and* category, not just category, since group may be the part
that's actually unresolved.

If no existing group matches at all, that's not automatically "low confidence" — it's a distinct outcome
("no group found") that should also route to review, offering "create new group" as an explicit option
(review UX from the original PRD, extended with group-creation).

## 4. Sortable units: files and whole folders

`_sorting/` can contain loose files and folders-full-of-documents. Folder handling is **opt-in**
(`--keep-folders`, off by default) — when off, folders in `_sorting/` are left alone and reported, not
descended into.

```
core/models/unit.py
    SortableUnit:
        source_path: Path
        kind: "file" | "folder"
        documents: list[Document]   # one entry for a file, many for a folder
```

**Decision — mixed-category folders:** dominant category wins. Every document inside a folder unit is
classified individually (both stages); the folder is filed as a whole under whichever `(group, category)` pair
has the highest combined confidence / vote count across its documents. Per-document classification results are
still recorded (in the folder's sidecar, see §6) even though only one filing decision is physically applied —
so a human can see *why* a folder landed where it did. A folder with no majority (e.g. an even split across two
groups) is treated as "no group found" and routed to review, same as an individual unresolved document.

## 5. Exclusions

`microfiche-config.toml`'s `[exclusions]` table — glob patterns never treated as a category and never descended into by
`resort`/taxonomy discovery, matched against each path component (`core/utils/filesystem.py::is_excluded`).
Three pattern families, not one fixed list — see the shipped file for the current exact patterns rather than
duplicating them here, since that list has already changed once since this ADR was written:
- The inbox itself (`_sorting*`, the canonical inbox folder name; `sorting*` is also excluded for
  compatibility with libraries still using the older, pre-rename convention).
- Any dot-prefixed folder (`.*`) — covers `.microfiche/`, `.obsidian/`, `.git/` without needing
  their own entries.
- Any underscore-prefixed folder (`_*`) — a second, non-dot-prefixed convention for a library's own non-category
  folders (templates, attachments, archives) that should still be visible in Obsidian's file explorer.

User-extendable for anything not covered by those three families.

## 6. New capabilities beyond concept 1b

### Category proposal (never auto-applies)
```
core/library/category_suggester.py
```
Given a scope (the inbox, one group, or the whole library), extract common terms across the documents in scope
(keyword/TF-IDF frequency by default; `--use-ai` routes the same content through the existing `ai/` abstraction
for a smarter naming pass) and print candidate new category names with supporting evidence. Creating the actual
folder always requires an explicit `--apply` from the user — this function only ever suggests.

### Resort / re-review existing filings
```
core/resort.py
```
Re-runs the two-stage classifier against documents **already filed** in the library, scoped to `--folder <path>`
or `--all`. Always dry-run by default — prints a diff of "currently at X, classifier now suggests Y" — and only
moves anything with `--apply`, going through the same filer/audit/rollback path as an initial sort. This is how
classification drift or rule changes get reconciled after the fact, per the PRD's "preview before execution"
and rollback constraints.

### Obsidian integration
```
core/obsidian/
    index_writer.py   # generates/refreshes index.md per touched folder (a folder-note / MOC)
    tag_index.py       # parses the library's root TagIndex.md into a canonical tag vocabulary
    tag_mapper.py      # maps extracted keywords to TagIndex.md tags
```
**Decision — tag governance: suggest-only.** `tag_mapper` fuzzy-matches extracted tags against `TagIndex.md`'s
canonical list. A tag with no close match is still applied to the document, and is appended under a clearly
separated `## Proposed` section in `TagIndex.md` (never silently merged into the reviewed list) plus logged to
the audit trail, so a human can promote or reject it later.

`../index.md` is regenerated for every folder touched by a sort, resort, or rollback — not just created once —
so it always reflects current contents. Format:
```markdown
# 01 Requirements

- [[architecture_review]] — #requirements #phoenix (filed 2026-09-07, confidence 0.91)
- [[user_stories_q3]] — #requirements #backlog
```
Relative markdown links `[Title](file.ext)` are used for non-Markdown files (PDF/DOCX); `[[wikilinks]]` for
`.md` notes, matching normal Obsidian conventions.

## 7. Sidecar metadata schema (extended)

`*.metadata.json` gains fields beyond concept 1b's original three:
```json
{
  "group": "Project Phoenix",
  "category": "01 Requirements",
  "unit_type": "file",
  "confidence": 0.91,
  "classified_by": "rules_engine",
  "tags": ["requirements", "phoenix"],
  "processed_date": "2026-09-07"
}
```
A folder unit's sidecar additionally carries the per-document breakdown used to pick the dominant category.

## 8. CLI surface (supersedes concept 1a's command list)

```bash
microfiche sort [--keep-folders] [--use-ai]        # process the library-wide _sorting/ inbox
microfiche review                                    # work the low-confidence queue from the last sort
microfiche propose-categories [--scope PATH] [--use-ai] [--apply]
microfiche resort [--folder PATH | --all] [--apply]  # re-review already-filed documents
microfiche index [--scope PATH | --all]              # force-regenerate Obsidian index.md files
microfiche audit                                     # show the audit log
microfiche rollback --job-id ID                      # undo a job by id
```

## 9. Explicitly deferred (unchanged from concept 1b / the roadmap)

No database, no vector store, no semantic search in this MVP — `ai/` is a fallback path for group/category
resolution and for `propose-categories --use-ai`, not a always-on classification pass. Phase 2+ items
(ChromaDB, RAG, knowledge graph) remain future roadmap, not part of this ADR.

## See also

- [mvp-roadmap.md](mvp-roadmap.md) — what's actually implemented against this design vs. still stubbed.
- [data-model.md](data-model.md) — the sidecar/`AuditEvent`/`Job` schemas as actually implemented.
- [mvp-build-plan.md](mvp-build-plan.md) — a staged, from-scratch process for building to this design.
