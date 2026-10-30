# ADR-007: File into a group that has no category folders

- **Status:** Accepted
- **Date:** 2026-10-30
- **Decision:** A folder with no child folders is a leaf at whatever level it is. With the opt-in setting
  `[sorting] file_in_empty_groups` (default off), a unit whose group has no category folders is filed into the group
  itself instead of going to review. See [Decisions](#decisions).
- **Source:** [RFC-011](../rfcs/RFC-011-groups-without-categories.md)

## Context

At `depth = 2` a group with no category folders resolves, even at 1.0, but the category stage has nothing to match, so
overall confidence is 0 and the unit goes to review with its group match thrown away. Nothing is misfiled, but `review`
can only offer to plan a new category folder.

## Decisions

- **A leaf is a folder with no child folders**, defined per level: `Taxonomy.is_leaf` takes the path down from the
  library root, so RFC-006 (depth 3) reuses it. Only the group level is built now.
- **Setting, default off:** `[sorting] file_in_empty_groups = false`. A placeholder group made for categories to be added
  later keeps today's behaviour (the unit goes to review). Revisit the default after the calibration corpus has an empty
  group.
- **When on,** `Classifier.classify_document` sets `category = None` for a leaf group (as for a flat library) and takes
  confidence from the group alone; `ClassificationResult.folders` already returns `(group,)`, so `file_batch`,
  `reclassify`, the duplicate check and the ledger need no change. The AI category call is skipped. A folder unit's vote
  counts a leaf group as `(group, None)`.
- **`review`** offers the group as a destination when it is a leaf, as well as planning a category. `reclassify` treats a
  file in a leaf group classified as `(group,)` as `keep`.
- **The run says so**, once: `sort` and `review` report how many units went straight into a group for lack of categories.
- **Leaf groups take no hints or rules.** A leaf group is chosen by name (exact or fuzzy) only; library-file entries at
  depth 2 keep taking them on categories only.
- **`attachments` joins the default `[exclusions] exclude` list**, so a tool-made folder directly under a group is not
  taken for a category. A list a user wrote replaces the default, so this reaches new libraries only; the user guide says
  so. `config --sync` and `init` do not flag such names.
- **Files at group level in a group that has categories** are still proposed for a move by `reclassify`. Treating them as
  `keep` is a separate decision with a real cost (leftovers from an older `depth` would never be proposed), recorded as a
  limitation rather than changed here.
- **When a filed-into group gains its first category,** the files at group level are one level too high. `reclassify`
  proposes moves for them, as after a depth change; the user guide says so. No extra run message.
- **No ledger or audit change.** `category = None` already records that the group was the destination.

## Alternatives considered

- Always on: simplest, but a placeholder group would start receiving files on the next sort.
- General `file_at = best_level` ([RFC-004](../rfcs/RFC-004-filing-target-mode.md)): it parks documents one level up when
  a category is merely unsure; this rule applies only when there is no category to be unsure about.
- Hints and rules on leaf groups: a model and validation change at depth 2 for a case no one has asked for.

## Consequences

- With the setting on, units that named an empty group file instead of waiting in review.
- A new setting to document: packaged defaults, example config, how-to-use, README and the generated CLI reference.
- New libraries stop treating `attachments` as a category; existing ones keep whatever their `exclude` list says.
