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
| `library_structure` | Depth of the group/category hierarchy (default: 2 levels). |
| `exclusions` | Folders never treated as a category and never scanned into. |
| `microfiche-library.json` | Keyword hints and filename rules per folder, in a separate file — not the category list itself. |
| `naming_rules` | Regex rename rules applied to filenames before filing (empty by default). |
