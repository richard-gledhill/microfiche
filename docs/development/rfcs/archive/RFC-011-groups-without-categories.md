# RFC-011: Groups with no category folders

Status: Accepted

Decided on 2026-10-30 and recorded in [ADR-007](../../adr/ADR-007-leaf-groups.md); the questions below were settled there.

**Background:** raised on 2026-10-25 from a question about what `sort` does at depth 2 when a group has no category
folders yet, and a very confident group match. Nothing built. Found by reading the code; not run.

**What happens now.** At `depth = 2` every document needs a group *and* a category (`Classifier.classify_document`):

1. `Library.taxonomy()` gives a group with no category folders an empty list. `Taxonomy.is_flat` is false, so the
   empty list means "a group with nowhere to file into", which is what `Taxonomy`'s docstring says it is for.
2. The group resolves, even at confidence 1.0. The category stage runs against an empty list and returns
   `name=None` ("No category keyword or name matched"). `_known_category` would reject any answer from the AI too.
3. Overall confidence is the minimum of the two stages (`combine_confidence`), so it is 0 and `confident` is false.
4. The unit goes to `needs_review`. Nothing is filed and nothing is misfiled, but the group match is thrown away and
   `review` can only offer to plan a new category folder (`ReviewSession.folder_problem`); it cannot file straight into
   the group.

It is probably worse with `--use-ai`: the category stage falls back to the AI because the rules had no answer, for a
list of categories that is empty. Not verified in `ai/llm_classifier.py`.

Depth 3 does not exist yet ([RFC-006](../RFC-006-subcategories-depth-3.md)); the same gap applies to a category with no
subcategory folders when it is built. Depth 1 is unaffected: the group is the destination.

This is documented behaviour, not a defect in the sense of a crash: `docs/development/architecture/overview.md` says
loose files and kept-whole folders are filed "at the leaf", and `library-depth.md` defines the vocabulary. What is not
written down is the case where the leaf is above the configured depth.

## Relation to RFC-004

[RFC-004 (`file_at = best_level`)](../RFC-004-filing-target-mode.md) is the general form: file into the deepest level that
is confident. It is under review because of a real concern, that a category name repeated across groups (`01
Requirements`) makes a "confident" category a weak basis for parking a document one level up.

This RFC is the narrow case where that concern does not arise. When a group has no category folders at all, there is no
category to be unsure about and no repeated name: the only possible destination is the group folder. So it could be
built first, on its own, without deciding RFC-004. If RFC-004 is built later, this rule is its special case.

## Related behaviour: what sits directly in a group folder

Reproduced on 2026-10-25 in a scratch depth-2 library (`Project Alpha/Requirements/`, `Project Alpha/attachments/`,
loose files directly in `Project Alpha/` and in a `Finance/` group with no categories). It started as a report that
files saved at group level appear as children in `microfiche-library.json`. They do not, but two neighbouring
behaviours are easy to mistake for it:

- **A loose file in a group is not in the library file.** `Library._folders_in` keeps directories only, and
  `test_structure_skips_files` pins it. `init`, `config --sync` and the first `sort` list folders, never files.
- **A folder in a group is a category.** `Project Alpha/attachments/` and a hand-made `Project Alpha/some-pack/` were
  both added to the library file as categories, and become filing targets. This is the stated rule (a folder within
  the depth is a filing target unless an exclusion pattern names it), but `attachments` is a common name (Obsidian
  creates it) and is not in the default `exclude` list, so a user sees folders they never meant as categories. The
  user guide only warns about a folder *inside a category*.
- **`reclassify` moves a loose group-level file into a category.** `filed_under` is false for a file that is in the
  group folder but not in the category folder, so `Project Alpha/loose-note.md` was proposed for a `move` into
  `Requirements` (0.90). A file the user saved at group level on purpose is treated as misplaced. In the `Finance`
  group, which had no categories, the loose files were left for `review`.
- **A group with no categories sent a unit to review.** The same library: an inbox file naming `Finance` went to
  `needs_review` with "No category keyword or name matched". This is the case the proposal below fixes.

Whether to change the first three is a decision, not a defect; they are recorded here and in the user guide's
limitations so they are not rediscovered.

## Proposal

A folder with no child folders is a leaf at whatever level it is, even above the configured depth.

- Add `Taxonomy.is_leaf(group) -> bool`: true if the library is flat or the group has no categories.
  `is_flat` stays as it is for the library-wide case.
- `Classifier.classify_document`: for a leaf group, set `category = None` (as for a flat library) and take the
  confidence from the group alone. `ClassificationResult.folders` already returns `(group,)` for that, so
  `filer.file_batch`, `reclassify`, the duplicate check and the ledger (category is optional there) need no change.
- Skip the AI category call for a leaf group.
- A folder unit's vote counts a leaf group as `(group, None)`, as a flat library does.
- `review`: when the chosen group is a leaf, offer to file into the group as well as to plan a category.
- `reclassify`: a file in a leaf group whose classification is `(group,)` is `keep` (`filed_under` already accepts the
  group folder itself).
- `sort` and `review` say, once, how many units were filed straight into a group because it has no categories, so the
  rule is visible.

## Questions to settle before building it

- Always on, or a setting (`[sorting] file_in_empty_groups`, default off)? Always on is simplest, but a user who makes an
  empty group as a placeholder for categories they will add later would start receiving files in it, and the first
  `sort` after the placeholder is made decides. A setting defaults to today's behaviour. If it is a setting, the
  default should probably be off until measured on the calibration corpus.
- When the group later gains its first category folder, the files already in the group sit one level too high.
  `reclassify` proposes moves for them (the same as after the depth is raised, see `library-depth.md`). Is that enough,
  or should the run say so?
- A group-level file that the user saved on purpose, in a group that *does* have categories, is still proposed for a
  move by `reclassify` (`filed_under` is false for the category). Related to this RFC, and a separate decision: treat a
  file directly in a group folder as `keep`? The cost is that a document `sort` filed there by mistake, or left there
  by an older `depth`, would no longer be proposed for a move.
- Add `attachments` (and similar tool-made folders) to the default `[exclusions] exclude` list, or only document it?
  A list the user writes replaces the default, so a changed default reaches new libraries only.
- Should `config --sync` and `init` say which folders directly under a group were added as categories, so a folder the
  user did not mean as one is noticed? They already print each addition; the question is whether to flag a name such
  as `attachments`.
- Library-file entries at depth 2 take hints and rules on categories only (a group's hints are for depth 1). Should a
  leaf group's entry take them, so a filename rule or hint can choose it, or is name and fuzzy matching enough?
  Without them a leaf group can only be chosen by its name.
- Depth 3: is the rule the same for a category with no subcategory folders? It should be written level-generically so
  RFC-006 does not redo it.
- Does the ledger or audit log need to record that the group was a leaf? Probably not: `category = None` already says
  so, as for a flat library.

## Tests and docs it would need

- `Taxonomy.is_leaf`: flat, group with categories, group without.
- `Classifier`: a group with no categories and a confident group match is `confident` with `folders == (group,)`;
  with a fake fallback resolver, the category stage is not asked.
- `run_sort` end to end: a library with one empty group and one group with categories; a unit for each goes to the right
  place, and the empty group's unit is no longer in `needs_review`.
- `ReviewSession`: offering the group as a destination when it has no categories; not when it has.
- `reclassify`: `keep` for a file already in the leaf group; `move` after the group gains a category.
- Docs: `docs/development/architecture/overview.md` and `library-depth.md` (the leaf rule), `docs/how-to-use.md` (both
  tabs, plus Current limitations), the README, `mvp-roadmap.md`, and CONTEXT.md if "leaf" becomes a term.
- Calibration: add an empty group to the corpus before choosing the default.
