# MVP build plan

A from-scratch, staged process for building microfiche to MVP, organized as six stages (plus four
interim stages, 4.1 to 4.5, added after review) that
each ship a **testable version** — something you can actually run and demo, not just a set of
merged PRs. Every stage is internally sequenced Plan → Design → Build → Test → Deploy.

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
  numbered with a decimal (Stages 4.1 to 4.5) is an update to the stage before it and gets no tag of its own;
  its milestone is named for the stage, not for a version. Tags keep the `v` prefix, as `v0.1.0` does.
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
- Add a `--ai-provider ollama|openai` CLI option (defaulting to Ollama) to `sort` and `reclassify`. *(Not built: `sort --use-ai` is Ollama-only and `OpenAIProvider` is unreachable from the CLI; see [mvp-roadmap.md](mvp-roadmap.md). Stage 4.1 closes this through an `[ai]` config section instead of a CLI option.)*

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

Why before Stage 5: `review` and `index` add settings of their own (`[obsidian]`, a review section), and
should be built against the layered loader rather than adding to the hard-coded constants. Stages 4.2 to 4.4
also add settings, so they build on it too. The reasoning is in [config-review.md](config-review.md); the
target design is [architecture.md §10](architecture.md#10-configuration-layout-planned-stage-41).

**Plan**
- Decide which constants become settings and which stay fixed (file names, chunk sizes, display styles), per [config-review.md](config-review.md) point 1.
- Define the split between settings (`microfiche-config.toml`) and library data (`microfiche-library.json`), and what is dropped: `library_templates`, `levels`, `file_target_level`.
- Decide whether `--use-ai` stays a per-run switch or becomes `[ai] enabled`, and whether the `init` command and a template catalog are in the MVP (the default is no).
- Write the stage's exit criteria as a single sentence: with the shipped defaults the calibration report is unchanged, and each new setting changes the behaviour it names.

**Design**
- Design the packaged defaults file and the load order: defaults, then the library's file, deep-merged (tables merge, lists replace), then validated.
- Design the `[classification]` additions (signal strengths, fuzzy thresholds, `max_document_chars`) with range validation, and how they reach `RulesEngine` and `LLMClassifier` by constructor.
- Design `[sorting] keep_folders` (default on) and the CLI precedence: flag, then library config, then packaged default. What the setting does when off is Stage 4.2.
- Design `[ai]` (provider, model, host, timeout, score, `api_key_env`) and the `build_provider` factory, leaving room for a second kind of AI classifier (a decision model, Stage 4.5) alongside the chat model. `provider = "openai"` sends document text off the machine, so it must be chosen explicitly and the run must say so.
- Design the `microfiche-library.json` node schema (`name`, `hints`, `rules`, `children`), with category hints global by category name to start with.

**Build**
- Add `core/defaults/microfiche-config.toml`, load it with `importlib.resources`, and remove the default values from the pydantic models.
- Move the signal strengths, fuzzy thresholds and `max_document_chars` into `[classification]` and thread them through the constructors.
- Add `[sorting] keep_folders = true` and change `--keep-folders` to `--keep-folders/--no-keep-folders`; make `propose-categories` use the setting too.
- Add `AIConfig` and `build_provider`, so `OllamaProvider` and `OpenAIProvider` are both reachable from `sort --use-ai`; this closes the Stage 4 `--ai-provider` gap. Read the OpenAI key from the environment variable named by `api_key_env`, never from the file.
- Add the `microfiche-library.json` model, loader and generated JSON Schema, and move `category_hints` and `filing_rules` into it.
- Delete `library_templates`, `levels` and `file_target_level` from the config; reject any `depth` other than 2 with a clear message.
- Fix the stale `.yaml` mentions in `library/templates.py` and `rules/metadata_rules.py`, and update the shipped template folder (`microfiche/`) to match.

**Test**
- Write a test that the shipped template and the packaged defaults agree (the `[obsidian] enabled` mismatch is the known case).
- Write config tests for the layered load: a missing file, a partial file, a list that replaces, and a range violation on each new score.
- Write a test that each new setting changes the behaviour it names, using fake resolvers rather than the real rules.
- Write a CLI test for `keep_folders` precedence: flag over config over default.
- Write tests that `build_provider` returns the provider the config names, and fails with a clear message when the OpenAI key variable is unset.
- Re-run `tests/calibration/report.py` and confirm the default threshold's findings still hold; update [calibration.md](calibration.md) if not.

**Deploy**
- Update `README.md`, `docs/how-to-use.md` and `docs/cli-reference.md` (`make docs-cli`) for the new settings and the changed `--keep-folders` default, in both the Bash and PowerShell tabs.
- Update `architecture.md` (§4 and §10), `mvp-roadmap.md` and `module-diagram.md`, and add "library template" and "hints" to [CONTEXT.md](../../CONTEXT.md).
- Merge to `main` without a new tag: this stage is an update on top of `v0.1.4`, and its changes ship with the next tag, `v0.1.5`.

**Deferred:** an `init` command and a template catalog; a `command` AI provider (needs a decision on running
commands from a config inside a shared library); per-group hint overrides.

---

## Stage 4.2 — Folder Handling & Name Collisions

**Milestone:** `Stage 4.2 — Folder Handling & Name Collisions` (an untagged update to `v0.1.4`)
**Testable version:** A name already taken at the destination no longer crashes `sort`: that unit stays in the
inbox for review, with the reason, and everything else is filed. With `keep_folders` on, the mock library's
inbox folder files whole under its dominant category; with it off, the files inside are filed one by one and
the emptied folder is removed, recorded so `rollback` recreates it.

Why now: today `file_batch` raises `FileExistsError` part-way through a batch and `commands.sort` does not
catch it, so a collision gives a traceback and a half-finished job. `keep_folders = false` also has to start
descending into folders, which makes same-name collisions between sub-folders likely. The reasoning is in
[operations-review.md](operations-review.md).

**Plan**
- Decide what `keep_folders = false` means. Today it ignores inbox folders (the scanner only descends into them when it is on), so their contents are never filed. The intended meaning is: descend, and file each document on its own. That changes today's behaviour and `architecture.md` §4.
- Decide the collision policy: a unit whose destination is taken stays in the inbox for review, with the reason. Nothing is renamed, suffixed or overwritten, matching what `reclassify` already does with its `conflict` action.

**Design**
- Design one destination check shared by `sort` and `reclassify`, applied after the naming rules, covering both a file that already exists and two units in the same run headed for the same destination (the first files, the second goes to review). `file_batch`'s `FileExistsError` stays as the last line of defence against a race.
- Design how an inbox folder is handled when `keep_folders` is off:
  - Its documents, including those in nested sub-folders, become single-document units.
  - Two files with the same name from different sub-folders are a collision, handled as above.
  - Once every supported file has moved, the emptied folder is removed only if it is truly empty. A folder that still holds an unsupported, unreadable or review-bound file stays, and the report says why.
  - The removal is recorded in the job (a new audit event kind, or a field on the job; see [data-model.md](data-model.md)), so `rollback` recreates the folder. This must be reconciled with the "nothing is ever deleted" wording in the README and `AGENTS.md`: no file is deleted, only an empty folder.

**Build**
- Add the shared destination check, and route a collision to `SortReport.needs_review` with a reason such as "a file named X already exists in Project Phoenix/02 Architecture".
- Make `scan_sorting_inbox` descend into inbox folders when `keep_folders` is off, returning one single-document unit per supported file (with the folder it came from recorded on the unit, so the emptied folder can be found).
- Add empty-folder handling to `file_batch` (or a step in `run_sort` after it): remove a folder left empty by the `no` option, record the removal in the job, and make `rollback_job` recreate it; leave a non-empty folder and report it.
- Show collision and kept-folder reasons in the `sort` summary.

**Test**
- Write collision tests: an existing file at the destination sends only that unit to review with the reason, the rest are filed, nothing is overwritten and there is no traceback; two units headed for the same destination file one and review the other.
- Add a folder to `tests/mock_library/_sorting/` that shows both outcomes. Two files can't do it: two documents that file differently tie, and a tie goes to review rather than to one location. Use three files, with two voting for one category and one for another. For example `phoenix-weekly-pack/` holding two Project Phoenix architecture documents (`architecture-decision-log.md`, `component-diagram-notes.md`) and one Project Phoenix research document (`research-summary.md`). Keep each document's wording to one category's name so the result doesn't depend on which name is matched first.
- Write end-to-end tests against that folder:
  - `keep_folders` on: the whole folder files into `Project Phoenix/02 Architecture/`, one folder record in the ledger, and `_sorting/` no longer holds it.
  - `keep_folders` off: the two architecture documents file into `02 Architecture/` and the research document into `03 Research/`, as three separate records in one job.
  - `keep_folders` off, emptied folder: the folder is gone after the sort, and `rollback` restores it and all three files exactly.
  - `keep_folders` off, folder not emptied (add an unsupported file such as a `.png`, or a sub-folder name clash): the folder stays and the report names why.
- Update the existing tests that copy `tests/mock_library` (`tests/cli/test_app.py`, `tests/core/test_organizer.py`, `tests/core/test_reclassify.py`) for the new folder, and check any that assert counts of filed or review items.

**Deploy**
- Update `docs/how-to-use.md` and the README (collisions, and what `--no-keep-folders` does), `architecture.md` §4 and the "nothing is ever deleted" wording.
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**Deferred:** renaming on collision (a suffix setting); detecting that the colliding file is an exact duplicate.

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
- Design `--dry-run`: classification runs as usual, but nothing is moved and no job, ledger record or audit line is written; the output is labelled as a preview.
- Design the run lock: `.microfiche/lock` holding the process id and start time, stale-lock detection, released on exit, and taken by `sort`, `reclassify --apply` and `rollback` (read-only commands don't take it).
- Design per-unit failure isolation in `run_sort` and `file_batch`: a failed move is not recorded as a move, the job keeps the successful ones, and the unit is reported for review.
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
handlers; the CLI adds `-v/--verbose` and `-q/--quiet`, writes a rotating `.microfiche/microfiche.log`, and
shows progress on long runs; `audit.log` is unchanged.

Why now: there is no logging today. `core/utils/logging.py::get_logger` is unused and writes
`organization.log` outside the `.microfiche/` convention, so when a unit lands in review or an AI call fails
there is nothing to read afterwards. Stages 5 and 6 are easier to build and debug with it in place.

**Plan**
- Separate the two kinds of record: `audit.log` and the ledger are product data that `rollback` reads and must stay stable; the diagnostic log is for people and can change.
- Decide what is logged: scan results, each classification with its reasons, AI call outcome and timing, skipped items and why, filing and rollback steps. Never document contents or API keys.

**Design**
- Design logger names (`microfiche.<module>`) and the rule that only the CLI configures handlers, so `core` stays quiet when used as a library.
- Design the levels: warnings and errors always; `-v` adds INFO to the console and DEBUG to the file; `-q` shows errors only.
- Design a `[logging]` section (`level`, `file`, `max_bytes`, `backup_count`) with defaults in the packaged file.
- Design progress output: shown only when attached to a terminal and when a run has many units or slow AI calls, so piped output stays clean.

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
- Update `docs/how-to-use.md` with a troubleshooting section (where the log is, what `-v` shows), the README and `docs/cli-reference.md`.
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**Deferred:** structured (JSON) log output; log shipping.

---

## Stage 4.5 — Decision-Model Classifier

**Milestone:** `Stage 4.5 — Decision-Model Classifier` (an untagged update to `v0.1.4`)
**Testable version:** `sort --use-ai` can use either a chat model (as today) or a decision-model classifier,
chosen in `[ai]`; both sit behind `Classifier` as resolvers. A decision model's own probability becomes the
confidence instead of a flat `0.70`, and the calibration report shows on the same corpus how each performs,
so the choice is a measurement.

Why here: it needs 4.1 (the `[ai]` section, the configurable AI score and `build_provider`), 4.3 (the
AI-unavailable path, so a slow or hosted backend degrades safely) and 4.4 (logs of each call and its timing).
The options, candidate models and adoption rules are in [ai-classifier-options.md](ai-classifier-options.md).

**Plan**
- Check the candidates (Jev, Clef, Nimble) against their own documentation or model cards: licence, local or hosted, size and hardware, Windows support, whether per-option probabilities are returned, and the input limit. Record the results in `ai-classifier-options.md`; the search summaries there are unverified.
- Decide the privacy rule: a hosted model sends document text off the machine, so it is treated like `OpenAIProvider` (chosen explicitly, the run says so, any key comes from an environment variable).
- Define the adoption gate: the decision model is adopted only if, on the calibration corpus, it is no less precise than the chat model at the same coverage and its probabilities separate right answers from wrong ones. If none passes, record that and stop the stage here.

**Design**
- Design a `ChoiceModel` protocol, `choose(text, question, options) -> Choice` with the chosen option or none, its probability and the ranked alternatives. It is a separate seam from `AIProvider`, because the two vary: one returns free text to be parsed, the other returns a bounded choice with a score.
- Design `ChoiceClassifier` as a `Resolver` beside `LLMClassifier`. The options are the taxonomy's names plus "none", and `Classifier` still checks the answer against the taxonomy and applies the threshold.
- Design the mapping from probability to confidence (direct, or scaled and clamped) as a setting, since a model's probabilities are not automatically calibrated.
- Design how `[ai]` names the kind (for example `kind = "chat" | "choice"`) alongside `provider`, `model` and `endpoint`. One kind at a time; chaining a decision model before a chat model is deferred.

**Build**
- Add `ai/choice_classifier.py` with the `ChoiceModel` protocol and `ChoiceClassifier`.
- Add one backend, the best verified candidate, behind `build_provider`, with any new dependency in the `ai` extra.
- Use the model's probability as the resolver's confidence, and log each call's choice, probability and timing (Stage 4.4).
- Extend `tests/calibration/` with saved decision-model answers, as it already does for the chat model's.

**Test**
- Write unit tests with a fake `ChoiceModel`: an option is chosen, "none" is chosen, an option that isn't in the taxonomy is treated as unresolved, and a probability below the threshold goes to review.
- Write tests for the probability-to-confidence mapping, including its bounds.
- Write a backend test against a mocked response; the suite uses no network and no model.
- Re-run the calibration report with both kinds and pin the finding in `test_calibration.py`.

**Deploy**
- Update `docs/how-to-use.md` (which kind to choose, what leaves the machine, the new settings), the README, `docs/cli-reference.md` and `calibration.md`.
- Merge to `main` without a new tag; the changes ship with `v0.1.5`.

**Deferred:** training a small classifier on the library's own ledger; chaining models; downloading and managing model files for the user.

---

## Stage 5 — Obsidian Integration & Review Workflow

**Milestone:** `v0.1.5 — Obsidian Integration & Review`
**Testable version:** Filed folders get a regenerated `index.md`, extracted keywords are
governed against a library's `TagIndex.md`, and a human can work the low-confidence review
queue interactively via `microfiche review` — completing the CLI surface
[architecture.md](architecture.md) describes.

**Plan**
- Define the review-queue interaction contract (accept / modify / create-new / skip) before writing the Typer prompt loop.
- Define the "suggest-only" tag governance contract: what happens to a tag with no canonical match.

**Design**
- If a decision model is configured (Stage 4.5), design the `review` prompt to offer its top-ranked group and category candidates as suggestions to accept; with only a chat model there is nothing to rank.
- Design the `index.md` folder-note format (wikilinks for `.md` files, relative links for other formats).
- Design the `TagIndex.md` parser and the `## Proposed` section convention for ungoverned tags.

**Build**
- Implement folder-note generation that regenerates a touched folder's `index.md` after every sort/reclassify/rollback.
- Implement tag governance that fuzzy-matches extracted keywords against `TagIndex.md` and appends unmatched ones to `## Proposed`.
- Implement the interactive `review` command's accept/modify/create/skip loop over the low-confidence queue.
- Wire the `index` and `review` commands to this new core logic.
- Implement `reclassify --apply`, reusing Stage 3's persistence path. *(Already shipped ahead of this stage.)*

**Test**
- Write unit tests for `index.md` generation against a folder with mixed Markdown and non-Markdown files.
- Write unit tests for tag governance covering a canonical match, a fuzzy match, and a fully novel tag.
- Write a CLI test driving the `review` loop through each of its four choices.

**Deploy**
- Tag `v0.1.5` — feature-complete against the documented CLI surface.

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
- Reconcile any remaining documentation drift between the README, `docs/how-to-use.md`, the architecture docs, and actual behavior.

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
4.1. **Configuration consolidation before Obsidian/review** — Stage 5 adds `[obsidian]` and review
   settings; building them on the layered defaults loader, with scores and the AI provider already
   configurable, avoids adding a second batch of hard-coded constants.
4.2. **Folder handling and collisions next** — the `keep_folders` default changes in 4.1, and turning it off
   has to start descending into folders; a name collision must route to review before that makes
   collisions common.
4.3. **Safe runs and input hardening** — `sort` moves files straight away, so a preview, a run lock and
   per-unit failure isolation come before the interactive `review` loop adds another way to file.
4.4. **Logging next** — it records decisions made by everything above, and Stages 5 and 6
   are easier to build and debug with it in place. It is small enough to move earlier if debugging needs it.
4.5. **Decision-model classifier last of the 4.x steps** — it needs the `[ai]` config (4.1), the safe
   AI-unavailable path (4.3) and logs (4.4), and it is gated on a measurement: if no candidate beats the chat
   model on the calibration corpus, the stage ends with that finding and Stage 5 proceeds unchanged.
5. **Obsidian/review fifth** — polish and completeness features that don't block earlier
   stages from being independently useful.
6. **Hardening last** — you can't set a meaningful coverage floor or write accurate docs
   until the feature set has stopped changing underneath them.
