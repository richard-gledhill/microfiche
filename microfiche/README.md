# Default library configuration

These are the default config files microfiche ships with. They are **not** read from here at
runtime — each library microfiche manages has its own `<library_root>/.microfiche/`
folder, read by `core.config.load_config`. Copy this folder there (renamed to
`.microfiche`) when setting up a new library — dot-prefixed so it's hidden from
Obsidian's file explorer by default.

A `microfiche init` command to automate that copy is a natural next step but isn't implemented
yet — see [docs/development/architecture.md](../docs/development/architecture.md).

| Section | Purpose |
|---|---|
| `library_structure` | Depth of the group/category hierarchy (default: 2 levels), and `library_inbox`, the inbox folder name (default `"_sorting"`). |
| `sorting` | `keep_folders` (default `true`): file a folder dropped in the inbox whole, under its dominant category, or leave it alone. `sort --keep-folders-off` and `--keep-folders` override it for one run. |
| `exclusions` | Folders never treated as a category and never scanned into. |
| `category_hints` | Keyword hints per *existing* category name, under `[category_hints.categories]` — not the category list itself. |
| `filing_rules` | Filename-glob rules, checked before keyword hints. |
| `naming_rules` | Regex rename rules applied to filenames before filing (empty by default). |
| `library_templates` | Category sets for a future `create-library`/`init` command. |
| `obsidian` | Turns Obsidian `index.md` generation on/off and sets tag governance mode. |

A section or setting that isn't listed here is an error rather than being ignored, so a typo such as
`[classifcation]` is caught instead of silently leaving the defaults in place.
