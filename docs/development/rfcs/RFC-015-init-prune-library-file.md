# RFC-015: `init` prunes stale folders from the library file

Status: Draft

**Background:** split from [RFC-014](RFC-014-filing-overhaul.md). Stale entries in `microfiche-library.json` can shadow
the real folders and mislead matching, which is one thing RFC-014's parsing check looks for.

## `init` should prune stale folders from the library file

**Today.** Re-running `init` (the library sync, `library/library_sync.py::sync_library_file`) adds entries for new
folders but only *warns* about entries whose folder has gone: `LibrarySync.missing` entries "are kept in the file", and
`possible_renames` is advisory. Stale entries accumulate, can mislead matching and hide renames.

**Proposal.** Default to updating the file to match the folders on disk, with a clear warning, and let the user opt out:

- Removed folders' entries are dropped from `microfiche-library.json` by default, and the run lists each removed entry
  (with its hints) so the user sees what went.
- Opt-out: a flag (e.g. `init --keep-missing`) and/or a setting, so a user whose folder is temporarily absent (offline
  drive, renamed in progress) loses nothing.
- Safety: back up the file before pruning (as `config` already does with a backup path), and print a restore hint.
  Hints and filename rules are user-written content, so the backup is not optional.
- Renames: when `possible_renames` finds exactly one pair, offer to carry the hints over to the new name instead of
  dropping them (opt-in per pair, or `--follow-renames`).
- Nothing in the library's folders is ever touched; only the JSON file changes.

**Open questions.** Flag, config setting or both? Does an unreadable or empty library (drive not mounted) prune
everything? (Proposal: refuse to prune when the library root is missing or empty of groups.) Does `config --sync` share
this behaviour? Docs to update on change: `how-to-use.md`, the README usage section, `cli-reference.md` via
`make docs-cli`.

## Next steps

1. Agree the opt-out (flag, setting or both) and the empty-library guard.
2. Build it with tests for prune, backup, opt-out and rename carry-over; update the user docs listed above.
3. Record the decision as an ADR and link it to this RFC.
