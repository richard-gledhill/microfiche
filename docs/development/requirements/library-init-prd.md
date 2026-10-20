# `init`: set up, check and edit a library's configuration

Status: Done

- **Id:** `library-init` ([capability map](post-mvp-capability-map.md), #1)
- **Depends on:** nothing

## Why

Setting up a library today means copying the `microfiche/` template folder into the library as `.microfiche/` by hand
([how-to-use.md](../../how-to-use.md)). It is the first thing every new user does, and the easiest to get wrong.
Getting it wrong is silent: a missing or misnamed config file, or a wrong `--library` path, falls back to the packaged
defaults, so a run looks normal while using settings the user never chose. And once a config exists, changing it means
editing TOML by hand, and a mistake is only found when the next command refuses to start.

`init` becomes the one place to set up a library, check its configuration and change it, with no flags to learn.

## User stories

- As a new user, I want one command that sets up my library, so I can run `sort` straight away.
- As an existing user, I want to run the same command to check my configuration and change settings one at a time,
  without editing TOML.
- As a user whose configuration is broken, I want to be offered a way back to working defaults, without losing the
  settings that were fine.

## Behaviour

`microfiche init` takes no flags of its own (the usual `--library PATH` chooses the library). It looks at the library's
`.microfiche/` and does one of three things:

| What it finds | What it does |
|---|---|
| **No install**: no `.microfiche/microfiche-config.toml` | Writes the packaged default config and creates `microfiche-library.json` from the folders that exist (the library file sync). No prompts. Prints what it wrote. |
| **A valid config** | Says it is valid and asks whether to go through the settings; No ends `init` there (after the library file sync). Otherwise walks through the settings section by section, showing each current value (and the default, where different), and asks whether to change it. Enter keeps the current value. Writes once, at the end, after a summary of the changes and one confirmation. Then syncs the library file. |
| **An invalid config** | Lists every problem (as `config` does today), then asks whether to revert **only the invalid and missing settings** to their defaults, keeping everything else, or **all settings**. Writes the result, checks it is now valid, then syncs the library file. Offers the settings walk-through afterwards. |

## Requirements

**Must**
- Behave as in the table above, with no flags.
- Walk through the commonly changed settings first (`confidence_threshold`, `depth`, `library_inbox`,
  `keep_folders`, AI `provider` and `model`), then ask once whether to go through all the others, section by section.
- Never create, move or delete the user's folders or documents. The one folder `init` may create is the inbox
  (`_sorting/`, or the configured name), when it is missing: it is microfiche's own.
- Never lose the user's settings silently: before rewriting an existing config, keep a copy of it beside it (for example
  `microfiche-config.toml.bak`, replacing any older copy only after asking), and say where it is.
- Keep the user's comments and layout in the config file where a setting is unchanged.
- Validate every value as it is entered (type and range, as `load_config` does), and ask again on a bad value.
- A partial install (a config but no library file, or the reverse) is completed, not reported as an error.
- Take the run lock while writing, like `config --sync`. Ctrl-C before the final confirmation writes nothing.
- `sort`, `reclassify` and `propose-categories` no longer run silently on defaults: with no config, they say so, tell
  the user to run `microfiche init`, and exit non-zero without writing anything.
- Prompts need a terminal. Without one, a fresh install still works (it asks nothing); an existing install is checked
  and reported, and `init` exits non-zero if anything would need a prompt.

**Should**
- Let the user skip a whole section in the walk-through.
- Explain each setting in one line as it is asked, taken from the same text as the config template's comments.
- If `microfiche-library.json` is invalid, report it and offer to rebuild it from the folders (keeping a copy), or to
  leave it for the user to fix.
- `config` (read-only) suggests `init` when it finds a problem.

**Won't (this time)**
- Named group templates or a template catalog ([backlog](../rfcs/RFC-007-group-templates.md)).
  A fresh install uses the one shipped template.
- Editing hints and filename rules interactively; they stay in the library file.
- Flags such as `--yes` or `--depth`. Depth is a setting, changed in the walk-through like any other.

## Acceptance criteria

- On a folder with no `.microfiche/`, `init` writes the default config and a library file listing the folders, asks
  nothing, and a following `sort --dry-run` runs without a warning.
- On a valid install, pressing Enter at every prompt leaves the config byte-identical and writes no backup.
- Changing one setting rewrites only that line (comments kept), writes a backup, and `config` shows the new value.
- On an invalid config, "invalid and missing only" fixes those settings and keeps a valid custom setting elsewhere;
  "all" restores the packaged defaults; either way the result loads and the backup holds the original.
- `sort` on a folder with no config exits non-zero, writes nothing (no lock, no `.microfiche/`), and names `init`.
- `docs/how-to-use.md` (both shell tabs), the README Usage section and `docs/cli-reference.md` describe `init`; the
  manual copy step is removed.
- `make check` and `make test` pass.

## Technical outline

Guidance for the spec, not binding.

- The defaults are packaged (`core/defaults/microfiche-config.toml`), and `load_config` already validates the whole file
  in one pass and names every problem. Expose those problems as data (section, setting, kind) so `init` can revert just
  those.
- Preserving comments needs a round-trip TOML library such as `tomlkit` (`tomllib` only reads). That is a new
  dependency: ask first.
- The library file part reuses `library_sync.sync_library_file`, which writes through a temporary file and a rename.
- Prompts live in `cli` (as `review`'s do in `cli/review.py`); `core` provides the check, the defaults and the write.
- Changing "missing config means defaults" changes pinned behaviour
  (`test_load_config_missing_files_fall_back_to_defaults` and the CLI test for a library with no config folder). The
  change is in the CLI's entry check, not in `load_config`, so tests and the calibration harness can still load
  defaults.

## Related

- [mvp-roadmap.md](mvp-roadmap.md#future-work): "Ask before running on defaults", which this absorbs.
- [mvp-followups-prd.md](mvp-followups-prd.md) D1 (`init` and a template catalog).

## Decisions

Settled with the owner on 2026-10-20, replacing the open questions.

- **Walk-through scope:** the common settings first, then one choice to go through every other setting, section by
  section (each section can be skipped).
- **Inbox:** `init` creates the inbox folder if it is missing.
- **`config --sync`:** kept, as the non-interactive way to sync the library file; `init` syncs it too.
- **Fresh install:** writes the packaged defaults file (`core/defaults/microfiche-config.toml`) as it is.
- **Valid config:** `init` first asks whether to go through the settings at all, so it can end there.
- **`tomlkit`:** added to `core` as a runtime dependency, to keep comments and layout when rewriting the config.
