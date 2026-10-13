# Library depth and non-library folders

A review of how many levels a library may have, how microfiche tells a library folder from a folder that is just
content, and where a document may land when only some levels are confident. It feeds Stages
[4.6](mvp-build-plan.md#stage-46--flat-libraries-depth-1) to
[4.8](mvp-build-plan.md#stage-48--non-library-folders) of the build plan. Depth 1 (Stage 4.6) and non-library folders (Stage 4.8) are built; depth 3 is in the
[feature backlog](feature-backlog.md#subcategories-depth-3), under review.
The filing target mode it once covered is in the [feature backlog](feature-backlog.md#filing-target-mode-file_at),
under review.

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

Depth 3 is in the [feature backlog](feature-backlog.md#subcategories-depth-3), under review (it was Stage 4.7). If
implementing it hits a practical limitation, the finding is recorded here and depth stays 1 or 2. Limits to watch:

- **Confidence falls with every level.** The path's confidence is the minimum across levels, so a third level can
  only send more documents to review.
- **AI cost grows with depth.** One call per level; the plan asks the AI about a level only when the rules are
  unsure at that level.
- **`review` gains a choice per level**, which Stage 5 has to be designed for.
- **The ledger schema changes again**, and so does every place that says "group and category".
- **Library creation is capped at three levels.** Any later template catalog or `init` (see the
  [feature backlog](feature-backlog.md#library-creation-init-and-group-templates)) makes at most three levels. The classifier is written level-generic so depth 4 is not a rewrite, but
  only depth 3 is specified and tested, and depth 4 and above is not planned.

The go/no-go numbers would be set in the backlog entry, against a three-level library added to the calibration corpus.

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

Reducing `depth` (2 to 1 now, 3 to 2 if depth 3 is ever built) turns the old category folders into plain folders inside
their group. Nothing moves: `filed_under` accepts any depth below the target, so `reclassify` keeps an item that is
still in the folder it belongs to, and it says how many filed items now sit below the depth (counted from the ledger's
paths, with no stored "previous depth"). Considered and rejected: moving everything automatically when the config
changes (a configuration edit should not move files, and the change cannot be detected without more state).
Considered and deferred: an explicit, opt-in flatten, recorded in
[feature-backlog.md](feature-backlog.md#opt-in-flatten-when-the-depth-is-reduced) to be reviewed. Increasing the depth
needs nothing special: the existing items sit one level too high and `reclassify` proposes moves into the new level.

## Filing target mode

Moved to the [feature backlog](feature-backlog.md#filing-target-mode-file_at), where it is under review. It was to
be an optional `[sorting] file_at` setting (`leaf_only`, today's behaviour, or `best_level`, which files at the deepest
confident level); the proposal, the names considered and the rules are kept there.

## Order of the work

4.6 first (before Stage 5), then 4.8, which depth 3 would need for telling a subcategory from a filed bundle. Depth 3
(4.7) and the filing target mode (4.9) are in the backlog; the numbering follows the order the stages were proposed, and
the numbers 4.5, 4.7 and 4.9 are not reused.
