# RFC-006: Subcategories (depth 3)

Status: Draft

**Background:** under review. It was Stage 4.7 of the [MVP build plan](../plan/archive/2026-10-mvp/plan.md), provisional from the start; it was
moved to the feature backlog on 2026-10-13 and the number is not reused. Nothing was built: `depth` accepts 1 and 2.

**Why it is under review.** It is the largest change to the model, it was gated on a measurement that has not been run, and
depth 3 is not needed for the first release. Its prerequisites are built: [Stage 4.6](../plan/archive/2026-10-mvp/plan.md#stage-46--flat-libraries-depth-1)
made the category optional, and [Stage 4.8](../plan/archive/2026-10-mvp/plan.md#stage-48--non-library-folders) gave the rule for telling a
subcategory from a filed bundle (`Library.structure()` already skips folders the ledger records as filed whole). The
vocabulary, the limits and the depth model are in [library-depth.md](../architecture/library-depth.md).

**The proposal.** With `depth = 3`, `sort` would classify group, then category, then subcategory, and file into the
subcategory folder. The ledger, `rollback` and `reclassify` would handle three levels, and the library creation functions
(any future [`init` or template catalog](RFC-007-group-templates.md)) would create up to three.

## The design to keep

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

## Questions to settle before building it

- What are the gate's numbers, and is there a real library that needs three levels?
- Does a deeper path make `review` unusable (three lists to answer for every unit), and is there a better prompt?
- Tests it would need: a three-level fixture (`tests/mock_deep_library`) with end-to-end sort, rollback and reclassify, unit
  tests for the per-level step, the minimum-across-levels confidence and the AI being asked only where the rules could
  not answer, library creation making three levels and refusing four, and the calibration report on the three-level library.
- Docs it would touch: README, `how-to-use.md`, `architecture/overview.md`, `data-model.md` and `CONTEXT.md` (add *subcategory*).
- Deferred with it: depth 4 and above.
