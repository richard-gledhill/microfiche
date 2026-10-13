# Feature backlog

Features taken out of the MVP on purpose, and ideas for beyond it, kept here with enough detail to bring them back.
Entries are placeholders, not commitments: none is tied to a release or can block one, they are not in priority order,
and each needs more specification and planning before it is built.

## Where a deferred or future item goes

Record an item once, in the first row that fits, and link to it from anywhere else.

| The item is... | It goes in |
|---|---|
| A stage of the MVP's work | [mvp-build-plan.md](mvp-build-plan.md), which covers the MVP only |
| A gap, an improvement to what is built, or a small postponed item (OCR, a lock timeout, watch mode) | [mvp-roadmap.md](mvp-roadmap.md#future-work-and-deferred-beyond-mvp) |
| A feature outside the MVP with a design to keep, code removed from the MVP, or an idea that needs specifying | This file |

An entry here moves to the build plan, as a stage, when it is picked up, and is removed from this file.

Each entry says why it was deferred, what was removed and where to restore it from, the design to keep, and the
questions to settle before building it again.

- [Obsidian integration](#obsidian-integration)
- [Plugin architecture](#plugin-architecture)
- [Opt-in flatten when the depth is reduced](#opt-in-flatten-when-the-depth-is-reduced)
- [Filing target mode (`file_at`)](#filing-target-mode-file_at)
- [Decision-model classifier](#decision-model-classifier)
- [Subcategories (depth 3)](#subcategories-depth-3)

---

## Obsidian integration

**Status:** removed from the MVP on 2026-10-12. It was implemented and unit-tested but never wired into `sort`, so no
user-visible behaviour was lost. It was Stage 5 of [mvp-build-plan.md](mvp-build-plan.md) together with `review`;
`review` stayed in the MVP and this half moved here.

**Why deferred.** It widened the MVP past "classify, file, undo, and work the review queue". It is also one of what
should be several integrations with other software, so it is better designed on top of the
[plugin architecture](#plugin-architecture) than bolted onto `core`. Nothing in the sort loop depends on it.

### What was removed, and where to get it back

The last commit that contains all of it is `551eec9` on `main`. Merges there are plain merge commits, so the commit
stays reachable.

| What | Where it was |
|---|---|
| `index.md` writer | `packages/core/src/core/obsidian/index_writer.py` |
| `TagIndex.md` parser and writer | `packages/core/src/core/obsidian/tag_index.py` |
| Tag matcher | `packages/core/src/core/obsidian/tag_mapper.py` (and the package `__init__.py`) |
| Tests | `tests/core/test_index_writer.py`, `tests/core/test_tag_governance.py` |
| `[obsidian]` config section | `ObsidianConfig` and the `MicroficheConfig.obsidian` field in `core/config.py`; the section in `core/defaults/microfiche-config.toml`, in the template `microfiche/microfiche-config.toml`, and in the two test libraries' configs |
| `index` command | `commands.index` and its registration in `cli/app.py` (a stub that always exited 1) |
| Diagram entry | the `core/obsidian` line in `scripts/module_diagram.py`'s `SUBGRAPHS` |

To read or restore a file:

```bash
git show 551eec9:packages/core/src/core/obsidian/tag_mapper.py
git checkout 551eec9 -- packages/core/src/core/obsidian tests/core/test_index_writer.py tests/core/test_tag_governance.py
```

Restoring the files does not restore the config section or the command; those need the design questions below
answered first.

### What it did

**`index.md` folder notes** (`index_writer.write_index(folder, entries)`). Writes `<folder>/index.md`, regenerated in
full each time, from a list of `IndexEntry(file_name, tags, confidence, filed_on)`. The title is the folder's name;
entries are sorted case-insensitively by file name. A Markdown file is linked as a wikilink and any other file as a
relative link, so the notes read normally in Obsidian:

```markdown
# 01 Requirements

- [[architecture_review]] — #requirements #phoenix (filed 2026-09-07, confidence 0.91)
- [spec](spec.pdf) — #architecture (filed 2026-09-07, confidence 0.80)
```

The intent was to regenerate it for every folder touched by a sort, a reclassify or a rollback, so it always matches
what is there. That call was never written.

**`TagIndex.md` vocabulary** (`tag_index.TagIndex`). Reads the library's root `TagIndex.md`: a `# Tag Index` heading,
then one `- #tag` line per canonical tag. Tags under a `## Proposed` heading are proposals awaiting a human, kept apart
from the canonical list. `load` returns an empty index if the file is missing; `add_proposed` ignores a tag that is
already canonical; `save` rewrites the file with canonical tags first and the proposed ones after.

**Suggest-only tag governance** (`tag_mapper.map_tags(candidates, tag_index, mode)`). The decision, first recorded in
[architecture.md §6](architecture.md#obsidian-integration): a tag with no close canonical match is still applied to
the document and is added to `## Proposed`, never merged into the reviewed list. Three modes:

| Mode | A close canonical match | No close match |
|---|---|---|
| `off` | candidates returned unchanged; the index is not read or written | |
| `suggest` (default) | replaced by the canonical tag | kept, and proposed |
| `strict` | replaced by the canonical tag | dropped |

Matching used RapidFuzz `WRatio` with `utils.default_process` (lowercases and strips punctuation on both sides,
keeps accents), `score_cutoff=89`, and a rounded score of at least 90 to count. So `Python` maps to `python` and
`Machine_Learning` to `machine-learning`, `Café` maps to `café`, but `munchen` does not match `münchen` and `ber` does
not match `über`. Whether to fold accents is still undecided.

**Config** (all removed):

```toml
[obsidian]
enabled = false
tag_index_path = "TagIndex.md"
tag_mode = "suggest"   # suggest | strict | off
```

`enabled` was never read, so it did nothing; `tag_mode` and `tag_index_path` were only read by tests.

**Tests that existed.** `index.md` links Markdown as a wikilink and other files as relative links; the tag index
round-trips through save and load; `suggest` normalises a near match and proposes a new tag; `strict` drops an
unmatched tag; matching ignores case, punctuation (`Machine_Learning`) and keeps accents (`Café`, and `ber` against
`über` does not match).

### The old Stage 5 plan for it

Kept from the build plan so the intent is not lost:

- Define the suggest-only tag governance contract: what happens to a tag with no canonical match.
- Design the `index.md` folder-note format (wikilinks for `.md` files, relative links for other formats).
- Design the `TagIndex.md` parser and the `## Proposed` section convention for ungoverned tags.
- Decide how tags with accents match (see above, and [fuzzy-matching-options.md](fuzzy-matching-options.md)).
- Regenerate a touched folder's `index.md` after every sort, reclassify and rollback.
- Fuzzy-match extracted keywords against `TagIndex.md` and append unmatched ones to `## Proposed`.
- Add an `[obsidian]` settings section (enable switch, tag mode, tag index path, a tag match threshold).
- Wire a `microfiche index [--scope PATH]` command that force-regenerates the notes.
- Tests: `index.md` generation for a folder of mixed Markdown and other files; tag governance for a canonical match, a
  fuzzy match and a fully novel tag.

### Questions to settle before building it again

- **Where do tags come from?** The modules only mapped tags handed to them. Nothing in microfiche extracts keywords
  from a document, and the ledger has no `tags` field ([data-model.md](data-model.md)). Both are needed first, and
  tag extraction may be useful beyond Obsidian.
- **Generated files inside the library.** An `index.md` is a file microfiche writes among the user's documents, the
  thing the ledger was introduced to avoid ([architecture.md §7](architecture.md#7-classification-ledger-replaces-per-file-sidecars)).
  If it comes back, then `reclassify` (which walks every file under the library) and `DuplicateIndex` (which hashes
  same-size library files) would both see it, so it must be recognised and skipped, and `rollback` must either record
  its writes or regenerate it. The same applies to `TagIndex.md` at the library root.
- **When it runs.** After `file_batch`, after `rollback_job`, and after `reclassify --apply`: a hook on a finished
  job, receiving the job and the folders it touched. That is the first extension point of the plugin architecture.
- **Failure.** A failed note write must not fail or undo a sort.
- **Config name.** Probably under the plugin's own namespace rather than a top-level `[obsidian]`; decide with the
  plugin architecture, not before.
- **Accent folding** for tag matching (above).

---

## Plugin architecture

**Status:** not started. Requirements only; there is no design and, deliberately, no code.

**Why.** Obsidian is the first integration, and likely not the last (other note-taking or document tools). Integrating
each of them by adding modules and a config section to `core` would grow `core` with every tool and make each one
a permanent part of the product.

**Why not now.** [AGENTS.md](../../AGENTS.md) says to add a seam only where something actually varies, and one
implementation is not a seam. With zero integrations in the MVP there is nothing to vary, and a framework designed
first would be shaped by guesses. Design it when the first integration is built, using that integration as the
test of the interface, and check it against a second use before treating it as stable.

### Requirements to design against

- **`core` does not depend on any integration.** The dependency points one way: an integration depends on `core`.
  The repo is already a uv workspace of `core` and `cli`, so an integration could be a third package (for example
  `packages/obsidian`) without `core` changing. This is an option, not a decision.
- **Extension points** the Obsidian work needs, in the order it needs them:
  1. A hook when a job finishes: sort, `reclassify --apply` and `rollback`, receiving the job and the folders it touched.
  2. A source of tag vocabulary, if tag governance returns.
  3. Settings of its own, validated like the rest of the config (an unknown setting is an error), under a namespace
     that cannot collide with core's sections.
  4. Optionally, a command of its own (such as the old `index`), registered without editing `cli/app.py`.
- **A plugin cannot break the core promise.** A plugin that fails must not fail, abort or half-apply a sort, and must
  not make a job impossible to roll back. This follows the existing per-unit failure isolation.
- **What a plugin writes must be accounted for.** Anything written into the library is either recorded in the job
  (so `rollback` undoes it) or recognisably generated (so `reclassify` and the duplicate check ignore it).
- **Off by default, explicit when on.** Same rule as the OpenAI provider: nothing that changes the library or sends
  data elsewhere runs unless the user turned it on, and a run says so.
- **Discovery.** How a plugin is found (a setting naming it, a Python entry point, or being installed at all) is
  open. Prefer the simplest thing that works for one plugin in the same repo.

### Tests it will need

Restore the removed `index.md` and tag governance tests, and add tests that the hook runs after sort, reclassify and
rollback, that a failing plugin does not fail a sort, and that `reclassify` and the duplicate check ignore generated
notes.

### Open questions

- Is an integration a separate package, or a module behind an optional extra like `ai`?
- Does the hook receive the `Job` model directly (coupling a plugin to its schema), or a smaller summary type?
- Do plugins need ordering or dependencies, or is one at a time enough?
- Should `review` (Stage 5) expose any hook, so that choices made there can feed a plugin? Probably not until a
  plugin needs it.


---

## Opt-in flatten when the depth is reduced

**Status:** to be reviewed for future implementation. Raised on 2026-10-12 while building
[Stage 4.8](mvp-build-plan.md#stage-48--non-library-folders); it needs specifying before it is planned.

**The situation.** A user reduces `[library_structure] depth` (from 2 to 1 today, and from 3 to 2 if
[depth 3](#subcategories-depth-3) is ever built). The folders that were categories
are now plain folders inside a group, and the items filed in them sit below the library's depth.

**What happens now.** Nothing moves. `reclassify` treats a file in such a folder as already in place while it is in
the folder it belongs to (`Library.filed_under` accepts any depth below the target), and `reclassify` says how many
filed items sit below the depth (`core.reclassify.items_below_depth`, which counts them from the ledger). New
documents are filed at the new depth. A depth increase needs no special handling: the existing items sit one level
too high, and `reclassify` proposes moves into the new level as an ordinary job.

**The idea.** An explicit, opt-in way to bring those items up to the new depth: a `reclassify` mode (a flag, say
`--flatten`) that proposes moving each item out of the folders below the depth and into its target folder, as one
rollback-able job like any other `reclassify --apply`. It would be a preview first, and it would never run on its own.

**Why deferred.** `reclassify` already keeps an item that is still in the right folder, so flattening is a different
question from "is this filed correctly": it needs its own rules. A configuration edit that moved files by itself was
rejected, and so was a stored "previous depth" to detect the change; the ledger's paths already say what is deep.

### Questions to settle before building it

- What happens to the emptied folders: left alone, or removed with a `remove_folder` event so `rollback` recreates them
  (as `keep_folders = false` does for inbox folders)?
- Two items with the same name from different folders: both are headed for one destination. The shared
  `DestinationClaims` check would send the second to `conflict`; is that enough, or should the user choose?
- Bundles filed whole: do they move up as one unit (the likely answer), and what if the bundle's own folder is now
  below the depth?
- A folder the user made (not in the ledger): flatten it, skip it, or ask? The current rule is that
  `[exclusions]` is how the user keeps something out, which would apply here too.
- Does it belong on `reclassify`, or is it a separate command?

---

## Filing target mode (`file_at`)

**Status:** under review. It was Stage 4.9 of [mvp-build-plan.md](mvp-build-plan.md), an optional stage; on review it was
moved here on 2026-10-12 and the number is not reused. Nothing was built: there is no `file_at` setting in the code.

**Why it is under review.**
- It looks redundant. It only changes the outcome for a document whose group is clear but whose category is not, and
  such edge cases can be managed by filing them manually from the review queue.
- It may introduce false positives where a category or subcategory name is repeated under different groups (`01
  Requirements` in every project, say). The walk judges each level on its own confidence, and a name that exists
  under several groups is a weak basis for parking or later moving a document one level deeper. This has not been
  measured; it is the reviewer's concern and should be tested before any decision to build.

**The proposal.** A setting, `[sorting] file_at`, chooses where a document (or a folder, with `keep_folders` on) lands:

- `leaf_only`, the default and today's behaviour: file only into the deepest level, and only when every level is
  confident, otherwise send it to review.
- `best_level`: walk the levels from the top and file into the deepest level that is confident, so a document whose
  group is clear but whose category is not stays in the group folder instead of going to review.

It is meaningful from depth 2 and independent of [depth 3](#subcategories-depth-3).
At depth 1 the two modes are identical. `leaf_only` would stay the default, because filing nothing is safer than filing
into a level the user didn't expect.

**Names.** "Flat" and "recursive" were the first suggestions, but "flat" also reads as a depth-1 library and "recursive"
as scanning subfolders, so the setting would name where the file lands:

| Option | `[sorting] file_at` value | Meaning |
|---|---|---|
| Chosen | `leaf_only` / `best_level` | Names where the file ends up |
| Considered | `strict` / `progressive` | Describes attitude, not outcome |
| Considered | `exact` / `partial` | Suggests a match quality |
| Considered | `deepest_only` / `descending` | Close, but "descending" describes the walk, not the result |

### The design to keep

- **The walk.** The confidence at a level is the minimum of the levels down to it. Descend while a level resolves and that
  confidence reaches the threshold; file at the deepest level reached; if the top level fails, the unit goes to review.
  `Classifier` would do the walk, and `ClassificationResult` would record the level reached.
- **Folder units vote level by level.** The dominant group first, then the dominant category among the documents that
  voted for that group. A tie at a level stops the folder one level up, where `leaf_only` sends it to review.
- **Records.** The ledger and audit would record a unit filed above the leaf with the deeper fields empty, and the
  filer, ledger and `reclassify` would accept files directly inside a group (or category) folder.
- **`reclassify`.** A unit parked above the leaf stays (`keep`) while nothing deeper is confident, and is moved deeper
  once a deeper level is (a new hint, a new folder).
- **Display.** The `sort` summary would show the level reached, and `review` would need to show a unit that is not at
  the leaf.

### Questions to settle before building it

- Is it needed at all, given that the edge cases can be filed manually? Count how many documents it would park, on a real
  library and on the calibration corpus, and compare with the review queue it would shorten.
- Does repeating a category or subcategory name under several groups make parked documents land or move wrongly?
  Measure it with a corpus that repeats names (the calibration libraries do: `Bills` under every group in `household`).
- Does a document sitting in a group folder, outside any category, break the rest of the system (a flat count, the
  duplicate check's "folder this would be filed to", `Library.filed_under`)?
- Is the confidence rule (the minimum down to the level) the right one, and what does the user see for a parked unit?
- Tests it would need: fake resolvers for each combination of confident levels in both modes, folder-vote ties in each
  mode, `reclassify` for a parked unit, and the calibration report in both modes.


---

## Decision-model classifier

**Status:** under review. It was Stage 4.5 of [mvp-build-plan.md](mvp-build-plan.md); it was moved here on 2026-10-13
and the number is not reused. Nothing was built.

**Why it is under review.** It was gated on a measurement and has not been started, and the gate cannot be run from the
repository alone: the candidates (Jev, Clef, Nimble) came from an unverified web search, a model has to be run somewhere
to be measured (a GPU model locally, or a hosted account), and a hosted one sends document text off the machine. The
AI fallback is only asked where the rules are unsure, and the calibration already shows it adds little as built
([calibration.md](calibration.md)), so the expected gain for the first release is small. The research, with its sources
and the rules for adopting a model, is in [ai-classifier-options.md](ai-classifier-options.md).

**The proposal.** `sort --use-ai` could use either a chat model (as today) or a **decision model**, a classifier that
takes text and a fixed list of options and returns one option with a probability. Both would sit behind `Classifier` as
resolvers. The model's own probability would become the confidence instead of a flat `0.70`, and the calibration report
would show on the same corpus how each performs, so the choice is a measurement. It also shortens a path to ranked
suggestions for [`review`](mvp-build-plan.md#stage-5--review-workflow), which today offers only the classifier's best guess.

### The design to keep

- **A separate seam.** A `ChoiceModel` protocol, `choose(text, question, options) -> Choice`, with the chosen option or
  none, its probability and the ranked alternatives. It is separate from `AIProvider` because the two vary: one returns
  free text to be parsed, the other returns a bounded choice with a score.
- **A second resolver.** `ChoiceClassifier` beside `LLMClassifier`, with the taxonomy's names plus "none" as the options.
  `Classifier` still checks the answer against the taxonomy and applies the threshold. `run_sort`, the CLI's
  `_build_ai_classifier` and `SortReport.ai_unavailable` are typed to `LLMClassifier` today and would be generalised, and
  the "stop asking after the first failure" logic in `LLMClassifier._ask` would be shared, not copied.
- **A mapping from probability to confidence** (direct, or scaled and clamped) as a setting, since a model's
  probabilities are not automatically calibrated.
- **Config.** `[ai] kind = "chat" | "choice"` alongside `provider`, `model` and `endpoint`. One kind at a time.
- **Privacy.** A hosted model is treated like `OpenAIProvider`: chosen explicitly, the run says so, any key comes from an
  environment variable.
- **The adoption gate.** Adopt a decision model only if, on the calibration corpus, it is no less precise than the chat
  model at the same coverage and its probabilities separate right answers from wrong ones. If none passes, record that and
  stop.
- **Where it lives.** `ai/choice_classifier.py`, one backend (the best verified candidate) behind `build_provider`, with any
  new dependency in the `ai` extra, and saved decision-model answers in `tests/calibration/` as for the chat model's.

### Questions to settle before building it

- Can any candidate be run on a Windows machine without a GPU, and is it licensed for this use? Check each against its own
  documentation or model card (the summaries in `ai-classifier-options.md` are unverified).
- Is the gain worth a new dependency and a second AI setting, given how rarely the AI is asked?
- Tests it would need: a fake `ChoiceModel` (an option chosen, "none" chosen, an option outside the taxonomy treated as
  unresolved, a probability below the threshold going to review), the probability mapping and its bounds, a backend test
  against a mocked response (the suite uses no network and no model), and the calibration report with both kinds.
- Deferred with it: training a small classifier on the library's own ledger, chaining models, and downloading or managing
  model files for the user.

---

## Subcategories (depth 3)

**Status:** under review. It was Stage 4.7 of [mvp-build-plan.md](mvp-build-plan.md), provisional from the start; it was
moved here on 2026-10-13 and the number is not reused. Nothing was built: `depth` accepts 1 and 2.

**Why it is under review.** It is the largest change to the model, it was gated on a measurement that has not been run, and
depth 3 is not needed for the first release. Its prerequisites are built: [Stage 4.6](mvp-build-plan.md#stage-46--flat-libraries-depth-1)
made the category optional, and [Stage 4.8](mvp-build-plan.md#stage-48--non-library-folders) gave the rule for telling a
subcategory from a filed bundle (`Library.structure()` already skips folders the ledger records as filed whole). The
vocabulary, the limits and the depth model are in [library-depth.md](library-depth.md).

**The proposal.** With `depth = 3`, `sort` would classify group, then category, then subcategory, and file into the
subcategory folder. The ledger, `rollback` and `reclassify` would handle three levels, and the library creation functions
(`create_library_group` and any future template catalog or `init`) would create up to three.

### The design to keep

- **The go/no-go gate, with numbers.** Measure on the calibration corpus extended with a three-level library: how far
  auto-filing may fall and how far misfiling may rise, against the same documents at depth 2. If the gate fails, record the
  finding in `library-depth.md` and keep depth at 1 or 2.
- **Likely limits to watch.** The minimum-across-levels confidence sends more documents to review; the AI fallback costs one
  call per level (ask for a level only when the rules are unsure at it, so the common case is no more calls than at depth 2);
  `review` needs a choice at each level; and the ledger schema changes again.
- **The cap.** Library creation supports at most depth 3; depth 4 and above is not planned. Write the classifier to be
  level-generic so it is not a rewrite, but specify and test depth 3 only.
- **The model.** `Taxonomy` as a tree read to `depth`, and `Library.target_dir` taking the path of levels. One resolver step
  per level, taking the path so far and the level, in place of `resolve_group` and `resolve_category` (the adapters
  `RulesEngine` and `LLMClassifier` follow). The path's confidence is the minimum across levels, as now.
- **Records.** Ledger and audit fields for the subcategory (optional, or a list of levels), and the folder-unit vote on the
  full path. The library file reads hints and rules for level-3 nodes.
- **`review`.** One more prompt per level; `ReviewSession` and `cli/review.py` take a `depth` already.
- **Vocabulary.** *Subcategory* is the third level.

### Questions to settle before building it

- What are the gate's numbers, and is there a real library that needs three levels?
- Does a deeper path make `review` unusable (three lists to answer for every unit), and is there a better prompt?
- Tests it would need: a three-level fixture (`tests/mock_deep_library`) with end-to-end sort, rollback and reclassify, unit
  tests for the per-level step, the minimum-across-levels confidence and the AI being asked only where the rules could
  not answer, library creation making three levels and refusing four, and the calibration report on the three-level library.
- Docs it would touch: README, `how-to-use.md`, `architecture.md`, `data-model.md` and `CONTEXT.md` (add *subcategory*).
- Deferred with it: depth 4 and above.
