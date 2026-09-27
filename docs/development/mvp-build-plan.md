# MVP build plan

A from-scratch, staged process for building microfiche to MVP, organized as six stages that
each ship a **testable version** — something you can actually run and demo, not just a set of
merged PRs. Every stage is internally sequenced Plan → Design → Build → Test → Deploy.

This is a different document from [mvp-roadmap.md](mvp-roadmap.md): that one is a bottom-up
status report against the *current* codebase (what's done/partial/stub, right now). This one
is the top-down process — the order you'd build microfiche in if you were starting today,
and a structure meant to be dropped directly into a GitHub Project. Read
[architecture.md](architecture.md) for the design detail behind any given stage's tasks.

## How to run this as a GitHub Project

- **Stage → Milestone.** Create one GitHub Milestone per stage (`v0.1 — Core Filing
  Skeleton`, `v0.2 — Configurable Rules Engine, Taxonomy & CLI`, …). Each milestone's
  description is that stage's "Testable version" line below.
- **Task → Issue.** Each bullet under Plan/Design/Build/Test/Deploy becomes one issue, titled
  with its one-sentence objective verbatim, assigned to its stage's milestone.
- **Phase → Label.** Apply one of `phase:plan`, `phase:design`, `phase:build`, `phase:test`,
  `phase:deploy` to every issue. Add `stage:1` … `stage:6` labels too if you want them
  independent of milestone (useful for filtering across a re-ordered board).
- **Project fields.** Add a single-select `Phase` field mirroring the labels above so the
  board can be grouped or filtered by phase within a milestone. A Table view grouped by
  Milestone, sorted by Phase, reproduces this document exactly.
- **Definition of done per stage:** every issue in the milestone is closed *and* the stage's
  "Testable version" statement is true when you check it out and run it.

---

## Stage 1 — Core Filing Skeleton

**Milestone:** `v0.1 — Core Filing Skeleton`
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
- Merge to `main` and tag `v0.1-alpha`; this stage ships to the team, not to users.

---

## Stage 2 — Configurable Rules Engine, Taxonomy Discovery & CLI

**Milestone:** `v0.2 — Configurable Rules Engine, Taxonomy & CLI`
**Testable version:** A `microfiche sort --library <path>` command that discovers a library's
existing group/category folder structure, classifies documents in a `_sorting/` inbox against
that taxonomy using YAML-configured rules, and files them — runnable and demoable by a human.

**Plan**
- Define the two-stage (group, then category) classification contract that replaces Stage 1's flat hardcoded classifier.
- Define the config file (`[categories]`, `[filing_rules]`, `[naming_rules]`, `[exclusions]`) and what each one governs.

**Design**
- Design the `Taxonomy` model representing the library's discovered `{group: [category, ...]}` structure.
- Design the rules-engine interface: filename-glob rules checked before keyword-hint rules, scoped to a resolved group's existing categories.
- Design the CLI's command surface and argument conventions (`--library`, `--keep-folders`) before writing any Typer code.

**Build**
- Implement `discover_taxonomy` to walk a library's folders, excluding configured exclusions, into a group → category map.
- Implement group resolution: filename/content keyword match, with fuzzy matching for near-misses.
- Implement category resolution: filename-glob rules, then keyword hints, scoped to the resolved group.
- Implement per-library YAML config loading and validation for all four config files.
- Implement the `sort` command in a Typer CLI, wiring config loading → taxonomy discovery → classification → filing.
- Implement Rich-rendered console output summarizing filed vs. needs-review counts.

**Test**
- Write a taxonomy-discovery test against a fixture library with a nested group/category structure and an excluded folder.
- Write group-resolution tests covering an exact match, a fuzzy near-miss, and a no-match case.
- Write a category-resolution test confirming filename-rule precedence over keyword-hint matching.
- Write a CLI smoke test asserting `microfiche sort --library <fixture>` exits 0 and produces the expected filed layout.

**Deploy**
- Publish the `microfiche` console-script entry point so `uv run microfiche sort` works from a clean checkout.
- Tag `v0.2` as the first internally demoable release.

---

## Stage 3 — Safety Net: Audit Trail & Rollback

**Milestone:** `v0.3 — Audit Trail & Rollback`
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
- Tag `v0.3` — the first version whose core safety promise ("nothing is ever lost") is actually true.

---

## Stage 4 — AI Fallback for Low-Confidence Classification

**Milestone:** `v0.4 — AI Fallback`
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
- Add a `--ai-provider ollama|openai` CLI option (defaulting to Ollama) to `sort` and `resort`.

**Test**
- Write unit tests for the AI-fallback trigger condition (below-threshold vs. above-threshold rules results).
- Write unit tests for both providers against a mocked model response.
- Write an integration test confirming a document only the AI path can classify gets filed correctly end-to-end with `--use-ai`.

**Deploy**
- Document the local Ollama setup steps needed to exercise `--use-ai` in a contributor's dev environment.
- Tag `v0.4`.

---

## Stage 5 — Obsidian Integration & Review Workflow

**Milestone:** `v0.5 — Obsidian Integration & Review`
**Testable version:** Filed folders get a regenerated `index.md`, extracted keywords are
governed against a library's `TagIndex.md`, and a human can work the low-confidence review
queue interactively via `microfiche review` — completing the CLI surface
[architecture.md](architecture.md) describes.

**Plan**
- Define the review-queue interaction contract (accept / modify / create-new / skip) before writing the Typer prompt loop.
- Define the "suggest-only" tag governance contract: what happens to a tag with no canonical match.

**Design**
- Design the `index.md` folder-note format (wikilinks for `.md` files, relative links for other formats).
- Design the `TagIndex.md` parser and the `## Proposed` section convention for ungoverned tags.

**Build**
- Implement folder-note generation that regenerates a touched folder's `index.md` after every sort/resort/rollback.
- Implement tag governance that fuzzy-matches extracted keywords against `TagIndex.md` and appends unmatched ones to `## Proposed`.
- Implement the interactive `review` command's accept/modify/create/skip loop over the low-confidence queue.
- Wire the `index` and `review` commands to this new core logic.
- Implement `resort --apply`, reusing Stage 3's persistence path.

**Test**
- Write unit tests for `index.md` generation against a folder with mixed Markdown and non-Markdown files.
- Write unit tests for tag governance covering a canonical match, a fuzzy match, and a fully novel tag.
- Write a CLI test driving the `review` loop through each of its four choices.

**Deploy**
- Tag `v0.5` — feature-complete against the documented CLI surface.

---

## Stage 6 — MVP Hardening & Release

**Milestone:** `v1.0 — MVP Release`
**Testable version:** `microfiche` is installable from a tagged release, has a real coverage
baseline enforced in CI, and its documentation is accurate against shipped behavior — the
actual MVP.

**Plan**
- Define the MVP's release acceptance criteria (coverage floor, zero known must-fix gaps, docs accuracy) before starting hardening work.

**Design**
- Design the coverage gate: which modules are expected at what coverage level before a `fail_under` is set.

**Build**
- Build out a fixture library with representative data covering every classification and filing path.
- Set the coverage `fail_under` threshold once a real baseline is established.
- Add a coverage-gated job to CI's test workflow.
- Reconcile any remaining documentation drift between the README, `docs/how-to-use.md`, the architecture docs, and actual behavior.

**Test**
- Run the full test suite across every supported Python version and confirm parity.
- Run a manual end-to-end walkthrough against a realistic sample library, following `docs/how-to-use.md` verbatim (both the Bash and PowerShell steps).

**Deploy**
- Cut the `v1.0` release through the repo's release workflow.
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
5. **Obsidian/review fifth** — polish and completeness features that don't block earlier
   stages from being independently useful.
6. **Hardening last** — you can't set a meaningful coverage floor or write accurate docs
   until the feature set has stopped changing underneath them.
