# RFC-007: Library creation (`init`) and group templates

Status: Draft

**Background:** removed from the MVP on 2026-10-14, by the Stage 6 simplification review. The code worked but nothing called it:
there is no command that creates a library or a group, so `create_library_group` and `validate_library_root` were unused and
had no tests. No user-visible behaviour was lost.
**Partly picked up:** `init` itself was built from [library-init-prd.md](../requirements/library-init-prd.md), feature 1 of
the post-MVP updates: it writes the packaged default config and edits an existing one. Group templates stay in this RFC.

**Why deferred.** microfiche reads a library that already exists; the user makes the folders, and `review` can plan a new
group or category folder. A command that creates a library, or a group from a named template, is a feature of its own that
needs a catalog of templates to be worth having.

## What was removed, and where to get it back

| What | File | Restore with |
|---|---|---|
| `create_library_group(library_root, project_name, template_categories)`: makes a group folder with one sub-folder per category | `packages/core/src/microfiche/core/library/templates.py` | `git show 99c79a4:packages/core/src/microfiche/core/library/templates.py` (the last commit before the removal) |
| `validate_library_root(path)`: raises if a path is not an existing folder | `packages/core/src/microfiche/core/utils/validation.py` | `git show 99c79a4:packages/core/src/microfiche/core/utils/validation.py` |

Both are small enough to rewrite from the table, and the first should be rewritten against the library file's node shape
(`{name, children}`) rather than restored as it was.

## The design to keep

- A template is a tree of folder names in the library file's own node shape, so one format describes a library, a template
  and a taxonomy ([ADR-001](../adr/ADR-001-configuration-layout.md) section 6 has the reasoning).
- Creation is explicit and never happens during `sort`: the folders are the authority, and only a command the user runs may
  make them.
- At depth 3 ([subcategories](RFC-006-subcategories-depth-3.md)) creation makes up to three levels, and depth 4 and above is not planned.

## Questions to settle before building it

- Is there a real need for named templates, or is copying a folder enough?
- Tests it would need: creation under an existing and a missing root, a name that clashes with a file, and a refusal to
  overwrite a folder that already exists.
