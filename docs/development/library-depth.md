# Library depth and non-library folders

A review of how many levels a library may have, how microfiche tells a library folder from a folder that is just
content, and where a document may land when only some levels are confident. It feeds Stages
[4.6](mvp-build-plan.md#stage-46--flat-libraries-depth-1) to
[4.9](mvp-build-plan.md#stage-49--filing-target-mode-optional) of the build plan. Depth 1 (Stage 4.6) is built; the rest is not.

## Where depth 2 was built in

| Part | What assumes two levels |
|---|---|
| `Taxonomy` | `groups: dict[str, list[str]]`; `Library.taxonomy()` walks exactly two levels (since Stage 4.6 it also carries `depth`, and reads one level at depth 1) |
| `Classifier` and `Resolver` | Two stages, `resolve_group` then `resolve_category` |
| Matching | Hints are keyed by category name; filing rules name a category; the AI prompts are group and category prompts |
| Filing | `Library.target_dir(group, category)` |
| Records | The ledger and audit events store `group` and `category` |
| Voting and reclassify | The folder vote and `reclassify`'s `keep` check key on a `(group, category)` pair |

The ledger fields are persisted, so a change later is a schema change, and Stage 5 builds `review` on
the same shape. That is why depth 1 is planned before Stage 5.

## Vocabulary

The word *group* is used at every depth, so naming stays consistent as depth grows:

| Depth | Levels | Files land in |
|---|---|---|
| 1 | group | the group folder |
| 2 | group, category | the category folder |
| 3 | group, category, subcategory | the subcategory folder |

A flat library therefore has groups and no categories. At depth 1 the group is the only thing to match on, so
level-1 nodes in `microfiche-library.json` take `hints` and `rules`, which a depth-2 library only needs on its
categories.

## Depth 3 and the limits on it

Stage 4.7 is provisional. If implementing it hits a practical limitation, it is deferred, the finding is
recorded here, and depth stays 1 or 2. Limits to watch:

- **Confidence falls with every level.** The path's confidence is the minimum across levels, so a third level can
  only send more documents to review.
- **AI cost grows with depth.** One call per level; the plan asks the AI about a level only when the rules are
  unsure at that level.
- **`review` gains a choice per level**, which Stage 5 has to be designed for.
- **The ledger schema changes again**, and so does every place that says "group and category".
- **Library creation is capped at three levels.** `create_library_group` and any later template catalog or
  `init` make at most three levels. The classifier is written level-generic so depth 4 is not a rewrite, but
  only depth 3 is specified and tested, and depth 4 and above is not planned.

The go/no-go numbers are set in Stage 4.7's Plan, against a three-level library added to the calibration corpus.

## Non-library folders

A *non-library folder* is any folder inside the library that is not a group, category or subcategory. There are
two kinds: a folder microfiche filed as content (a bundle filed whole by `keep_folders`, such as
`Project Phoenix/02 Architecture/phoenix-weekly-pack/`), and a folder the user made (`attachments/`, `old/`).

What goes wrong without a rule:

- **`reclassify` splits a bundle.** It walks every file under the library and classifies each one, so the
  documents of a filed bundle are proposed separately. Today's code has no check for this.
- **At depth 3 the bundle becomes a subcategory.** The taxonomy walk would read it as one.
- **`propose-categories`** has to treat the folder as content, and so would any future integration that writes into
  category folders (the Obsidian `index.md` notes, see [feature-backlog.md](feature-backlog.md)).

Today the taxonomy walk stops at level 2, so at depth 2 the taxonomy itself is not affected.

The principle (settled when Stage 4.8 was built): *a folder within the depth is a filing target unless a rule
excludes it; a folder beyond the depth is content.* Signals, in the order they apply:

1. **The existing exclusion patterns** (`.*`, `_*` and any the user adds), matched on every path component. This is
   how a user skips a folder "tagged" a certain way, such as `[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_*` for
   `yyyymmdd_` folders. It is a deny-list and applies at every level, and to files too.
2. **The ledger.** A path recorded as a filed folder unit is content: `reclassify` treats it as one unit, and
   `Library.structure()` never reads it as a group, category or subcategory. This is exact for what microfiche filed.

An allow-list `name_pattern` per level in `microfiche-library.json` (the whole folder name must match, for example
`^\d{2} .+` for numbered categories) was proposed and dropped: it changes the schema and couples the taxonomy walk to
the library file, and the deny-list covers the need. It could return if a convention-following library asks for it.

A folder the user made below a category, and the ledger does not know about, is not a filing target and not skipped: its
files are read one by one, as they always were. To keep it out, exclude it. Folders moved by hand are not recognised
by the ledger; that is deferred.

### When the depth is reduced

Reducing `depth` (2 to 1 now, 3 to 2 if Stage 4.7 is built) turns the old category folders into plain folders inside
their group. Nothing moves: `filed_under` accepts any depth below the target, so `reclassify` keeps an item that is
still in the folder it belongs to, and it says how many filed items now sit below the depth (counted from the ledger's
paths, with no stored "previous depth"). Considered and rejected: moving everything automatically when the config
changes (a configuration edit should not move files, and the change cannot be detected without more state).
Considered and deferred: an explicit, opt-in flatten, recorded in
[feature-backlog.md](feature-backlog.md#opt-in-flatten-when-the-depth-is-reduced) to be reviewed. Increasing the depth
needs nothing special: the existing items sit one level too high and `reclassify` proposes moves into the new level.

## Filing target mode

This is the optional Stage 4.9. Two behaviours were proposed:

- Only the deepest folder: the document (or folder, with `keep_folders`) is filed only when every level is
  confident, and otherwise goes to review. This is today's behaviour.
- Level by level: starting at the top level, the document is filed into the deepest level that is confident.

"Flat" and "recursive" were the first names. "Flat" also reads as a depth-1 library, and "recursive" as scanning
subfolders, so the setting names where the file lands instead:

| Option | `[sorting] file_at` value | Meaning |
|---|---|---|
| Chosen | `leaf_only` / `best_level` | Names where the file ends up |
| Considered | `strict` / `progressive` | Describes attitude, not outcome |
| Considered | `exact` / `partial` | Suggests a match quality |
| Considered | `deepest_only` / `descending` | Close, but "descending" describes the walk, not the result |

`best_level` rules:

- The confidence at a level is the minimum of the levels down to it. Descend while a level resolves and that
  confidence reaches the threshold. File at the deepest level reached. If the top level fails, the unit goes to
  review.
- A folder's documents vote level by level: the dominant group first, then the dominant category among the
  documents that voted for that group. A tie at a level stops the folder one level up, where `leaf_only` sends
  it to review.
- A unit parked above the leaf is not stuck: `reclassify` keeps it while nothing deeper is confident and moves it
  deeper once a deeper level is (a new hint, a new folder).
- At depth 1 the two modes are identical, so the setting matters from depth 2. It is independent of Stage 4.7.

`leaf_only` stays the default, because filing nothing is safer than filing into a level the user didn't expect.

## Order of the work

4.6 first (before Stage 5), then 4.8, because 4.7 needs its rule for telling a subcategory from a filed bundle,
then 4.9 (optional, works at depth 2), then 4.7 (provisional). The numbering follows the order the stages were
proposed; renumber if the build order should show in the labels.
