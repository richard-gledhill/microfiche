# RFC-003: Opt-in flatten when the depth is reduced

Status: Draft

**Background:** to be reviewed for future implementation. Raised on 2026-10-12 while building
[Stage 4.8](../plan/archive/2026-10-mvp/plan.md#stage-48--non-library-folders); it needs specifying before it is planned.

**The situation.** A user reduces `[library_structure] depth` (from 2 to 1 today, and from 3 to 2 if
[depth 3](RFC-006-subcategories-depth-3.md) is ever built). The folders that were categories
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

## Questions to settle before building it

- What happens to the emptied folders: left alone, or removed with a `remove_folder` event so `rollback` recreates them
  (as `keep_folders = false` does for inbox folders)?
- Two items with the same name from different folders: both are headed for one destination. The shared
  `DestinationClaims` check would send the second to `conflict`; is that enough, or should the user choose?
- Bundles filed whole: do they move up as one unit (the likely answer), and what if the bundle's own folder is now
  below the depth?
- A folder the user made (not in the ledger): flatten it, skip it, or ask? The current rule is that
  `[exclusions]` is how the user keeps something out, which would apply here too.
- Does it belong on `reclassify`, or is it a separate command?
