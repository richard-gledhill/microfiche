# Default library configuration

These are example config files for a library. They are **not** read from here at
runtime — each library microfiche manages has its own `<library_root>/.microfiche/`
folder, read by `microfiche.core.config.load_config`. `microfiche init --library <library>`
sets that folder up, writing the packaged defaults (`core/defaults/microfiche-config.toml`, which lists the same
settings as the config here); run it again to check the config or change its settings one by one.

The config here has the same settings and values as what `init` writes, with longer comments. The library file here
has example hints for five document-type categories; `init` writes one listing your own folders instead. Copy either
into a library's `.microfiche/` if you want them.

| Section | Purpose |
|---|---|
| `library_structure` | Depth of the group/category hierarchy (default: 2 levels), and `library_inbox`, the inbox folder name (default `"_sorting"`). |
| `sorting` | `keep_folders` (default `true`): file a folder dropped in the inbox whole, under its dominant category, or file its documents one by one and remove the folder once it is empty. `sort --keep-folders-off` and `--keep-folders` override it for one run. `ignore` (default `~$*`, `.DS_Store`, `Thumbs.db`, `*.tmp`): file and folder names the inbox scan skips without comment. |
| `parsing` | `max_file_mb` (default 50): a file bigger than this is not read; it stays in the inbox for review, with the reason. |
| `logging` | The diagnostic log, separate from the audit log. `level` (default `INFO`): how much the log file records. `file` (default `microfiche.log`): its name, kept in `.microfiche/`. `max_bytes` (default 1048576) and `backup_count` (default 3): when the file is rotated and how many backups are kept. |
| `classification` | `confidence_threshold` (default 0.75): how sure microfiche must be to file without review. `name_match_confidence` (0.9), `filename_match_confidence` (0.95) and `hint_match_confidence` (0.75): how sure each kind of match is. `fuzzy_group_threshold` (0–100, default 85): how close a near-miss must be to a group's name. |
| `ai` | `provider` (`"ollama"` or `"openai"`), `model`, `host`, `timeout` and `api_key_env` (the name of the variable holding the OpenAI key). `ai_confidence` (0–1, default 0.70): how sure any AI-fallback answer is. `max_document_chars` (default 4000; `0` = all of it, with a warning): how much of a document's text is sent. |
| `exclusions` | Folders never treated as a group or category and never scanned into: names or globs, matched at any level. The list in this file is `sorting*`, `_sorting*`, `.*`, `_*`; a list you write replaces it, so keep those and add yours. |
| `naming_rules` | Regex rename rules applied to filenames before filing, as `rules = { 'pattern' = "replacement" }`, in order, to the whole name (empty by default). See [Renaming on the way in](https://richard-gledhill.github.io/microfiche/how-to-use/#renaming-on-the-way-in). |

Keyword hints and filename rules are not in the config. They live in `microfiche-library.json` beside it,
a tree of folder names with `hints` and `rules` (see the file here, and `microfiche-library.schema.json`
for editor completion). A `*` entry applies to every group, and a named group adds to it for that group
only. The folders in the library decide what exists; this file only helps match them.

A section or setting that isn't listed here is an error rather than being ignored, so a typo such as
`[classifcation]` is caught instead of silently leaving the defaults in place.
