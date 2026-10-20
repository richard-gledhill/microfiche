# RFC-004: Filing target mode (`file_at`)

Status: Draft

**Background:** under review. It was Stage 4.9 of the [MVP build plan](../plan/archive/2026-10-mvp/plan.md), an optional stage; on review it was
moved to the feature backlog on 2026-10-12 and the number is not reused. Nothing was built: there is no `file_at` setting in the code.

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

It is meaningful from depth 2 and independent of [depth 3](RFC-006-subcategories-depth-3.md).
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

## The design to keep

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

## Questions to settle before building it

- Is it needed at all, given that the edge cases can be filed manually? Count how many documents it would park, on a real
  library and on the calibration corpus, and compare with the review queue it would shorten.
- Does repeating a category or subcategory name under several groups make parked documents land or move wrongly?
  Measure it with a corpus that repeats names (the calibration libraries do: `Bills` under every group in `household`).
- Does a document sitting in a group folder, outside any category, break the rest of the system (a flat count, the
  duplicate check's "folder this would be filed to", `Library.filed_under`)?
- Is the confidence rule (the minimum down to the level) the right one, and what does the user see for a parked unit?
- Tests it would need: fake resolvers for each combination of confident levels in both modes, folder-vote ties in each
  mode, `reclassify` for a parked unit, and the calibration report in both modes.
