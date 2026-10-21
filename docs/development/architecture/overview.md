# Architecture: library-aware sorting

This supersedes the folder/module layout in [20260707_microfiche_prd_concept_1b.md](../requirements/archive/20260707_microfiche_prd_concept_1b.md)
for the points below. Concept 1b's core principle — **the filesystem is the source of truth, no database,
plain files only (originally JSON sidecars; now a JSONL ledger in `.microfiche/`, see §7) plus JSON rollback jobs**
— is unchanged and still governs everything here.

## Why this revision exists

Concept 1b assumed the classifier files documents into a static, config-defined `CATEGORY_MAP` and that "the
library" is the destination being built from scratch. In practice the library already exists, already has its
own folder taxonomy, and already has a live inbox folder that developers drop things into. This ADR reconciles
the design with that reality.

Paths such as `core/library/library.py` are shorthand for `packages/core/src/microfiche/core/library/library.py`: the
`core` and `cli` distributions import as `microfiche.core` and `microfiche.cli` (a shared namespace package).

***

## 1. The library is the taxonomy — categories are discovered, not configured

The folders decide *what groups and categories exist*. The library file (`.microfiche/microfiche-library.json`, Stage 4.1) holds the keyword hints and
filename rules that help the rules engine match content to a category that **already exists as a folder**. From Stage 4.10 it is also created from the
folders, to the configured depth, on the first run, and kept in step: a folder the user adds is found and added on the next run, and an entry whose
folder has gone is reported but never used or removed. **The folders always win**: filing is checked against the folders that exist, the file never
creates or removes a folder, and regenerating it never overwrites what the user wrote.

A taxonomy discovery step walks the library tree (excluding the inbox, the `.microfiche/` state folder, and anything in
`microfiche-config.toml`'s `[exclusions]` table) and builds an in-memory index of `{group_name: [category_name, ...]}` on every run.
The taxonomy used for filing is never read from the file — it is computed from the folders on every run, and the walk is cheap because it only reads
directory names at a fixed depth, not file contents.

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
keyword hints, so the user guides ([README](../../../README.md#how-a-library-is-organised),
[how-to-use](../../how-to-use.md#other-ways-to-organise-a-library)) show how to pick names that work.

`.microfiche/microfiche-config.toml`'s `[library_structure]` table:
```toml
[library_structure]
library_inbox = "_sorting"
depth = 2
```
Depth is 1 or 2; any other value is rejected with a message saying so. Loose files and kept-whole folders are filed at the
leaf. Depth 3 (group, category, subcategory) is in the [feature backlog](../rfcs/RFC-006-subcategories-depth-3.md), under review; see [library-depth.md](library-depth.md).
The word *group* is used at every depth.

**Depth 1 — a flat library** (Stage 4.6). A library of group folders only: a document is filed straight into one. The
taxonomy says so itself (`Taxonomy.depth`, `is_flat`), because an empty category list could otherwise mean either "no
categories at this depth" or "a group with nowhere to file into". `Classifier` then runs one stage: the confidence is the
group's, the AI fallback is asked the group prompt only, and a folder unit's vote is on the group alone.
`ClassificationResult.category` is `None` (not an unresolved `CategoryMatch`), and `ClassificationResult.folders` is the
tuple of folder names to file under, `(group,)` or `(group, category)`, so the filer, `reclassify` and the duplicate check
do not care how many levels there are. With only its folder names to go on, a flat library's group entries in the library
file take `hints` and `rules`: `RulesEngine.resolve_group` tries a filename rule, then the group's name, then its hints.

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

**Stage 1 — group resolution** (`rules/group_rules.py`):
* Match against known group names in the document text. At depth 2 groups have no keyword hints; a flat library's groups do (§2).
* Fuzzy match (via `rapidfuzz`, a direct dependency — this is what it's for) to catch near-misses like
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
answers. The default was set by measurement ([calibration.md](../testing/calibration.md)), which found that a higher
threshold files less without filing more accurately: the scores reflect the kind of evidence, not how reliable
it is. Anything below the
threshold goes to the review queue, and
the review prompt must let the user pick group *and* category, not just category, since group may be the part
that's actually unresolved.

If no existing group matches at all, that's not automatically "low confidence" — it's a distinct outcome
("no group found") that also routes to review, where "create new" is an explicit option for the group
(review UX from the original PRD, extended with group-creation; see §8).

## 4. Sortable units: files and whole folders

`_sorting/` can contain loose files and folders-full-of-documents. Folders are kept whole **by default**
(`[sorting] keep_folders = true`; `sort --keep-folders` and `--keep-folders-off` override it for one run). When it is
off, the scanner descends into each folder and every supported file in it, including those in nested sub-folders,
becomes a single-document unit of its own, filed on its own merits. The unit remembers the top-level inbox folder it
came from (`origin_folder`); see "Decision — emptied inbox folders" below. A folder with no supported file is left
alone either way.

```
core/models/unit.py
    SortableUnit:
        source_path: Path
        kind: "file" | "folder"
        documents: list[Document]   # one entry for a file, many for a folder
```

**Decision — a folder that was filed whole is content, not structure.** A folder within the depth is a filing target
unless `[exclusions]` skips it; a folder beyond the depth is content. The ledger (`unit_type: "folder"`,
`Ledger.folder_units()`) says which folders microfiche filed whole, and `reclassify` classifies each as one unit and
proposes it whole, so a filed bundle is never split; `Library.structure()` skips it, so it never becomes a category if
the depth is raised. Any other folder below a category is read file by file; the user keeps one out with `[exclusions]`.

**Decision — mixed-category folders:** dominant category wins. Every document inside a folder unit is
classified individually (both stages); the folder is filed as a whole under whichever `(group, category)` pair
has the most votes across its documents, represented by that pair's most confident document. Per-document
classification results are
meant to be recorded in the ledger (§7; the ledger records the folder's one decision today, not the per-document breakdown)
even though only one filing decision is physically applied — so a human can see *why* a folder landed where it did. If two or more `(group, category)` pairs tie for the
most votes (e.g. an even split across two groups) the folder is **not** guessed: it is left unresolved and
routed to review, with the disagreement as its reason — same as an individual unresolved document. A unique
winner is enough; it does not need a strict majority. Documents whose group didn't resolve don't vote.

**Decision — files that can't be read:** a supported file that can't be parsed (corrupt, truncated) must not
abort the run. The parsers module wraps any parser failure in `UnreadableDocumentError`; the scanner records
such files on their unit's `unreadable` list instead of raising. They don't take part in classification, and a
unit with no readable document at all is left unresolved — routed to review with "Could not read '<file>': …"
as the reason — while everything else is sorted as normal. A folder with some unreadable files is classified by
its readable ones and moves whole, as always.

**Decision — a unit never overwrites, renames or deletes anything.** After a unit is classified, two further
checks can hold it in the inbox. Neither changes any file: the unit stays where it is and the report says why.
`sort` makes them in this order, and the first one a unit fails decides where it is listed.

1. **Duplicate** (`core/duplicates.py`). A *file* unit whose bytes (SHA-256) match a file already in the library,
   in any group or category, or a file already being filed earlier in the same run, goes to `SortReport.duplicates`
   — not to `needs_review`, because it is not a classification question. It is classified first, so the reason can say
   where it would have gone: "already filed where this would go", "in the folder this would be filed to", or "this would
   be filed in X/Y" when the copy is somewhere else. A duplicate that is unconfident or unresolved is listed once, here.
   Only new files are checked, in one direction: the inbox against the library. A project often keeps the same reference
   document in several places, so duplicates already inside the library are never looked for or reported, and the check
   has no setting. A folder unit kept whole is not checked (its files are checked individually when `keep_folders` is
   off). `DuplicateIndex` is built lazily on the first file: one library walk reading only sizes (skipping the inbox, the
   state folder and exclusions), and a file is hashed only when another file of the same size is in play. Empty files are
   never duplicates.
2. **Collision** (`filer.py::DestinationClaims`). If the destination name — after the naming rules — already exists, or
   another unit in the same run is already going there (the first in scan order wins), the unit goes to `needs_review`
   with the collision appended to its reason. The group and category it was given are kept. `reclassify` uses the same
   claims for its `conflict` action. `file_batch` still refuses to overwrite, as the last line of defence for a path that
   is taken between planning and moving.

A held duplicate does not claim its destination, so it cannot block a different file.

**Decision — emptied inbox folders.** With `keep_folders` off, once every unit is filed, `file_batch` removes each inbox
folder the units came from if nothing at all is left inside it (only empty directories), deepest first, with
`Path.rmdir`, which refuses a directory that has anything in it. A folder that still holds a file stays, and the report
names the file and why it stayed: not a document, still needs review, or a duplicate. Each removal is a `remove_folder`
event in the job, and `rollback` recreates the folder (`restore_folder`) before putting its files back. This is the only
thing microfiche ever removes: no file is deleted, and the folder is empty when it goes.

**Decision — a failure belongs to one unit, not to the run.** One awkward input never aborts a `sort`:

- *A move is a plain rename* (`core.utils.filesystem.safe_move`), never a copy followed by a delete. `shutil.move`
  quietly falls back to copy-then-delete when a rename fails, and on Windows, when Word has the file open, the rename
  fails, the copy succeeds and the delete fails, leaving a full copy that no job, ledger or audit line knows about (the next
  run then holds the original as a duplicate of it). A rename either happens or changes nothing. There is no
  cross-volume fallback: the inbox is inside the library, so a move across volumes is almost unreachable, and the case
  fails with the operating system's error.
- `file_batch` returns a `FilingResult` (the job, and the units that failed). A move that raises an `OSError` is not
  recorded, its reason is put into plain language (a file in use becomes "it is open in another program; close it and
  sort again"), and the rest of the batch is filed. `run_sort` moves such a unit to `needs_review` with the reason,
  keeping the group and category it was given. The job only ever holds moves that happened, so `rollback` needs to know
  nothing about failures.
- The AI fallback: any exception from the provider (a connection failure, a timeout, a missing optional package) makes
  `LLMClassifier` stop asking for the rest of the run, answering "no match" so the rules' answers stand. The first failure
  is kept (`failure`), logged once at WARNING, and exposed as data in `SortReport.ai_unavailable`; the CLI prints no line
  of its own for it, so the user sees the one warning (see "core emits, the CLI configures logging" below).
- Inputs are filtered before they are read: names matching `[sorting] ignore` are skipped without comment, a symlink or
  Windows junction is skipped and listed (`is_link` checks the reparse *tag*, because OneDrive's on-demand placeholders are
  reparse points too), and a file over `[parsing] max_file_mb` is refused by `parse_document` before it is opened, so it
  reaches review as an unreadable document with the reason.

**Decision — a preview is the same run with one step left out.** `sort --dry-run` runs `run_sort(dry_run=True)`: scan,
classify, duplicate and name checks, and any AI calls, but not `file_batch`. It writes no job, ledger or audit line and
takes no lock, and creates no state folder. Because the real code path is shared, a preview cannot drift from a real run.
The one piece of new logic is predicting which inbox folders would be removed once emptied.

**Decision — one run at a time.** `sort` (not `--dry-run`), `reclassify --apply`, `rollback`, `config --sync` and `review` (only
when it files, at the end) take `.microfiche/lock` (`core/runlock.py`) at the CLI level, so `reclassify --apply` can hold it from
planning to filing. The file is created
atomically (`O_CREAT | O_EXCL`) and holds the process id, command and start time. A lock whose process no longer exists
is stale and is cleared; a lock file that cannot be read counts as held and is never cleared, because guessing wrong
would let two runs through while deleting one file is an easy request to make. On Windows the process check uses the
operating system's process API: `os.kill(pid, 0)` must not be used there, since it sends the process a Ctrl-C. Previews
and read-only commands take no lock. A lock timeout and a `--force` override are deferred.

**Decision — core emits, the CLI configures logging.** Every module that logs has `_logger = logging.getLogger(__name__)`
(`microfiche.core.*`, `microfiche.cli.*`), and `core/__init__.py` adds a `NullHandler` to the `microfiche.core` logger and nothing else, so `core` is quiet
when used as a library. Only the CLI installs handlers (`cli/logging.py::configure_logging`), and only on the `microfiche.core` and
`microfiche.cli` loggers, not the root, so a third party's records (the AI SDKs' HTTP clients) stay out and `propagate` stays on for
`caplog`. The loggers pass every record on and each handler filters, so `-v` and `-q` can differ from the file: the console
(stderr) shows WARNING and above, INFO with `-v`, errors only with `-q` (which wins); the file records `[logging] level`,
or DEBUG with `-v`. The file is a rotating UTF-8 `.microfiche/microfiche.log`, opened lazily, and is attached only by a
command that holds the run lock (`sort` without `--dry-run`, `reclassify --apply`, `rollback`, `config --sync`, `review` when
it files), so a preview creates
nothing and only the lock holder ever rotates it. The commands enter `_locked` before `_logging`: a run the lock refuses
raises before logging starts and leaves no trace. `_logging` is a context manager so the handlers are always removed
when the command ends, and a library whose config cannot be read still rolls back, logging to the screen only.
Two kinds of record are kept apart: the ledger and `audit.log` are product data that `rollback` and `audit` read, and
the log is for people and can change. A decision is logged by its names, scores and reasons, never the document's text.
A message the user has already been told on screen is logged with `extra=FILE_ONLY`, which a filter on the console handler
keeps off the screen. `run_lock` logs nothing itself, because it runs outside the logging window; it yields the holder
of a stale lock it cleared, `_locked` passes that to the command, and `_logging` logs it as a WARNING, so the lock-first
order that keeps a refused run out of the log also leaves a way for the lock to be heard.

**Decision — output is UTF-8 and never aborts a command.** `cli/streams.py::prepare_output_streams` runs first in `main()`. When stdout or
stderr is a pipe, a file or a pseudo-terminal (Git Bash), Python on Windows uses the legacy code page, so a message's em dash is
the cp1252 byte `0x97` and shows as a block; it reconfigures them to UTF-8. And when the reader goes away (`microfiche sort | head`)
the next write fails with `EPIPE`, or `EINVAL` on Windows, which Rich does not treat as a closed pipe; a stream that is not a
terminal is wrapped so that failure ends the output, not the command, which has already filed and recorded everything before it
reports. Any other `OSError` is still raised.

**Decision — progress is a callback.** `run_sort` and `run_reclassify` take an optional `progress(done, total)`, called
first with `(0, total)` and then as each unit finishes, so `core` reports progress without importing Rich. `cli/progress.py`
turns it into a bar on the same stderr console as the log lines, and decides once, from the first call, whether to draw:
only on a terminal, never with `-q`, only when there is something to count, and then for 20 or more units or when the AI
is used.

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
Extracts common terms across the documents in the inbox (keyword frequency) and prints candidate new category names with
supporting evidence. It only ever suggests: it never creates a folder, and a person makes one themselves (or plans one in
`review`). Built: the inbox scope, and print-only. Designed but not built: a scope of one group or the whole library, a
`--use-ai` pass for better names, and an `--apply` that creates the chosen folders.

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

**Not part of the MVP.** The `index.md` folder notes and the `TagIndex.md` tag governance (suggest-only) were never
called from the pipeline, and were removed so the MVP stays at "classify, file, undo and review". They are to come back
as a plugin rather than as code in `core`; the design, the code to restore and the open questions are in
[feature-backlog.md](../rfcs/RFC-002-obsidian-integration.md). For now microfiche stays out of the way: its state lives
in the hidden `.microfiche/` folder (§7), so no file is added beside the user's documents.

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
[data-model.md](data-model.md). Still to add: for a folder unit, the per-document breakdown used to pick the dominant
category. A `tags` field is parked with the Obsidian integration (§6).

## 8. CLI surface (supersedes concept 1a's command list)

```bash
microfiche init                                      # set up the library's config, or check and edit it
microfiche sort [--keep-folders | --keep-folders-off] [--use-ai] [--dry-run]        # process the library-wide _sorting/ inbox
microfiche review [--use-ai]                         # decide, one by one, what sort left in the inbox
microfiche propose-categories                        # suggest category names from the inbox; print-only
microfiche reclassify [--folder PATH] [--apply]      # re-review already-filed documents
microfiche audit                                     # show the audit log
microfiche rollback --job-id ID | --last             # undo a job by id, or the newest one not yet undone
microfiche --version                                 # print the installed version
microfiche config [--sync]                           # show the loaded configuration; --sync updates the library file from the folders
```

**Decision — `review` has no stored queue.** What `sort` leaves behind is exactly what a preview sort would leave
(`ReviewSession.start`), so the inbox is the queue and there is no report to keep in step. A person's choice becomes a
`ClassificationResult` with `classified_by = "user"`, and goes through the same checks and the same `file_batch` as a
sorted unit, so it is recorded, rollback-able and never overwrites. The choices are only staged until one confirmation,
and the run lock is held only while filing, so deciding never blocks another run. A new group or category folder is
planned in the session and made by filing into it.

Every command also takes `--library PATH`, and each command that opens a library takes `-v`/`--verbose` and
`-q`/`--quiet`. Scoping `propose-categories` to a library folder, and its `--use-ai`
variant (§6), are designed but not built; see [mvp-roadmap.md](../requirements/mvp-roadmap.md) for each command's status. An `index`
command, for regenerating Obsidian folder notes, was part of this surface and left the MVP with the Obsidian
integration (§6).

## 9. Explicitly deferred (unchanged from concept 1b / the roadmap)

No database, no vector store, no semantic search in this MVP — `ai/` is a fallback path for group/category
resolution and for `propose-categories --use-ai`, not an always-on classification pass. Phase 2+ items
(ChromaDB, RAG, knowledge graph) remain future roadmap, not part of this ADR.

Other deferred work is in [mvp-roadmap.md](../requirements/mvp-roadmap.md#future-work-and-deferred-beyond-mvp) and
[feature-backlog.md](../rfcs/feature-backlog.md).

## 10. Configuration layout

Built in [Stage 4.1](../plan/archive/2026-10-mvp/plan.md#stage-41--configuration-consolidation). The reasoning for each point is in
[ADR-001](../adr/ADR-001-configuration-layout.md).

```
core/defaults/microfiche-config.toml   # packaged defaults, the only source of default values
<library>/.microfiche/microfiche-config.toml   # the library's overrides, deep-merged over the defaults
<library>/.microfiche/microfiche-library.json  # this library's folder tree with hints and filing rules (data, not settings)
```

* **Defaults live in one packaged file.** `load_config` reads `core/defaults/microfiche-config.toml`, deep-merges the
  library's file over it (tables merge key by key, lists replace), then validates. The pydantic models carry no default
  values, so a key missing from the packaged file fails loudly. The template in `microfiche/` lists the same settings, and
  tests keep the two in step.
* **`init` writes and edits the library's file** (`core/library_init.py`, post-MVP,
  [library-init-prd.md](../requirements/library-init-prd.md)). A new library gets the packaged defaults file as it is;
  every setting there has a comment, which `init` shows as its explanation. An existing file is edited as a `tomlkit`
  document, so comments and layout survive and a changed setting rewrites only its value. An entered value is checked
  by validating the whole candidate config (`validate_config`), and `ConfigError.problems` locates each problem so an
  invalid file can have just those settings reverted. The write keeps a `.bak`, refuses a file changed since it was
  read, and goes through a temporary file and a rename under the run lock. `sort`, `reclassify` and
  `propose-categories` refuse a library with no config file and point to `init`; `load_config` itself still falls back
  to the defaults.
* **Settings and data are separate.** `microfiche-config.toml` holds behaviour only. The category hints and filing rules
  are in `microfiche-library.json` (`core/library/library_file.py`): a recursive tree of folder nodes
  `{name, description, hints, rules, children}` whose top level is the groups. A node named `*` stands for any folder at
  its level, so hints can be shared by every group, and a named group adds its own; the most specific entry comes first.
  `Library.library_file` loads it lazily, checked against `depth`. A missing file means no hints, and an invalid one stops
  `sort` and `reclassify` before anything moves. Its JSON Schema is generated (`make library-schema`) so editors can
  validate it. Hints and rules only match folders that already exist (§1). `naming_rules` stays in the TOML. The file is
  created from the folders, and kept in step, by `core/library/library_sync.py::sync_library_file`
  ([Stage 4.10](../plan/archive/2026-10-mvp/plan.md#stage-410--library-file-sync)): it diffs `Library.structure()` (the sorted,
  exclusion-aware, link-skipping walk to `depth`, of which `Library.taxonomy()` is a view) against the file and appends
  an entry, with no hints, for each folder that has none. A `*` entry at a level covers its folders, so none is added
  for them. It runs at the start of a real `run_sort` and from `config --sync`, both under the run lock, never for a
  preview, and writes through a temporary file and a rename, only when something was added. Entries with no folder
  are reported, never removed.
* **Depth is the only structural setting.** `[library_structure] depth` is validated against `SUPPORTED_DEPTHS` (1 and 2;
  [depth 3](../rfcs/RFC-006-subcategories-depth-3.md) is in the backlog). `levels`, `file_target_level` and `library_templates` are
  gone; a template catalog would reuse the library file's node shape.
* **Scores and thresholds are config.** `[classification]` holds the confidence threshold, the match strengths (category
  name, filename rule, keyword hint) and the group fuzzy-match threshold (a RapidFuzz partial-ratio score, rounded to a
  whole number). `[ai]` holds the AI score. They reach `RulesEngine` and `LLMClassifier` by constructor, and the shipped
  values reproduce the calibrated behaviour.
* **`[sorting] keep_folders`** defaults to `true`. `sort --keep-folders` and `--keep-folders-off` override it for one run,
  and passing both is an error. With it off, a folder's documents are filed one by one, and the emptied folder is
  removed and recorded in the job so `rollback` can recreate it (§4).
* **`[sorting] ignore`** lists file and folder name globs the inbox scan skips without comment (Office lock files and OS
  clutter by default). A library's list replaces the default. **`[parsing] max_file_mb`** (default 50, above 0) is the size
  past which a file is not read and goes to review (§4).
* **`[ai]`** picks the provider (`ollama` or `openai`), model, host, timeout, the name of the environment variable that
  holds the OpenAI key (`api_key_env`; the key is never in the file), the AI score, and `max_document_chars` (how much of a
  document is sent; `0` means all of it). `core.ai.factory.build_provider` builds the provider from it. `sort` says when
  document text goes to OpenAI, and warns once if the length is unlimited. A second kind of classifier, a decision model
  that returns a bounded choice with a probability, is in the
  [feature backlog](../rfcs/RFC-005-decision-model-classifier.md) (see [ai-classifier-options.md](ai-classifier-options.md));
  a `command` provider is deferred behind a security decision.

## See also

- [ADR-001](../adr/ADR-001-configuration-layout.md) — why the configuration is being reorganised, and what was weighed.
- [mvp-roadmap.md](../requirements/mvp-roadmap.md) — what's actually implemented against this design vs. still stubbed.
- [data-model.md](data-model.md) — the ledger/`AuditEvent`/`Job`/`audit.log` schemas as actually implemented.
- [MVP build plan](../plan/archive/2026-10-mvp/plan.md) — a staged, from-scratch process for building to this design.
