# SPEC: `microfiche init`

Source: [library-init-prd.md](../requirements/library-init-prd.md) (Accepted, with the owner's decisions of
2026-10-20 under Decisions). This spec records only what is specific to `init`. Code style, module layout and test
naming follow [conventions.md](../conventions.md); the gates and the coverage floor are in
[constraints.md](../constraints.md); test levels and fixtures are in [testing/](../testing/README.md).

## Command

`microfiche init [--library PATH] [-v] [-q]`: the usual shared options, nothing of its own. It reads the state
folder and takes one of three paths. Every path ends the same way: create the inbox if it is missing, sync the
library file, print what was written.

| State | Terminal | No terminal |
|---|---|---|
| **No install** (no `microfiche-config.toml`) | Write the packaged defaults file verbatim, then the common ending. No prompts. | Same. |
| **Valid** | "Configuration is valid." Ask "Go through the settings? [y/N]". No: the common ending only. Yes: the walk-through, then the common ending. | Report valid, the common ending, exit 0. |
| **Invalid** | List every problem. Ask: revert the invalid and unknown settings only, revert all, or leave it (exit 1, nothing written). After writing, re-validate, then offer the walk-through. | List every problem, write nothing, exit 1 with "run `microfiche init` in a terminal to fix it". |

A partial install (a library file without a config) is the "No install" path; a config without a library file gets
one from the sync. Only the walk-through, the revert and the backup question prompt.

## Walk-through

1. The **common settings**, in this order: `classification.confidence_threshold`, `library_structure.depth`,
   `library_structure.library_inbox`, `sorting.keep_folders`, `ai.provider`, `ai.model`.
2. "Go through all the other settings? [y/N]". Yes: every remaining section in file order, each opened by
   "Change settings in [section]? [y/N]" so a section can be skipped; inside it, every remaining setting.
3. Each prompt shows the one-line explanation, the current value and, where different, the default. Enter keeps the
   current value. A bad value is explained and asked again.
4. A summary of the changes (`section.setting: old -> new`) and one "Write these changes? [y/N]". No changes: say so
   and write nothing (no backup), so Enter at every prompt leaves the file byte-identical.

Values are typed by the default's type: `bool` (y/yes/true/on or n/no/false/off), `int`, `float`, `str`, and
`list[str]` entered comma-separated (an empty answer to "clear it" is `-`). `naming_rules.rules` (a table of regex
rules) is shown but not edited: the prompt says to edit it in the file.

Validation of an entered value builds the candidate config (the file's current settings plus every change so far,
merged over the defaults) and validates it with `MicroficheConfig`; any problem located at that setting, or at its
section as a whole (such as `ai.host` with a non-Ollama provider), rejects the value.

The one-line explanation is the comment directly above the setting in the packaged defaults file. Every setting gets
one there (adding the missing ones for `library_inbox`, `depth`, `exclude` and `rules`), kept in step with the
`microfiche/` template, and a test checks that every setting has one.

## Revert (invalid config)

`ConfigError` gains `problems`, a tuple of `ConfigProblem(section, setting, kind, message)` where `kind` is
`"invalid"` (a bad value), `"unknown"` (a name that isn't a setting or section) or `"section"` (a section that is not
a table, or a section-level rule such as host-with-provider). The message text is unchanged.

- **Invalid and unknown only:** each invalid setting is set to its default; each unknown setting or section is removed;
  a section-level problem resets the settings the rule names (for the host rule, `host` to `""`). Valid custom
  settings, comments and layout elsewhere are kept. Settings missing from the file stay missing: they already take
  their default, and writing them in would rewrite the user's file for no change in behaviour. (This is how the spec
  reads the PRD's "invalid and missing".)
- **All:** the file is replaced with the packaged defaults verbatim.
- A file that is not valid TOML offers only **All** or leave it, since there is nothing to keep.

After either, the result is loaded with `load_config`; if it is still invalid (it should not be), nothing is
written and the remaining problems are shown.

## Writing

- `core` owns the file: a `tomlkit` document of the library's config, edited in place, so unchanged settings keep
  their comments and layout and a changed setting rewrites only its value. A setting absent from the file is
  appended to its section (the section created at the end of the file if absent).
- **Backup:** before rewriting an existing config, it is copied to `microfiche-config.toml.bak` beside it. If a
  backup already exists, `init` asks before replacing it; No writes nothing. The path is printed. A fresh install
  makes no backup.
- **Lock:** prompting holds no lock (as `review`). The write takes the run lock, re-reads the file and aborts with a
  message if it changed since it was read, then writes through a temporary file and a rename. Ctrl-C before the
  confirmation writes nothing.
- The inbox is created with `mkdir` under the same lock; the library file sync reuses
  `library_sync.sync_library_file`.
- **Invalid library file:** after the config is valid, if `microfiche-library.json` does not load, report why and,
  in a terminal, offer to rebuild it from the folders (moved aside to `microfiche-library.json.bak` first) or leave it
  (exit 1). Without a terminal, exit 1.

## Commands that now need a config

`sort`, `reclassify` and `propose-categories` check for `.microfiche/microfiche-config.toml` before anything else
(before the library is opened, the lock is taken or logging starts) and, if it is missing, print
"No configuration found in <library>/.microfiche. Run `microfiche init --library <library>` to set it up." and exit 1.
The check is in `cli` (`_open_library`'s callers); `load_config` still falls back to the defaults, so tests and the
calibration harness are unaffected. Every command that stops on a `ConfigError` adds "Run `microfiche init` to fix
it." (the PRD's "`config` suggests `init`").

## Module layout

| Module | What it holds |
|---|---|
| `core/config.py` | `ConfigProblem`, `ConfigError.problems`, the packaged defaults' text and path (public, for `init`). |
| `core/library_init.py` (new) | `inspect_install(library) -> InstallCheck` (state, problems); `install_defaults(library)`; `ConfigEditor` (load the `tomlkit` document, the list of `Setting`s with value, default and help, `set`/`check` a value, `revert_invalid`, `revert_all`, `changes`, `save` with backup); `create_inbox`. No prompts. |
| `cli/init_prompts.py` (new) | The prompts and their wording, as `cli/review.py` is for `review`. |
| `cli/commands.py` | `init` itself (registered in `app.py`), and the no-config check. |

`tomlkit` is added to `core`'s dependencies (owner approved, 2026-10-20).

## Tests

Test-first, through the interfaces above; `tests/core/test_library_init.py` and `tests/cli/test_cli_init.py`, with
prompts driven through `CliRunner(input=...)` and `stdin_is_terminal` patched as `test_cli_review.py` does. One test
per PRD acceptance criterion, plus: a value rejected and asked again; skipping a section; an existing `.bak`
declined writes nothing; a file changed during the prompts is not overwritten; not-TOML offers only "all"; no
terminal on an invalid config exits 1 untouched; the inbox is created; every default setting has a comment.

Pinned behaviour that changes: `test_sort_library_without_config_folder` (now exits 1 and names `init`) and any CLI
test that runs these three commands on a library without a config, which gains one. `test_load_config_missing_
files_fall_back_to_defaults` is unchanged.

## Docs

`docs/how-to-use.md` (both shell tabs: `init` replaces the manual copy step), the README Usage section,
`docs/cli-reference.md` (`make docs-cli`), `requirements/mvp-roadmap.md` (the "Ask before running on defaults" item),
`architecture/overview.md`, `microfiche/README.md` (no longer "not implemented"), CONTEXT.md if a term is added.
