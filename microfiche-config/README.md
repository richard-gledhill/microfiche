# Default library configuration

These are the default config files microfiche ships with. They are **not** read from here at
runtime — each library microfiche manages has its own `<library_root>/.microfiche-config/`
folder, read by `core.config.load_config`. Copy this folder there (renamed to
`.microfiche-config`) when setting up a new library — dot-prefixed so it's hidden from
Obsidian's file explorer by default.

A `microfiche init` command to automate that copy is a natural next step but isn't implemented
yet — see [docs/prd/20260907_microfiche_architecture_v2.md](../docs/prd/20260907_microfiche_architecture_v2.md).

| File | Purpose |
|---|---|
| `library_structure.yaml` | Depth of the group/category hierarchy (default: 2 levels). |
| `exclusions.yaml` | Folders never treated as a category and never scanned into. |
| `obsidian.yaml` | Turns Obsidian `index.md` generation on/off and sets tag governance mode. |
| `categories.yaml` | Keyword hints per *existing* category name — not the category list itself. |
| `filing_rules.yaml` | Filename-glob rules, checked before keyword hints. |
| `naming_rules.yaml` | Regex rename rules applied to filenames before filing (empty by default). |
| `library_templates.yaml` | Category sets for a future `create-library`/`init` command. |
