# MVP build plan

A from-scratch, staged process for building microfiche to MVP, organized as six stages (plus the
interim stages 4.1 to 4.10, added after review) that
each ship a **testable version** — something you can actually run and demo, not just a set of
merged PRs. Every stage is internally sequenced Plan → Design → Build → Test → Deploy. This plan
covers the MVP only; work beyond it is in [feature-backlog.md](feature-backlog.md).

This is a different document from [mvp-roadmap.md](mvp-roadmap.md): that one is a bottom-up
status report against the *current* codebase (what's done/partial/stub, right now). This one
is the top-down process — the order you'd build microfiche in if you were starting today,
and a structure meant to be dropped directly into a GitHub Project. Read
[architecture.md](architecture.md) for the design detail behind any given stage's tasks.

## How to run this as a GitHub Project

- **Stage → Milestone.** Create one GitHub Milestone per stage (`v0.1.1 — Core Filing
  Skeleton`, `v0.1.2 — Configurable Rules Engine, Taxonomy & CLI`, …). Each milestone's
  description is that stage's "Testable version" line below.
- **Task → Issue.** Each bullet under Plan/Design/Build/Test/Deploy becomes one issue, titled
  with its one-sentence objective verbatim, assigned to its stage's milestone.
- **Phase → Label.** Apply one of `phase:plan`, `phase:design`, `phase:build`, `phase:test`,
  `phase:deploy` to every issue. Add `stage:1` … `stage:6` labels too if you want them
  independent of milestone (useful for filtering across a re-ordered board).
- **Project fields.** Add a single-select `Phase` field mirroring the labels above so the
  board can be grouped or filtered by phase within a milestone. A Table view grouped by
  Milestone, sorted by Phase, reproduces this document exactly.
- **Versioning.** The whole MVP is the `0.1.x` line, and the repo already has a `v0.1.0` tag as its
  baseline. Each stage's Deploy step tags the next patch version: Stage 1 is `v0.1.1`, Stage 2 `v0.1.2`,
  Stage 3 `v0.1.3`, Stage 4 `v0.1.4`, Stage 5 `v0.1.5` and Stage 6 `v0.1.6`, the MVP release. An interim stage
  numbered with a decimal (Stages 4.1 to 4.10) is an update to the stage before it and gets no tag of its own;
  its milestone is named for the stage, not for a version. Tags keep the `v` prefix, as `v0.1.0` does. There is no
  Stage 4.5, 4.7 or 4.9: they were moved to the [feature backlog](feature-backlog.md) while under review (the
  [decision-model classifier](feature-backlog.md#decision-model-classifier), [depth 3](feature-backlog.md#subcategories-depth-3)
  and the [filing target mode](feature-backlog.md#filing-target-mode-file_at)), and the numbers are not reused.
- **Definition of done per stage:** every issue in the milestone is closed *and* the stage's
  "Testable version" statement is true when you check it out and run it.

---

## Stage 1 — Core Filing Skeleton

**Milestone:** `v0.1.1 — Core Filing Skeleton`
**Testable version:** A Python pipeline that scans a folder, extracts text from PDF/DOCX/TXT/
Markdown, classifies each file against a small hardcoded category list by filename/keyword
matching, and moves it into a matching output folder — verified entirely by pytest against a
fixture folder. No CLI, no config files, no AI, no rollback.

**Plan**
- Define the MVP's minimal domain vocabulary (`Document`, `Category`, `ClassificationResult`) before writing any pipeline logic.
- Write the stage's exit criteria as a single sentence: given a fixture folder of N files, running the pipeline files each one into its correct hardcoded category and the test suite passes.

**Design**
- Design the `Document` model: file path, file name, extension, extracted text content.
- Design the `ClassificationResult` model: category name, confidence score, matching reason.
- Design the folder-scanning contract: a function that lists processable files in a directory and skips unsupported extensions.

**Build**
- Implement a folder scanner that lists supported files (PDF/DOCX/TXT/Markdown) in a source directory.
- Implement one parser per supported format that extracts plain text from a file.
- Implement a hardcoded keyword-matching classifier that maps extracted text to one of a fixed set of categories.
- Implement a filer that moves a classified file into `<output>/<category>/<filename>`.
- Implement one pipeline function that chains scan → parse → classify → file.

**Test**
- Write a unit test per parser against one sample file of that format.
- Write a unit test for the keyword classifier covering an obvious match, an ambiguous match, and a no-match case.
- Write an end-to-end test that runs the full pipeline against a fixture folder and asserts every file lands in its expected category.

**Deploy**
- Set up ruff, mypy, pytest, and pre-commit so the skeleton is enforced by CI from the first commit.
- Merge to `main` and tag `v0.1.1`; this stage ships to the team, not to users.

---

## Stage 2 — Configurable Rules Engine, Taxonomy Discovery & CLI

**Milestone:** `v0.1.2 — Configurable Rules Engine, Taxonomy & CLI`
**Testable version:** A `microfiche sort --library <path>` command that discovers a library's
existing group/category folder structure, classifies documents in a `_sorting/` inbox against
that taxonomy using TOML-configured rules, and files them — runnable and demoable by a human.

**Plan**
- Define the two-stage (group, then category) classification contract that replaces Stage 1's flat hardcoded classifier.
- Define the config file (`[category_hints.categories]`, `[filing_rules]`, `[naming_rules]`, `[exclusions]`) and what each one governs.

**Design**
- Design the `Taxonomy` model representing the library's discovered `{group: [category, ...]}` structure.
- Design the rules-engine interface: filename-glob rules checked before keyword-hint rules, scoped to a resolved group's existing categories.
- Design the CLI's command surface and argument conventions (`--library`, `--keep-folders`) before writing any Typer code.

**Build**
- Implement taxonomy discovery (`Library.taxonomy()`) to walk a library's folders, excluding configured exclusions, into a group → category map.
- Implement group resolution: filename/content keyword match, with fuzzy matching for near-misses.
- Implement category resolution: filename-glob rules, then keyword hints, scoped to the resolved group.
- Implement per-library TOML config loading and validation (`microfiche-config.toml`, one table per concern).
- Implement the `sort` command in a Typer CLI, wiring config loading → taxonomy discovery → classification → filing.
- Implement Rich-rendered console output summarizing filed vs. needs-review counts.

**Test**
- Write a taxonomy-discovery test against a fixture library with a nested group/category structure and an excluded folder.
- Write group-resolution tests covering an exact match, a fuzzy near-miss, and a no-match case.
- Write a category-resolution test confirming filename-rule precedence over keyword-hint matching.
- Write a CLI smoke test asserting `microfiche sort --library <fixture>` exits 0 and produces the expected filed layout.

**Deploy**
- Publish the `microfiche` console-script entry point so `uv run microfiche sort` works from a clean checkout.
- Tag `v0.1.2` as the first internally demoable release.

---

## Stage 3 — Safety Net: Audit Trail & Rollback

**Milestone:** `v0.1.3 — Audit Trail & Rollback`
**Testable version:** Every `sort` run writes a human-readable audit log and a structured
rollback job file, and `microfiche rollback --job-id <id>` actually restores the pre-sort
state — verified by a round-trip integration test.

**Plan**
- Define the audit/rollback data contract: what one audit event records, and what one job groups together.
- Decide the on-disk layout for persisted state (`.microfiche/audit.log`, `.microfiche/rollback/job_<id>.json`) before implementing either writer.

**Design**
- Design the `AuditEvent` and `Job` models and their JSON serialization format.
- Design how the filer emits an audit event per move without coupling it to how that event gets persisted.

**Build**
- Implement the `AuditEvent` and `Job` models.
- Implement a `.microfiche/audit.log` writer that appends one line per audit event.
- Implement save/load functions that persist and reload a job as `.microfiche/rollback/job_<id>.json`.
- Wire `sort` to build and persist a job from every run's filing events.
- Implement rollback logic that replays a job's moves in reverse and restores original file locations.
- Implement the `audit` and `rollback` CLI commands against this persisted state.

**Test**
- Write a unit test for the audit log writer's line format.
- Write a unit test for job save/load round-tripping through JSON.
- Write an integration test: sort a fixture inbox → assert the audit log and job file exist → roll back → assert the library matches its pre-sort state exactly.

**Deploy**
- Add the round-trip test to CI as a required check before merge.
- Tag `v0.1.3` — the first version whose core safety promise ("nothing is ever lost") is actually true.

---

## Stage 4 — AI Fallback for Low-Confidence Classification

**Milestone:** `v0.1.4 — AI Fallback`
**Testable version:** `microfiche sort --use-ai` correctly classifies documents the rules
engine can't resolve confidently, by falling back to a local Ollama model, without changing
behavior for anything the rules engine already handles.

**Plan**
- Define the confidence threshold and escalation contract: precisely what "the rules engine can't resolve" means, and what the AI classifier is asked to return.
- Decide the provider abstraction so Ollama and OpenAI are interchangeable behind one interface.

**Design**
- Design the LLM-classifier interface and its provider abstraction.
- Design the prompts that ask a model to pick a group/category (or "none") from the library's existing taxonomy.

**Build**
- Implement the provider-agnostic LLM classifier wrapping group and category resolution prompts.
- Implement the Ollama provider against a local Ollama server.
- Implement the OpenAI provider as a second, equally-supported option.
- Wire the classifier to fall back to the AI path only when rules-based confidence is below threshold.
- Add a `--ai-provider ollama|openai` CLI option (defaulting to Ollama) to `sort` and `reclassify`. *(Closed by Stage 4.1: `sort --use-ai` builds its provider from an `[ai]` config section, so `OpenAIProvider` is reachable, instead of through a CLI option.)*

**Test**
- Write unit tests for the AI-fallback trigger condition (below-threshold vs. above-threshold rules results).
- Write unit tests for both providers against a mocked model response.
- Write an integration test confirming a document only the AI path can classify gets filed correctly end-to-end with `--use-ai`.

**Deploy**
- Document the local Ollama setup steps needed to exercise `--use-ai` in a contributor's dev environment.
- Tag `v0.1.4`.

---

## Stage 4.1 — Configuration Consolidation

**Milestone:** `Stage 4.1 — Configuration Consolidation` (an untagged update to `v0.1.4`; see [Versioning](#how-to-run-this-as-a-github-project))
**Testable version:** Every tunable value (confidence scores, fuzzy thresholds, `keep_folders`, the AI
provider) is read from configuration rather than hard-coded; defaults come from one packaged file; and a
library's category hints and filing rules live in `.microfiche/microfiche-library.json`, separate from the
behaviour settings in `microfiche-config.toml`. `microfiche sort` produces the same results as v0.1.4 on the
calibration corpus, except that whole folders are now filed intact by default.

Why before Stage 5: `review` adds settings of its own (a review section), and
should be built against the layered loader rather than adding to the hard-coded constants. Stages 4.2 to 4.4
also add settings, so they build on it too. The reasoning is in [config-review.md](config-review.md); the
target design is [architecture.md §10](architecture.md#10-configuration-layout).

**Plan**
- Decide which constants become settings and which stay fixed (file names, chunk sizes, display styles), per [config-review.md](config-review.md) point 1.
- Define the split between settings (`microfiche-config.toml`) and library data (`microfiche-library.json`), where the folders stay the authority on what exists and the file describes them (it is created and kept in step by Stage 4.10), and what is dropped: `library_templates`, `levels`, `file_target_level`. `depth` stays, as the one structural setting.
- Decide whether `--use-ai` stays a per-run switch or becomes `[ai] enabled`, and whether the `init` command and a template catalog are in the MVP (the default is no).
- Decide whether to keep `thefuzz` or depend on `rapidfuzz` directly. [fuzzy-matching-options.md](fuzzy-matching-options.md) records the comparison: `thefuzz` is a wrapper over RapidFuzz, scores and speed are the same for `partial_ratio`, and the calibration report is identical. The recommendation is to switch, as the last Build step, so `fuzzy_group_threshold` is settled before it ships.
- Write the stage's exit criteria as a single sentence: with the shipped defaults the calibration report is unchanged, and each new setting changes the behaviour it names.

**Design**
- Design the packaged defaults file and the load order: defaults, then the library's file, deep-merged (tables merge, lists replace), then validated.
- Design the `[classification]` additions (signal strengths, fuzzy thresholds) with range validation, and how they reach `RulesEngine` and `LLMClassifier` by constructor.
- Design `[sorting] keep_folders` (default on) and the CLI precedence: `--keep-folders` or `--keep-folders-off` (passing both is an error), then library config, then packaged default. What the setting does when off is Stage 4.2.
- Design `[ai]` (provider, model, host, timeout, score, `max_document_chars`, `api_key_env`) and the `build_provider` factory, leaving room for a second kind of AI classifier (a decision model, now in the [backlog](feature-backlog.md#decision-model-classifier)) alongside the chat model. `provider = "openai"` sends document text off the machine, so it must be chosen explicitly and the run must say so.
- Design `[ai] max_document_chars` (how much of a document is sent to the AI): at least 0, where `0` means no limit. An unlimited run prints one warning before any document is classified, never one per document, about token usage, processing time and the model's context window (a longer document may fail or be cut off). The CLI prints it and `core` stays quiet; Stage 4.4 also logs it at WARNING. With `provider = "openai"` the warning also says the cost is real money.
- Design the `microfiche-library.json` node schema as a recursive tree of folders, `{name, hints, rules, children}`, whose top level is the groups, so it is not tied to two levels and can be created from the folders. A `name` of `*` means any folder at that level, which keeps today's behaviour (hints global by category name) without repeating them in every group. The hints and rules for a group and category are the concrete nodes' first, then the `*` nodes'. The tree may not be deeper than `[library_structure] depth`. The file is reviewed and confirmed before it is built on.
- Design the fuzzy-library switch: pass `score_cutoff=fuzzy_group_threshold` to the group match, decide whether scores stay rounded integers or become floats (84.6 used to round up to 85 and pass), and give `tag_mapper` an explicit `processor` because RapidFuzz's `extractOne` does not lowercase or strip punctuation by default.

**Build**
- Add `core/defaults/microfiche-config.toml`, load it with `importlib.resources`, and remove the default values from the pydantic models.
- Move the signal strengths and fuzzy thresholds into `[classification]` and thread them through the constructors. `max_document_chars` is read only by the AI, so it goes in `[ai]` instead.
- Add `[sorting] keep_folders = true` and keep `--keep-folders` as a boolean switch, adding a `--keep-folders-off` switch beside it (no `--no-keep-folders`): `--keep-folders` forces folders on for that run, `--keep-folders-off` forces them off, passing both exits with an error, and passing neither defers to the setting; make `propose-categories` use the setting too.
- Add `AIConfig` and `build_provider`, so `OllamaProvider` and `OpenAIProvider` are both reachable from `sort --use-ai`; this closes the Stage 4 `--ai-provider` gap. Read the OpenAI key from the environment variable named by `api_key_env`, never from the file.
- Add `[ai] max_document_chars` (default 4000) and make `0` mean unlimited: send the whole document, and print the one-per-run warning designed above.
- Add the `microfiche-library.json` model, loader and generated JSON Schema, and move `category_hints` and `filing_rules` into it as `*` nodes. A missing file means no hints; the sync that creates it is Stage 4.10.
- Delete `library_templates`, `levels` and `file_target_level` from the config; validate `depth` against the supported range (2 until Stage 4.6 widened it to 1–2; [depth 3](feature-backlog.md#subcategories-depth-3) is in the backlog) with a clear message.
- Fix the stale `.yaml` mentions in `library/templates.py` and `rules/metadata_rules.py`, and update the shipped template folder (`microfiche/`) to match.
- Replace `thefuzz` with `rapidfuzz` in `rules/group_rules.py` and `obsidian/tag_mapper.py`, as its own commit after the library file work: declare `rapidfuzz` in `core`'s `pyproject.toml`, remove `thefuzz` and its mypy override, and pass `score_cutoff` and `processor` as designed.

**Test**
- Write a test that the shipped template and the packaged defaults agree (the `[obsidian] enabled` mismatch was the known case; the section has since been removed with the Obsidian integration).
- Write config tests for the layered load: a missing file, a partial file, a list that replaces, and a range violation on each new score.
- Write a test that each new setting changes the behaviour it names, using fake resolvers rather than the real rules.
- Write a CLI test for `keep_folders` precedence: either flag, when passed, over config over default, and passing both is an error.
- Write tests that `build_provider` returns the provider the config names, and fails with a clear message when the OpenAI key variable is unset.
- Write tests for `[ai] max_document_chars`: a positive value cuts the text sent, `0` sends the whole document (`content[:0]` would send nothing, so this guards against that slip), a negative value is rejected, and the CLI prints the unlimited warning once per run, not per document, and not when the limit is positive.
- Re-run `tests/calibration/report.py` and confirm the default threshold's findings still hold; update [calibration.md](calibration.md) if not. After the fuzzy-library switch the report must be identical.
- Write a `tag_mapper` test that `Python` still maps onto `python` after the switch, and a group-match boundary test that a score exactly at `fuzzy_group_threshold` is accepted and one point below is not.

**Deploy**
- Update `README.md`, `docs/how-to-use.md` and `docs/cli-reference.md` (`make docs-cli`) for the new settings and the changed `--keep-folders` default, in both the Bash and PowerShell tabs.
- Update `architecture.md` (§3, §4 and §10), `mvp-roadmap.md` and `module-diagram.md`, and add "library template" and "hints" to [CONTEXT.md](../../CONTEXT.md).
- Reword the places that name `thefuzz`: `AGENTS.md`, `calibration.md` and the `ClassificationConfig` docstring in `core/config.py`.
- Merge to `main` without a new tag: this stage is an update on top of `v0.1.4`, and its changes ship with the next tag, `v0.1.5`.

**Deferred:** an `init` command and a template catalog; a `command` AI provider (needs a decision on running
commands from a config inside a shared library); per-group hint overrides.

**Since removed:** the `obsidian/tag_mapper.py` part of the `rapidfuzz` switch, and its test, were built and later
removed with the Obsidian integration. See [feature-backlog.md](feature-backlog.md#obsidian-integration).

---

## Stage 4.2 — Folder Handling & Name Collisions

**Milestone:** `Stage 4.2 — Folder Handling & Name Collisions` (an untagged update to `v0.1.4`)
**Testable version:** A name already taken at the destination no longer crashes `sort`: that unit stays in the
inbox for review, with the reason, and everything else is filed. With `keep_folders` on, the mock library's
inbox folder files whole under its dominant category; with it off, the files inside are filed one by one and
the emptied folder is removed, recorded so `rollback` recreates it. An inbox file whose content is identical to a
file already in the library (or to another inbox file filed in the same run) is classified as usual but not
filed: it stays in the inbox and the summary lists it under Duplicates, naming the existing copy and, when the
existing copy is somewhere else, where this one would have been filed.

Why now: today `file_batch` raises `FileExistsError` part-way through a batch and `commands.sort` does not
catch it, so a collision gives a traceback and a half-finished job. `keep_folders = false` also has to start
descending into folders, which makes same-name collisions between sub-folders likely. A name check says nothing
about content, so the commonest collision, dropping a file that is already filed, is better recognised as a
duplicate than reported as a name clash. The reasoning is in [operations-review.md](operations-review.md).

**Plan**
- Decide what `keep_folders = false` means. Today it ignores inbox folders (the scanner only descends into them when it is on), so their contents are never filed. The intended meaning is: descend, and file each document on its own. That changes today's behaviour and `architecture.md` §4.
- Decide the collision policy: a unit whose destination is taken stays in the inbox for review, with the reason. Nothing is renamed, suffixed or overwritten, matching what `reclassify` already does with its `conflict` action.
- Decide what a duplicate is: an inbox file whose bytes (SHA-256) match a file already in the library, in any group or category, or a file already being filed in this run. The name does not matter; the same name with different content is a collision, not a duplicate.
- Decide the principle: the check looks at **new files only**, comparing each inbox file against the library. It never examines or reports duplicates already inside the library, because a project often holds the same document in more than one place (reference documents, for example). For the same reason it is always on and has no setting: it has no effect on what is already filed.
- Decide the policy: a duplicate is classified like any other file, then held in the inbox with the reason. Nothing is renamed, moved or deleted; the user decides what to do with it. This is the collision policy applied to content.
- Decide the scope: file units only. With `keep_folders` off every file inside an inbox folder is its own unit, so each is checked; with it on, a folder unit is not checked (a duplicate bundle files as before). Checking a folder is deferred.

**Design**
- Design one destination check shared by `sort` and `reclassify`, applied after the naming rules, covering both a file that already exists and two units in the same run headed for the same destination (the first files, the second goes to review). `file_batch`'s `FileExistsError` stays as the last line of defence against a race.
- Design the order of checks for each inbox unit: classify, then the duplicate check, then the destination check. The unit is classified first so the duplicate message can say where it would have been filed. The duplicate check comes before the destination check so that a file already filed under the same name is reported as a duplicate, which is more informative, and so a held duplicate never claims a destination that a different file needs.
- Design `DuplicateIndex(library)` (in `core/duplicates.py`) as a lazy index of the library: nothing is read until the first inbox file needs checking. `find(path)` returns the existing copy or `None`, and `add(destination)` registers a unit that is about to be filed, so a second identical inbox file is caught as a duplicate of the first. It is cheap by checking size first:
  - Walk the library once and `stat` every file, pruning the inbox, `.microfiche/` and excluded folders so `.git` and `.obsidian` are never entered. Group the paths by size.
  - Hash an inbox file only if a library file has the same size, and hash a library file only if it is the same size as an inbox file being checked. Most runs hash a handful of files out of thousands, and a cloud-only OneDrive placeholder is never downloaded unless it is a real candidate.
  - Check the inbox against the library in one direction only; the library is never compared with itself.
- Design the reason for a duplicate from the unit's classification and the existing copy's place:
  - the copy is at the destination: "identical to `<path>`, already filed where this would go";
  - the copy is in the destination category folder, under another name or in a sub-folder: "identical to `<path>`, in the folder this would be filed to";
  - the copy is in a different category or group: "identical to `<path>`; this would be filed in `<group>/<category>`";
  - the classification is not confident but names a group and category: "identical to `<path>`; the classifier suggests `<group>/<category>` but is not confident";
  - the classification is unresolved: "identical to `<path>`; could not be classified";
  - the copy is another inbox file being filed in this run: "identical to `<name>`, which is being filed this run to `<group>/<category>`".
- Design `SortReport.duplicates`: a list of a small record holding the unit, its full `ClassificationResult`, the existing path and the reason. A duplicate is listed here only, not also in `needs_review`, because it is not a classification question and the user should not be asked to pick a category for a file they will probably discard. Name collisions stay in `needs_review`.
- Design `Library.filed_under(path, group, category)`, true when the path is in that category folder or below it. `reclassify` already applies this rule inline for its `keep` action, so move it here and have both use it.
- Design `reclassify` as unaffected by duplicates: it moves documents within the library and never imports from the inbox.
- Design the interaction with emptied folders: a duplicate left in an inbox folder stops that folder being removed, and the report says why.
- Design how an inbox folder is handled when `keep_folders` is off:
  - Its documents, including those in nested sub-folders, become single-document units.
  - Two files with the same name from different sub-folders are a collision, handled as above.
  - Once every supported file has moved, the emptied folder is removed only if it is truly empty. A folder that still holds an unsupported, unreadable or review-bound file stays, and the report says why.
  - The removal is recorded in the job (a new audit event kind, or a field on the job; see [data-model.md](data-model.md)), so `rollback` recreates the folder. This must be reconciled with the "nothing is ever deleted" wording in the README and `AGENTS.md`: no file is deleted, only an empty folder.

**Build**
- Add the shared destination check, and route a collision to `SortReport.needs_review` with a reason such as "a file named X already exists in Project Phoenix/02 Architecture".
- Make `scan_sorting_inbox` descend into inbox folders when `keep_folders` is off, returning one single-document unit per supported file (with the folder it came from recorded on the unit, so the emptied folder can be found).
- Add empty-folder handling to `file_batch` (or a step in `run_sort` after it): remove a folder left empty by the `no` option, record the removal in the job, and make `rollback_job` recreate it; leave a non-empty folder and report it.
- Add `core/duplicates.py` with `DuplicateIndex`, and `Library.filed_under` (used by `reclassify` as well).
- Call the duplicate check from `run_sort` between classification and the destination check, and fill `SortReport.duplicates`.
- Show collision and kept-folder reasons in the `sort` summary, and list duplicates in their own Duplicates section with the filed and needs-review counts.

**Test**
- Write collision tests: an existing file at the destination sends only that unit to review with the reason, the rest are filed, nothing is overwritten and there is no traceback; two units headed for the same destination file one and review the other.
- Add a folder to `tests/mock_library/_sorting/` that shows both outcomes. Two files can't do it: two documents that file differently tie, and a tie goes to review rather than to one location. Use three files, with two voting for one category and one for another. For example `phoenix-weekly-pack/` holding two Project Phoenix architecture documents (`architecture-decision-log.md`, `component-diagram-notes.md`) and one Project Phoenix research document (`research-summary.md`). Keep each document's wording to one category's name so the result doesn't depend on which name is matched first.
- Write end-to-end tests against that folder:
  - `keep_folders` on: the whole folder files into `Project Phoenix/02 Architecture/`, one folder record in the ledger, and `_sorting/` no longer holds it.
  - `keep_folders` off: the two architecture documents file into `02 Architecture/` and the research document into `03 Research/`, as three separate records in one job.
  - `keep_folders` off, emptied folder: the folder is gone after the sort, and `rollback` restores it and all three files exactly.
  - `keep_folders` off, folder not emptied (add an unsupported file such as a `.png`, or a sub-folder name clash): the folder stays and the report names why.
- Update the existing tests that copy `tests/mock_library` (`tests/cli/test_app.py`, `tests/core/test_organizer.py`, `tests/core/test_reclassify.py`) for the new folder, and check any that assert counts of filed or review items.
- Write duplicate tests, building the duplicates inside each test rather than in `tests/mock_library` so the shared fixture does not change again:
  - a copy already at the destination is held with "already filed where this would go";
  - a copy under another name in the destination folder, and one in a sub-folder of it, are held with the "in the folder this would be filed to" reason;
  - a copy in a different category, and one in a different group, are held and the reason names both places;
  - a duplicate that classifies with low confidence, and one that is unresolved, are each listed once under duplicates and not in `needs_review`;
  - two identical inbox files file the first and hold the second, with the "being filed this run" reason;
  - a held duplicate does not claim its destination: a different-content file that would take the same destination name (two inbox sub-folders with `keep_folders` off, or a naming rule) still files;
  - the same name with different content is a collision in `needs_review`, not a duplicate; the same size with different content is neither;
  - identical files that are both already in the library are never reported;
  - with `keep_folders` off a duplicate inside an inbox folder is held and the folder stays, with the reason; with it on, a folder unit is not checked;
  - the index hashes only same-size candidates (count the hash calls through a fake), prunes excluded folders, and reads nothing when the inbox is empty;
  - `Library.filed_under` accepts the category folder and its sub-folders and rejects a sibling category, and `reclassify`'s `keep` still behaves as before.

**Deploy**
- Update `docs/how-to-use.md` and the README (collisions, duplicates and how to resolve one, and what `keep_folders = false` does), `architecture.md` §4 and the "nothing is ever deleted" wording.
- Add "duplicate" to [CONTEXT.md](../../CONTEXT.md), update `mvp-roadmap.md` (move duplicate detection out of "Future work and deferred beyond MVP"), and update the Decisions in [operations-review.md](operations-review.md), which still lists recognising an exact duplicate as deferred.
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**Deferred:** renaming on collision (a suffix setting); moving duplicates to a `_sorting/duplicates/` folder to
leave the inbox tidier (a `[sorting] duplicates = "leave" | "quarantine"` setting, which needs a scanner skip rule and
its own collision handling); duplicate checking of folder units; a persistent hash cache keyed by path, size and
modification time; a hash of the parsed text, to catch a re-saved copy whose bytes differ.

---

## Stage 4.3 — Safe Runs & Input Hardening

**Milestone:** `Stage 4.3 — Safe Runs & Input Hardening` (an untagged update to `v0.1.4`)
**Testable version:** `microfiche sort --dry-run` shows what would be filed and what would go to review without
moving or recording anything; a second `sort` started while one is running refuses to start; and no single bad
input (a locked file, a symlink, an oversize file, Ollama not running) aborts a run: the unit goes to review
with the reason, or the AI is skipped with one warning.

Why now: `sort` moves files as soon as it classifies them, one run can interleave with another, and a Windows
file held open by Obsidian or Word will fail a move. The reasoning is in [operations-review.md](operations-review.md).

**Plan**
- Define the failure policy: a failure that belongs to one unit sends that unit to review with a reason; a failure of the run itself (a lock held) exits with code 1 and a message.
- Decide the symlink policy: links and junctions in the inbox are skipped and listed, never followed.

**Design**
- Design `--dry-run`: classification runs as usual, but nothing is moved and no job, ledger record or audit line is written, and the library file is not synced (Stage 4.10); the output is labelled as a preview.
- Design the run lock: `.microfiche/lock` holding the process id and start time, stale-lock detection, released on exit, and taken by `sort`, `reclassify --apply`, `rollback` and `config --sync` (Stage 4.10); read-only commands don't take it.
- Design per-unit failure isolation in `run_sort` and `file_batch`: a failed move is not recorded as a move, the job keeps the successful ones, and the unit is reported for review.
- Design moves as plain renames, with no copy fallback. `shutil.move` falls back to copy-then-delete when a rename fails; on Windows, with Word holding the file open, the copy succeeds and the delete fails, leaving a stray copy that nothing records. A rename either happens or changes nothing, which is what makes per-unit isolation safe. `file_batch` returns a `FilingResult` (the job and the failed units), and a failure is reported in plain language ("it is open in another program; close it and sort again").
- Design link detection around the Windows reparse tag, not the reparse-point attribute: OneDrive's on-demand placeholders are reparse points too, and only symlinks and junctions (mount points) count as links.
- Design the lock to be taken at the CLI level, so `reclassify --apply` holds it from planning to filing. A process is checked with the operating system's process API on Windows, never `os.kill(pid, 0)`, which sends a Ctrl-C there. A lock file that cannot be read counts as held.
- Design the AI-unavailable path: the first connection failure or timeout logs one warning and the rest of the run uses the rules only.
- Design the new settings and add them to the packaged defaults: `[sorting] ignore` (patterns such as `~$*`, `.DS_Store`, `Thumbs.db`, `*.tmp`) and `[parsing] max_file_mb` (an oversize file goes to review rather than being parsed).

**Build**
- Add `--dry-run` to `sort`.
- Add the run lock and take it in the commands above.
- Catch per-unit `OSError` during filing, and AI provider errors during classification, as designed.
- Make the scanner skip symlinks, junctions and files matching `[sorting] ignore`, and report the skipped links.
- Make the parsers check `max_file_mb` before reading.

**Test**
- Write a `--dry-run` test: the output lists the planned moves, and the library, ledger, audit log and job folder are byte-identical afterwards.
- Write lock tests: a second run refuses while the first holds the lock, and a stale lock (dead process id) is cleared.
- Write failure tests with fake providers and a locked file: the run finishes, the unit is in review with the reason, and the job lists only successful moves; with a fake provider that raises, the rules-only result is used and one warning is shown.
- Write scanner tests for a symlink, an ignored name and an oversize file.

**Deploy**
- Update `docs/how-to-use.md` (preview before you sort, what a lock message means, the new settings), the README and `docs/cli-reference.md` (`make docs-cli`).
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**Deferred:** a lock timeout or `--force` override; nested-library detection.

---

## Stage 4.4 — Logging & Diagnostics

**Milestone:** `Stage 4.4 — Logging & Diagnostics` (an untagged update to `v0.1.4`)
**Testable version:** `core` logs decisions through the standard `logging` module without installing any
handlers; the CLI adds `-v/--verbose` and `-q/--quiet`, writes a rotating `.microfiche/microfiche.log` (only
from a command that holds the run lock, so a preview or a read-only command writes none), and shows progress on
long runs; `audit.log` is unchanged.

Why now: there is no logging today. `core/utils/logging.py::get_logger` is unused and writes
`organization.log` outside the `.microfiche/` convention, so when a unit lands in review or an AI call fails
there is nothing to read afterwards. Stages 5 and 6 are easier to build and debug with it in place.

**Plan**
- Separate the two kinds of record: `audit.log` and the ledger are product data that `rollback` reads and must stay stable; the diagnostic log is for people and can change.
- Decide what is logged: scan results, each classification with its reasons, AI call outcome and timing, skipped items and why, filing and rollback steps. Never document contents or API keys.

**Design**
- Design logger names as plain `logging.getLogger(__name__)` (`core.<module>`, `cli.<module>`), not a `microfiche.` prefix: a helper that adds the prefix would only move one line into every module.
  - Only the CLI configures handlers, and it attaches them to the `core` and `cli` loggers, not the root. Third-party loggers (the AI SDKs' HTTP clients) then stay out of the log, and `propagate` stays on so `caplog` works.
  - `core/__init__.py` adds a `NullHandler` to the `core` logger, so `core` stays quiet when used as a library.
- Design the levels: the logger sits at DEBUG and each handler filters. A handler's level is a threshold, so WARNING shows WARNING, ERROR and CRITICAL.
  - The console (stderr) shows WARNING and above by default, INFO with `-v` and ERROR with `-q`. The file shows `[logging] level` (INFO by default) and DEBUG with `-v`.
  - `-v` and `-q` are per-command options, defined once as shared constants like `--library`, on every command that opens a library. If both are passed `-q` wins, with no usage error, and `--help` says so.
- Design a `[logging]` section, with defaults only in the packaged file and the template in `microfiche/` kept in step. The console level is set by the flags alone.
  - `level`: the file's level when `-v` is not given; a level name checked with `logging.getLevelNamesMapping()`; default `"INFO"`.
  - `file`: a plain file name kept inside `.microfiche/`, validated like `library_inbox` so it cannot point outside the state folder; default `"microfiche.log"`.
  - `max_bytes`: greater than 0; default 1048576. `backup_count`: 0 or more; default 3.
- Design when the file handler attaches: only in commands that hold the run lock (`sort` without `--dry-run`, `reclassify --apply`, `rollback`). A dry run then still writes no state folder (Stage 4.3), and only the lock holder rotates the file, which fails on Windows if two processes hold it. Other commands log to the console only.
  - Setup goes through one helper that every command passes through (`rollback` and `audit` open the library without `_open_library` today).
  - It is idempotent: it removes and closes the handlers it added before adding them again, so repeated invocations in one process do not duplicate lines or leave the file open.
- Design how a condition the user is already told about is shown once.
  - The OpenAI notice and the unlimited-`max_document_chars` notice stay direct prints, so they survive `-q`. They are also logged at WARNING, to the file only, through a filter on the console handler.
  - `core` logs the AI-unavailable condition at WARNING, once per run, with the flag held on the run state, not in a module global. The report keeps `ai_unavailable` as data, and the CLI no longer prints a separate line for it.
- Design progress output: shown on stderr, only when the console is a terminal, the run has many units or the AI is in use, and `-q` was not given, so piped output stays clean.
  - It shares one stderr `Console` with the log handler, so log lines print above the bar.
  - "Many units" is a constant in the code, not a setting.
  - `core` cannot import Rich, so it reports progress through an optional callback parameter on `run_sort` and `run_reclassify`.

**Build**
- Replace `core/utils/logging.py::get_logger` with module loggers, and remove the unused `organization.log` writer.
- Add log calls at the decision points listed in the Plan.
- Add `-v` and `-q` to the CLI and a `RotatingFileHandler` for `.microfiche/microfiche.log`.
- Add a Rich progress display for `sort` and `reclassify`.

**Test**
- Write a test that importing and running `core` adds no handlers to the root logger.
- Write `caplog` tests that a classification, an AI failure and a skipped file each log at the intended level.
- Write a CLI test that `-v` and `-q` change what is shown, and that the log file is created under `.microfiche/` and holds no document text.
- Write a test that piped output carries no progress control codes.

**Deploy**
- Update `docs/how-to-use.md` with a troubleshooting section (where the log is, what `-v` and `-q` show, and that a `--dry-run` or other read-only command writes no log file), the README and `docs/cli-reference.md`.
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**Deferred:** structured (JSON) log output; log shipping.

---

## Stage 4.6 — Flat Libraries (Depth 1)

**Milestone:** `Stage 4.6 — Flat Libraries (Depth 1)` (an untagged update to `v0.1.4`)
**Testable version:** With `[library_structure] depth = 1`, `microfiche sort` classifies each document against
the library's group folders only and files it straight into one. The ledger, `rollback` and `reclassify` work on
a flat library as they do on a two-level one. The default stays 2.

Why before Stage 5: `review` would otherwise be built on the group-then-category shape and have to
be reworked. The vocabulary, the depth model and the dependencies between 4.6 to 4.8 are in
[library-depth.md](library-depth.md).

**Plan**
- Confirm the vocabulary: the word *group* is used at every depth, so a flat library has groups only; *category* appears at depth 2 and *subcategory* at depth 3. This keeps the names consistent from depth 1 upward.
- Decide the accepted range: `depth` is 1 or 2 after this stage (any other value is still rejected with a clear message).
- Decide that group-level hints and filing rules are needed. A flat library has only its folder names to match on, so a level-1 node in `microfiche-library.json` takes `hints` and `rules` like any other node.

**Design**
- Design how `Taxonomy` and `Library.taxonomy()` represent a library with no categories (empty category lists, or a depth-aware shape), reading only as deep as `depth`.
- Design a single-stage `Classifier` path: the overall confidence is the group's confidence, and the AI fallback is asked the group prompt only.
- Design filing-rule targets: a rule names the folder at the deepest level, so the `category` key becomes a `target` that means a group at depth 1.
- Design the ledger and audit change: `category` becomes optional, and [data-model.md](data-model.md) records it.
- Design the folder-unit vote and `reclassify`'s `keep` check for depth 1: the vote is on the group alone, and a document is already in place when it is under its group folder.

**Build**
- Make `depth` validate as 1 or 2, and make `Library.taxonomy()` and `target_dir` depth-aware.
- Add the single-stage path to `Classifier`, `RulesEngine` and `LLMClassifier`.
- Read hints and rules for level-1 nodes in the library file.
- Make `file_batch`, the ledger and `reclassify` accept a missing category.
- Update the `sort` and `reclassify` displays for a missing category.

**Test**
- Add a flat fixture library (`tests/mock_flat_library`) with a few group folders and an inbox.
- Write end-to-end tests on it: sort files into a group folder, `rollback` restores it, and `reclassify` reports `keep`, `move` and `review` correctly.
- Write unit tests for group-level hints and a filing rule whose target is a group, and for a folder unit voting on the group alone.
- Add a flat library to the calibration corpus and re-run `tests/calibration/report.py`; update [calibration.md](calibration.md) if the default threshold's findings change.

**Deploy**
- Update `README.md`, `docs/how-to-use.md` (a section on flat libraries, in both the Bash and PowerShell tabs) and `docs/cli-reference.md`.
- Update `architecture.md` §2 and §10, `data-model.md`, and `CONTEXT.md` (the library is one or two levels; a group is the top level at any depth).
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**As built:**
- `Taxonomy` gained `depth` (default 2) and `is_flat`, and keeps `groups` as a dict whose category lists are empty at depth 1. This is the "depth-aware shape": the empty list alone could not tell "no categories at this depth" from "a group with nowhere to file into".
- `ClassificationResult.category` is `None` in a flat library, which is not the same as a `CategoryMatch` with `name=None` (an unresolved category). `ClassificationResult.folders` returns the folder names to file under, and `reason` and `held()` say which stage carries the reason. `Library.target_dir`, `Library.filed_under` and `destination_for` take those folders, so nothing outside the classifier counts levels.
- The `category` key of a rule became `target` inside `RulesEngine`. The library file did not change: a rule is held by the entry it files into, so a group entry's rules file into the group at depth 1. No schema change, so `make library-schema` produced no diff.
- A flat library's group is matched by filename rule, then its name, then its hints (filename rule 0.95, an exact name 1.0, a hint 0.75). Hints of two different groups in one document are left for review, not resolved in favour of the first: with the group as the only stage there is nothing after it to correct a wrong guess. The two-level category matcher still takes the earlier category.
- `propose-categories` says a flat library has no categories and prints nothing; the reclassify table drops its category column.
- A library file written at depth 2 is refused at depth 1 (its entries below the top level are too deep) with a message saying to remove them or raise the depth; sync never prunes entries.
- The calibration corpus for depth 1 is a separate root, `tests/calibration/corpus_flat`. The AI arm and its saved answers cover the two-level corpus only and were not re-run for depth 1.
- Group names are the only signal in a flat library, so the substring gap (`Car` in `care` or `scarf`, recorded in [calibration.md](calibration.md)) bites more. It is a known follow-up, not part of this stage.

---

## Stage 4.8 — Non-Library Folders

**Milestone:** `Stage 4.8 — Non-Library Folders` (an untagged update to `v0.1.4`)
**Testable version:** A folder that isn't part of the taxonomy (a bundle filed whole by `keep_folders`, or a
folder the user made, such as `attachments/`) is never read as a group, category or subcategory, and
`reclassify` keeps a filed bundle together instead of splitting it.

Why: with `keep_folders` on, a folder such as `phoenix-weekly-pack/` is filed whole inside a category. The plan
has no task for what that folder is afterwards. Today the taxonomy walk stops at level 2, so it doesn't see
the bundle, but `reclassify` walks every file under the library and would classify the bundle's documents one
by one, splitting it. At depth 3 the bundle would also be read as a subcategory, and the same applies to any
folder a user keeps inside a category. The reasoning is in [library-depth.md](library-depth.md).

**Plan**
- Define a non-library folder: any folder inside the library that is not a group, category or subcategory.
- Decide the signals that identify one, and their order: the exclusion patterns that exist already, then a folder the ledger recorded as a filed folder unit, then a name that fails the level's name pattern (below).
- Decide what happens to the documents inside a non-library folder that isn't in the ledger (the user's own folder): by default `reclassify` leaves them where they are and says so.

**Design**
- Design an optional `name_pattern` per level in `microfiche-library.json`, a regular expression the whole folder name must match (for example `^\d{2} .+` for a library whose categories are numbered). With no pattern, any name is accepted, as today. A template copied at creation carries the pattern for its convention, which is how the template is referred to without making the template the taxonomy.
- Design pattern errors: an invalid regular expression is a `ConfigError` naming the file and the level.
- Design `Library.is_taxonomy_folder(path, level)` as the one place the three signals combine, used by the taxonomy walk, `reclassify`, `Library.files` and `propose-categories`.
- Design `reclassify` for a ledger-recorded folder unit: it is proposed as one unit (`move` whole, `keep`, `review` or `conflict`), never document by document.
- Design the report line for a skipped non-library folder, so the user sees what was left alone.

**Build**
- Add `name_pattern` to the library file's model and validate it.
- Add `Ledger.is_folder_unit(path)` and `Library.is_taxonomy_folder`, and use them in the callers above.
- Make `reclassify` unit-aware for filed folders and skip other non-library folders with a report line.
- Show the patterns in `microfiche config`.

**Test**
- Write a fixture with a category holding a filed bundle and a user's `attachments/` folder.
- Write tests: the taxonomy ignores both; a pattern accepts and rejects the right names; an invalid pattern is reported with its file and level; `reclassify` keeps the bundle whole and leaves `attachments/` alone with a report line; `rollback` of the folder unit still restores it.
- If [depth 3](feature-backlog.md#subcategories-depth-3) is ever built, add a depth-3 test that the bundle is not read as a subcategory.

**Deploy**
- Update `docs/how-to-use.md` (what microfiche leaves alone, and how to add a name pattern), the README, `architecture.md` §1 and §4, and `CONTEXT.md` (*non-library folder*).
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**Revised before building (2026-10-12).** The stage was reduced to what the principle needs: *a folder within the
depth is a filing target unless a rule excludes it; a folder beyond the depth is content*. Skipping a folder "tagged a
certain way" (say `yyyymmdd_*`) is what `[exclusions]` already does, so the `name_pattern` allow-list, its schema change
and `Library.is_taxonomy_folder` were dropped, and with them the two follow-up decisions (a result object for skipped
folders, and the library file's coupling to the taxonomy walk). Folders the user made are no longer skipped with a report
line: `reclassify` reads their files as it always did, and the user keeps a folder out by excluding it.

**As built:**
- `Ledger.folder_units()` returns the library-relative paths of the folders currently filed whole, from the one replay of the ledger.
- `run_reclassify` classifies each such folder as one unit (the dominant pair across its documents, as `sort` does) and proposes it whole: `keep`, `move`, `review` (a tied vote) or `conflict`. A scope that covers only part of a bundle still proposes the whole bundle. A bundle whose folder is gone is ignored.
- `Library.structure()` skips the folders the ledger records as filed whole. This matters as soon as the depth is raised: a bundle filed at `Group/pack` at depth 1 would otherwise become a category at depth 2 (and a subcategory at depth 3). `sort` only appends to the ledger, so an unreadable ledger is a warning there and the folders are simply not recognised.
- `reclassify` reads the ledger, so a corrupt one now stops it with a message (`LedgerCorruptError`).
- `core.reclassify.items_below_depth` counts the ledger's current items filed deeper than the depth allows and still on disk (a bundle counts once), and `reclassify` prints a note when there are any, after any moves. Nothing is moved.
- The opt-in flatten that would bring those items up is recorded in [feature-backlog.md](feature-backlog.md#opt-in-flatten-when-the-depth-is-reduced).

**Deferred:** detecting folders moved by hand that the ledger doesn't know about. A bundle moved by hand drops out of the unit set and is split by `reclassify`; the ledger's content hash could identify it at its new place, but the hash changes if its documents were edited. Pinned by a test.

---

## Stage 4.10 — Library File Sync

**Milestone:** `Stage 4.10 — Library File Sync` (an untagged update to `v0.1.4`)
**Testable version:** A library with no `microfiche-library.json` gets one on its first real `sort`, and from
`microfiche config --sync`, listing its folders to the configured depth with no hints. A folder the user adds later
is found on the next run, added to the file and reported once. A folder that disappears is reported on every run
and never removed from the file. Hints, rules and order the user wrote are never changed, and `sort --dry-run`
writes nothing.

Why a stage of its own: Stage 4.1 moves hints into a library file that the user writes by hand. This stage makes
the file follow the folders, so a new library does not send everything to review and a folder added later needs no
manual entry. It builds after 4.3 because it writes during `sort`, so it needs `--dry-run` (which must not write)
and the run lock. Stage 4.6 reuses its structure walk for depth 1, as depth 3 would. The principle is in
[architecture.md §1](architecture.md#1-the-library-is-the-taxonomy--categories-are-discovered-not-configured).

**Plan**
- Confirm the principle: the folders decide which groups and categories exist, and the library file describes them. An entry with no folder is never filed into, and a folder with no entry still files. The file never creates or removes folders.
- Decide which folders count as library folders: within `[library_structure] depth`; not the inbox, `.microfiche/` or an `[exclusions]` match; not a folder the ledger records as filed content (a bundle); matching the level's `name_pattern` if one is set (Stage 4.8); a real directory, not a symlink. There is no per-entry "ignore": a folder to leave out goes in `[exclusions]`.
- Decide when the file is written: automatically on the first real `sort` with a one-line notice, on every later real `sort` when a folder has been added, and from `config --sync`. Never under `--dry-run`.

**Design**
- Design `Library.structure()`: the sorted, exclusion-aware walk to the configured depth, returned as a tree. `Library.taxonomy()` becomes a view of it, so the two cannot disagree.
- Design the sync as a diff between the structure and the file: `added` (a folder with no entry) and `missing` (an entry with no folder). The merge appends added entries in sorted order, writes atomically (a temporary file, then rename) and only when something was added, and leaves every existing entry, its text and its order alone. A missing and an added folder in the same run are reported as a possible rename, never merged.
- Design where it runs: at the start of `run_sort`, under the run lock, and from `microfiche config --sync`, which prints what it added and what is missing. `config` without the flag stays read-only.
- Design failure: a library file that cannot be written (read-only, locked) is a warning and the sort goes on; a file that exists but is invalid stops the command with the error and is never overwritten.
- Design the report: `SortReport` carries the changes. The summary lists new folders once, when they are added, and missing entries on every run until the user removes them.

**Build**
- Add `Library.structure()`.
- Add the sync function and the library file write.
- Call the sync from `run_sort`, and add `--sync` to `config`.
- Show added and missing folders in the `sort` summary.

**Test**
- Write structure tests: the depth limit, exclusions, the inbox and state folder, a filed bundle recorded in the ledger, a symlink, and sorted order.
- Write sync tests: the first run creates the file with no hints; a second run changes nothing and leaves the file byte-identical; a new folder is added and reported once; hints, rules, wildcard entries and order the user wrote are preserved; a missing entry is reported and kept; a rename is reported as a possible rename.
- Write tests that `sort --dry-run` writes nothing, that an unwritable `.microfiche/` is a warning and the sort completes, and that an invalid existing file is reported and not overwritten.
- Write CLI tests: `config --sync` prints what it added and what is missing and exits 0, and plain `config` writes nothing.

**Deploy**
- Update `docs/how-to-use.md` (what the file is, the first-run notice, `config --sync` in both the Bash and PowerShell tabs, leaving a folder out with `[exclusions]`, and the "Current limitations" list), the Usage section of `README.md` and `docs/cli-reference.md` (`make docs-cli`).
- Update `architecture.md` (§1, §8 and §10), `mvp-roadmap.md` and `module-diagram.md`, and add "library file" to [CONTEXT.md](../../CONTEXT.md).
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**As built:**
- A `*` entry at a level covers every folder at that level without an entry of its own, so none is added for them. The shipped template is all `*` entries; appending an entry per folder would have reformatted every new library's file on its first sort.
- A preview does not run the sync at all, so it doesn't list folders that would be added or entries with no folder.
- The "filed bundle in the ledger" and `name_pattern` signals for what counts as a library folder are not built in the sync: at depth 2 the walk never reaches a bundle. Stage 4.8 built the first for `reclassify` (`Ledger.folder_units()`) and replaced `name_pattern` with the existing `[exclusions]`.
- A symlinked or junctioned folder is no longer a group or category (`Library.taxonomy()` now follows `structure()`), matching the inbox scan's rule.
- A rename is flagged only when exactly one entry went and exactly one folder appeared under the same parent.

**Deferred:** a description or aliases per entry, and sending them to the AI (a privacy decision); a Markdown way to read and write the same model; rename detection beyond reporting; creating folders from the file; a preview that shows what would be added.

---

## Stage 5 — Review Workflow

**Milestone:** `v0.1.5 — Review Workflow`
**Testable version:** A human can work the units that `sort` left in `_sorting/` with `microfiche review`: each
is shown with its reasons and best guesses, and the user accepts a suggestion, picks a group and category, creates a
new category folder, or skips it. Accepted units are filed through `file_batch` as one rollback-able job. This
completes the MVP's CLI surface, which no longer includes `index`.

This stage used to be "Obsidian Integration & Review Workflow". The Obsidian half (`index.md` folder notes,
`TagIndex.md` tag governance, the `[obsidian]` settings and the `index` command) was moved out of the MVP, because
it extended the target and is better built on a plugin architecture than inside `core`. Its code and design are kept in
[feature-backlog.md](feature-backlog.md#obsidian-integration). `review` stays: without it a unit below the confidence
threshold has no way out of the inbox except filing it by hand.

**Revised before building (2026-10-13).** Stage 5 does not wait for the decision-model classifier or depth 3 (since moved to the backlog), because
neither blocks it: the ranked suggestions a decision model would give, and the extra prompt a third level would add, can follow if they are built.
Decisions taken:
- *The queue is not stored.* `review` previews a sort (`run_sort(dry_run=True)`) and queues what it leaves in the inbox, so the inbox is the queue.
- *Duplicates are not in the queue.* A copy is not a classification question and microfiche never deletes; `review` counts them and `sort` lists them.
- *A folder unit is one item*, with one destination for the whole folder. To file its documents separately, use `sort --keep-folders-off`.
- *`review` may create a group or category folder*, after the person confirms the exact path. The folder is only planned until a unit is filed into it, so an abandoned session creates nothing.
- *Choices are staged and filed once.* One confirmation at the end, one `file_batch` job; Ctrl-C before it moves nothing.
- *The run lock is taken only to file*, with every choice re-checked at that moment, so deciding never blocks another run.
- *`review` needs a terminal* and exits 1 without one.

**Plan**
- Define the review-queue interaction contract (accept / modify / create-new / skip) before writing the Typer prompt loop.
- Decide where the queue comes from. `sort` keeps no queue: a unit below the threshold simply stays in the inbox, so the current `review` docstring ("from the most recent sort run") promises more than is stored. Either re-scan and re-classify the inbox, or save the last report under `.microfiche/`. The inbox is already the queue, so re-classifying is the simpler of the two; saving a report adds state that has to be kept in step with the inbox.

**Design**
- If a decision model is ever configured ([backlog](feature-backlog.md#decision-model-classifier)), design the `review` prompt to offer its top-ranked group and category candidates as suggestions to accept; with only a chat model there is nothing to rank.
- Design one choice per level, so the prompt works at depth 1 (Stage 4.6), depth 2 and, if it is ever built, depth 3 ([backlog](feature-backlog.md#subcategories-depth-3)).
- Design "create new" as making a folder in the library. `propose-categories` never creates folders, so `review` would be the first command that does: decide whether it may, and require an explicit confirmation. Stage 4.10's library file sync then lists the new folder on the next run.
- Design filing from `review` to take the same safeguards as `sort`: the run lock, the shared destination check and the duplicate check, and one `file_batch` job per session.

**Build**
- Implement the interactive `review` command's accept/modify/create/skip loop over the low-confidence queue.
- Wire `review` to it, replacing the stub in `cli/commands.py` and the placeholder `cli/review.py`.
- File the accepted units as one job and print its id and the undo hint, as `sort` does.
- Implement `reclassify --apply`, reusing Stage 3's persistence path. *(Already shipped ahead of this stage.)*

**Test**
- Write a CLI test driving the `review` loop through each of its four choices.
- Write tests that a skipped unit stays in the inbox, that accepted units are one job `rollback` undoes, and that a collision or duplicate found at review time is reported and nothing is overwritten.

**Deploy**
- Update `docs/how-to-use.md` (a section on `review` in both the Bash and PowerShell tabs, and remove it from "Current limitations"), the Usage section of `README.md`, `docs/cli-reference.md` (`make docs-cli`), the `review` row in `mvp-roadmap.md`, `architecture.md` §8, and the note in `calibration.md` that `review` is a stub.
- Tag `v0.1.5` — feature-complete against the MVP's CLI surface.

**As built:**
- `core/review.py::ReviewSession` holds the queue and the choices. `decide` checks a choice as it is made, in `sort`'s order (a place that exists or is planned, then a copy, then the name), and reserves the destination; `problem` asks the same without reserving; `commit` re-checks each choice and files them through `file_batch`. `DestinationClaims` gained a non-reserving `problem`, so the name check is written once.
- A choice is recorded as a `ClassificationResult` with `classified_by = "user"`, reasons "Chosen in review" and confidence 1.0. Nothing is learned back into hints.
- `cli/review.py` holds the prompts: accept (only when the guess names a free destination), modify (numbered lists, `n` for a new folder), skip (the default), quit. `display.render_job` became public so `review` and `sort` print the job the same way.
- The log file is written only for the commit, under the lock; asking logs to the screen only. If the lock is held at that point the choices are kept and the person is asked whether to try again.
- Safety found in review: a planned folder is refused if anything is already on disk by that name (a link, a loose file, a folder filed whole), if it is the inbox or state folder in any case, or if it is a reserved Windows name or over 255 characters. A unit's content hash is taken when it is chosen and checked again at the commit, so a document replaced meanwhile is left in the inbox. A folder made for a move that then fails is taken back, and the session's choices are used up after a commit.
- `review` also says how many documents `sort` would file (it does not ask about them) and how many copies it is leaving.
- `--use-ai`, `-v` and `-q` as on `sort`. The old test that pinned the stub's help text was replaced by one for the real command.
- The `v0.1.5` tag is a release step and was not created.

**Deferred:** ranked suggestions from a decision model, and an extra prompt per level at depth 3 (both in the backlog); going back to an item once passed; learning hints from choices.

---

## Stage 6 — MVP Hardening & Release

**Milestone:** `v0.1.6 — MVP Release`
**Testable version:** `microfiche` is installable from a tagged release, has a real coverage
baseline enforced in CI, and its documentation is accurate against shipped behavior — the
actual MVP.

**Plan**
- Define the MVP's release acceptance criteria (coverage floor, zero known must-fix gaps, docs accuracy) before starting hardening work.

**Design**
- Design the coverage gate: which modules are expected at what coverage level before a `fail_under` is set.
- Design how a release is installed. `core` and `cli` are separate workspace packages and `cli` depends on `core`, so decide whether a release ships both wheels or `cli` pins `core` by version. Today the release workflow only builds the documentation.

**Build**
- Build out a fixture library with representative data covering every classification and filing path.
- Set the coverage `fail_under` threshold once a real baseline is established.
- Add a coverage-gated job to CI's test workflow.
- Extend the release workflow to build the `core` and `cli` wheels, check that the packaged defaults file is inside them, and attach them to the GitHub release.
- Add `microfiche --version`, `rollback --last` (so the job id needn't be copied from `audit`), and a documented list of exit codes.
- Reconcile any remaining documentation drift between the README, `docs/how-to-use.md`, the architecture docs, and actual behavior, including that no shipped doc presents Obsidian folder notes or tag governance as present.

**Test**
- Run the full test suite across every supported Python version and confirm parity.
- Run the test suite on Windows as well as Linux (add `windows-latest` to the CI matrix); CI is Ubuntu-only today, while the docs and the project's own development use Windows paths and PowerShell.
- Install the built wheels into a clean virtual environment and run `microfiche --version` and a sort against the mock library.
- Run a manual end-to-end walkthrough against a realistic sample library, following `docs/how-to-use.md` verbatim (both the Bash and PowerShell steps).

**Deploy**
- Cut the `v0.1.6` release through the repo's release workflow, with the wheels attached.
- Publish the documentation site for the tagged release.

---

## Stage sequencing rationale

Each stage exists because it's the earliest point that capability can be *tested end-to-end*
rather than in isolation:

1. **Core skeleton first** — proves the parse/classify/file loop works before anything else
   depends on it.
2. **CLI + config second** — turns a hardcoded proof-of-concept into something a real user
   (or the AI-fallback and safety-net stages) can actually drive.
3. **Safety net third, before AI** — deliberately ordered ahead of AI classification: once a
   less-deterministic classifier is in the loop, having rollback already proven means a bad
   AI call is never destructive.
4. **AI fourth** — the rules engine and CLI need to be stable before adding a fallback path
   that only fires when they fail.
4.1. **Configuration consolidation before review** — Stage 5 adds review settings; building them on the layered
   defaults loader, with scores and the AI provider already configurable, avoids adding a second batch of
   hard-coded constants.
   The fuzzy-library switch is its last step: it must land before `v0.1.5` so the `fuzzy_group_threshold`
   setting never changes meaning after release (see [fuzzy-matching-options.md](fuzzy-matching-options.md)).
4.2. **Folder handling and collisions next** — the `keep_folders` default changes in 4.1, and turning it off
   has to start descending into folders; a name collision must route to review before that makes
   collisions common.
4.3. **Safe runs and input hardening** — `sort` moves files straight away, so a preview, a run lock and
   per-unit failure isolation come before the interactive `review` loop adds another way to file.
4.4. **Logging next** — it records decisions made by everything above, and Stages 5 and 6
   are easier to build and debug with it in place. It is small enough to move earlier if debugging needs it.
   (4.5, a decision-model classifier gated on a measurement, was moved to the backlog while under review; see
   [feature-backlog.md](feature-backlog.md#decision-model-classifier).)
4.6. **Flat libraries before Stage 5** — `review` is built on the library's shape, so a one-level
   library has to exist first or it is reworked.
   (4.7, subcategories at depth 3, was moved to the backlog while under review; see
   [feature-backlog.md](feature-backlog.md#subcategories-depth-3).)
4.8. **Non-library folders** — useful on its own at depth 2, where `reclassify` would otherwise split a
   filed bundle. It is also the rule depth 3 would need to tell a subcategory from one.
   (4.9, an optional filing target mode, was moved to the backlog while under review; see
   [feature-backlog.md](feature-backlog.md#filing-target-mode-file_at).)

4.10. **Library file sync, after 4.3** — the library file arrives in 4.1 as a hand-written file; this makes it follow
   the folders, so a new library is not all review and a new folder needs no manual entry. It writes during
   `sort`, so it needs 4.3's `--dry-run` and run lock. Build it before 4.6, which reuses its structure
   walk for depth 1.
5. **Review fifth** — it is the other end of the sort loop: everything `sort` holds back lands in the queue it
   works. It needs the earlier stages' safeguards (the collision and duplicate checks, the run lock, rollback) because
   it files too. The Obsidian integration used to share this stage and was moved out of the MVP, so that it can be
   designed as a plugin. It does not depend on 4.5 or 4.7, which were later moved to the backlog (see its "Revised before
   building" note).
6. **Hardening last** — you can't set a meaningful coverage floor or write accurate docs
   until the feature set has stopped changing underneath them.
