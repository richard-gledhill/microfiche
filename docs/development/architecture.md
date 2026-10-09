# Architecture: library-aware sorting

This supersedes the folder/module layout in [20260707_microfiche_prd_concept_1b.md](archive/20260707_microfiche_prd_concept_1b.md)
for the points below. Concept 1b's core principle — **the filesystem is the source of truth, no database,
plain files only (originally JSON sidecars; now a JSONL ledger in `.microfiche/`, see §7) plus JSON rollback jobs**
— is unchanged and still governs everything here.

## Why this revision exists

Concept 1b assumed the classifier files documents into a static, config-defined `CATEGORY_MAP` and that "the
library" is the destination being built from scratch. In practice the library already exists, already has its
own folder taxonomy, and already has a live inbox folder that developers drop things into. This ADR reconciles
the design with that reality.

***

## 1. The library is the taxonomy — categories are discovered, not configured

`microfiche-config.toml`'s `[category_hints.categories]` table no longer defines *what categories exist*. It only supplies keyword hints that help the
rules engine match content to a category that **already exists as a folder** in the library.

A taxonomy discovery step walks the library tree (excluding the inbox, the `.microfiche/` state folder, and anything in
`microfiche-config.toml`'s `[exclusions]` table) and builds an in-memory index of `{group_name: [category_name, ...]}` on every run.
No taxonomy is persisted — the walk is cheap because it only reads directory names at a fixed depth, not file
contents.

```
core/library/library.py        # Library: layout (inbox, state folder, target folders), exclusions, and
                               #   Library.taxonomy() -> {group: [category, ...]}
```

## 2. Fixed depth model: group → category

Default library shape, matching the existing example library:

```
Library/
├── Project Phoenix/          ← level 1: "group" (here, a project)
│   ├── 01 Requirements/      ← level 2: "category" (files land here; here, a document type)
│   ├── 02 Architecture/
│   └── ...
└── Project Atlas/
    ├── 01 Requirements/
    └── ...
```

"Group" and "category" are roles, not meanings. A project is the usual group, but the same two-level shape fits
other taxonomies — for example project › stage (`Project Phoenix/03 Build/`), client › document type, or
course › topic. The classifier only ever matches group *names* against document text and category names or
keyword hints, so the user guides ([README](../../README.md#how-a-library-is-organised),
[how-to-use](../how-to-use.md#other-ways-to-organise-a-library)) show how to pick names that work.

`.microfiche/microfiche-config.toml`'s `[library_structure]` table:
```toml
[library_structure]
depth = 2
levels = ["group", "category"]
file_target_level = 2   # loose files (and kept-whole folders) are filed at the leaf
```
Depth is configurable for future flexibility, but 2 is the only depth implemented today. Stage 4.6 plans depth 1
(groups only), and Stage 4.7 plans depth 3 (group, category, subcategory), provisionally; see
[library-depth.md](library-depth.md). The word *group* is used at every depth.

## 3. Sorting is a single, library-wide inbox — two-stage classification

**Decision:** one inbox folder at the library root (`_sorting/` unless the config's `[library_structure] library_inbox`
names another), not one per group. This is the harder classification
problem — every item in it could belong to *any* group — so the classifier runs in two stages:

```
core/classifier.py          # Classifier: owns the flow, the threshold, the taxonomy check
    Resolver (protocol)      # what Classifier asks; each answer is a GroupMatch / CategoryMatch
        resolve_group(document, taxonomy)           → GroupMatch(name, confidence, reason)
        resolve_category(document, group, taxonomy) → CategoryMatch(name, confidence, reason)
rules/rules_engine.py        # Resolver adapter 1: deterministic rules
ai/llm_classifier.py         # Resolver adapter 2: the AI fallback
```

**Stage 1 — group resolution** (`rules/group_rules.py`, new):
* Match against known group names in the document text (groups have no keyword hints).
* Fuzzy match (via `thefuzz`, already a dependency — this is what it's for) to catch near-misses like
  "Phoenix Project" vs "Project Phoenix".
* AI fallback (`ai/llm_classifier.py`) only if the rules' answer is missing or below the confidence threshold:
  given the document text and the list of known group names, ask the model to pick one or say "none". A
  confident rules answer is never overridden, and an AI "none" leaves the rules' weak suggestion in place.

**Stage 2 — category resolution** (`rules/keyword_rules.py`, extended): once the group is known, this is
exactly concept 1b's original single-stage classification, scoped to that group's existing category folders.
The same per-stage fallback applies: rules first, the AI only for a category the rules couldn't resolve
confidently. Whoever proposes a group or category, `Classifier` checks it against the taxonomy; a name that
isn't an existing folder is treated as unresolved, so the filer never creates a folder.

**Overall confidence** = combination (min, not average — a confident category guess under an unconfident group
guess is still an unconfident result) of both stages. A result is *confident* — and so filed without asking —
when both stages resolved and that overall confidence reaches the **confidence threshold**: the library's
`[classification] confidence_threshold` (0 to 1), defaulting to 0.75. Today's signal strengths are 1.0 for an
exact group name, 0.95 for a filename rule, 0.90 for a category name, 0.85–0.99 for a fuzzy group match, 0.75
for a category keyword hint and 0.70 for an AI answer, so at the default threshold everything but AI-only
answers files; a library raises the threshold to hold hint matches for review, or lowers it to 0.7 to file AI
answers. The default was set by measurement ([calibration.md](calibration.md)), which found that a higher
threshold files less without filing more accurately: the scores reflect the kind of evidence, not how reliable
it is. Anything below the
threshold goes to the review queue, and
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
has the most votes across its documents, represented by that pair's most confident document. Per-document
classification results are
meant to be recorded (in the ledger, see §7 — not implemented yet) even though only one filing decision is physically applied —
so a human can see *why* a folder landed where it did. If two or more `(group, category)` pairs tie for the
most votes (e.g. an even split across two groups) the folder is **not** guessed: it is left unresolved and
routed to review, with the disagreement as its reason — same as an individual unresolved document. A unique
winner is enough; it does not need a strict majority. Documents whose group didn't resolve don't vote.

**Decision — files that can't be read:** a supported file that can't be parsed (corrupt, truncated) must not
abort the run. The parsers module wraps any parser failure in `UnreadableDocumentError`; the scanner records
such files on their unit's `unreadable` list instead of raising. They don't take part in classification, and a
unit with no readable document at all is left unresolved — routed to review with "Could not read '<file>': …"
as the reason — while everything else is sorted as normal. A folder with some unreadable files is classified by
its readable ones and moves whole, as always.

## 5. Exclusions

`microfiche-config.toml`'s `[exclusions]` table — glob patterns never treated as a category and never descended into by
`reclassify`/taxonomy discovery, matched against each component of the path *relative to the library root*
(`Library.is_excluded`, which uses `core/utils/filesystem.py::is_excluded`) — never against the folders above the
library, so a library kept under `~/.vaults` or `~/_work` behaves like any other. Two folders are excluded
structurally, whatever the config says: the library's inbox and its `.microfiche/` state folder.
Three pattern families, not one fixed list — see the shipped file for the current exact patterns rather than
duplicating them here, since that list has already changed once since this ADR was written:
- Inbox-style folders (`_sorting*`, `sorting*`). The library's own inbox is excluded automatically; these stay
  so that other inbox-style folders — for example the inboxes of sub-libraries nested inside it — are kept out of
  the taxonomy too.
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

### Reclassify / re-review existing filings
```
core/reclassify.py
```
Re-runs the two-stage classifier against documents **already filed** in the library, scoped to `--folder <path>`
(inside the library) or the whole library. Always dry-run by default — prints a table of "currently at X, classifier
now suggests Y" with the action `--apply` would take for each document — and only moves anything with `--apply`,
going through the same `file_batch` path as an initial sort, so it is one job in the ledger and audit log and can
be undone with `rollback`. This is how classification drift or rule changes get reconciled after the fact, per the
PRD's "preview before execution" and rollback constraints.

Each document gets one action: `move` (confident, and not already under the proposed category folder), `keep`
(already under it, even in a subfolder), `review` (unresolved or below the confidence threshold — never moved
automatically), or `conflict` (the destination file already exists, or another document in the same run is headed
there — left alone rather than overwritten).

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

`../index.md` is regenerated for every folder touched by a sort, reclassify, or rollback — not just created once —
so it always reflects current contents. Format:
```markdown
# 01 Requirements

- [[architecture_review]] — #requirements #phoenix (filed 2026-09-07, confidence 0.91)
- [[user_stories_q3]] — #requirements #backlog
```
Relative markdown links `[Title](file.ext)` are used for non-Markdown files (PDF/DOCX); `[[wikilinks]]` for
`.md` notes, matching normal Obsidian conventions.

## 7. Classification ledger (replaces per-file sidecars)

Concept 1b wrote a `*.metadata.json` sidecar beside every filed document. That is replaced by a single
append-only ledger, `.microfiche/ledger.jsonl`, with one record per filing (and one per rollback):
```json
{"event": "filed", "job_id": "20261004-153012-a1b2c3", "path": "Project Phoenix/01 Requirements/architecture_review.md",
 "original_path": "_sorting/architecture_review.md", "content_hash": "9f2c…", "unit_type": "file",
 "group": "Project Phoenix", "category": "01 Requirements", "confidence": 0.91, "classified_by": "rules_engine", …}
```
Why: sidecars doubled the file count of a vault, went stale when a file was renamed or moved outside microfiche, were
left behind by rollback (nothing recorded them), and nothing ever read them. The ledger lives with the rest of
microfiche's own state in the hidden `.microfiche/` folder, is keyed by **path + content hash** so a record can be
found again after a move or rename, and is replayed to get the library's current state. Full schema and semantics:
[data-model.md](data-model.md). Still to add: `tags`, and for a folder unit the per-document breakdown used to pick
the dominant category.

## 8. CLI surface (supersedes concept 1a's command list)

```bash
microfiche sort [--keep-folders] [--use-ai]        # process the library-wide _sorting/ inbox
microfiche review                                    # work the low-confidence queue (stub - see mvp-roadmap.md)
microfiche propose-categories                        # suggest category names from the inbox; print-only
microfiche reclassify [--folder PATH] [--apply]      # re-review already-filed documents
microfiche index [--scope PATH]                      # force-regenerate Obsidian index.md files (stub)
microfiche audit                                     # show the audit log
microfiche rollback --job-id ID                      # undo a job by id
microfiche config                                    # show the library's loaded configuration
```

Every command also takes `--library PATH`. Scoping `propose-categories` to a library folder, and its `--use-ai`
variant (§6), are designed but not built; see [mvp-roadmap.md](mvp-roadmap.md) for each command's status.

## 9. Explicitly deferred (unchanged from concept 1b / the roadmap)

No database, no vector store, no semantic search in this MVP — `ai/` is a fallback path for group/category
resolution and for `propose-categories --use-ai`, not a always-on classification pass. Phase 2+ items
(ChromaDB, RAG, knowledge graph) remain future roadmap, not part of this ADR.

## 10. Configuration layout (planned, Stage 4.1)

**Not built yet.** §1-§9 describe what exists; this section is the target for
[Stage 4.1](mvp-build-plan.md#stage-41--configuration-consolidation). The reasoning for each point is in
[config-review.md](config-review.md).

```
core/defaults/microfiche-config.toml   # packaged defaults, the only source of default values
<library>/.microfiche/microfiche-config.toml   # the library's overrides, deep-merged over the defaults
<library>/.microfiche/microfiche-library.json  # this library's category hints and filing rules (data, not settings)
```

* **Defaults live in one packaged file.** The loader reads it, deep-merges the library's file over it (tables
  merge key by key, lists replace), then validates. The pydantic models no longer carry default values. This
  replaces today's two sources (the models and the repo-root `microfiche/` template), which already disagree.
* **Settings and data are separate.** `microfiche-config.toml` holds behaviour only. `category_hints` and
  `filing_rules` move to `microfiche-library.json`, a recursive `{name, hints, rules, children}` node format
  with a generated JSON Schema. Hints still only match folders that already exist (§1); they never define
  the taxonomy. `naming_rules` stays in the TOML.
* **Depth is the only structural setting in the config.** `[library_structure] depth` stays and is validated
  against the supported range (2 today; 1–2 from Stage 4.6, and 3 from Stage 4.7 if it goes ahead); `levels` and `file_target_level` are dropped (`levels` moves to the JSON if it is kept at all).
  `library_templates` is dropped until an `init` command exists; a template catalog would reuse the library
  file's node schema.
* **Scores and thresholds are config.** `[classification]` gains the signal strengths (name, filename rule,
  keyword hint, AI) and the fuzzy-match thresholds, passed into `RulesEngine` and `LLMClassifier` by
  constructor. `confidence_threshold` keeps its meaning; the shipped values reproduce today's behaviour.
* **`[sorting] keep_folders`** defaults to `true` (§4 then reads "on by default"); `--keep-folders` stays a
  boolean switch and `--keep-folders-off` is its counterpart (passing both is an error); whichever is passed
  overrides the config. With it off (Stage 4.2), an inbox folder is no
  longer ignored (as §4 describes today): its documents are filed one by one, and the emptied folder is
  removed and recorded in the job so `rollback` can recreate it. A folder that isn't empty afterwards stays,
  and the report says why.
* **`[ai]`** names the kind of classifier (a chat model, or from Stage 4.5 a decision model that returns a bounded choice with a probability; see [ai-classifier-options.md](ai-classifier-options.md)), the provider (`ollama` or `openai`), model, host, timeout and score; `core.ai` builds the
  provider from it. A `command` provider (the config names a program to run) is deferred behind a security
  decision.

## See also

- [config-review.md](config-review.md) — why the configuration is being reorganised, and what was weighed.
- [mvp-roadmap.md](mvp-roadmap.md) — what's actually implemented against this design vs. still stubbed.
- [data-model.md](data-model.md) — the ledger/`AuditEvent`/`Job`/`audit.log` schemas as actually implemented.
- [mvp-build-plan.md](mvp-build-plan.md) — a staged, from-scratch process for building to this design.
