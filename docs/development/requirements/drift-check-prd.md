# Background drift check

Status: Draft

- **Id:** `drift-check` ([capability map](post-mvp-capability-map.md), #6). Formerly drafted as `ledger-doctor`, a
  separate command; folded into the existing commands instead.
- **Depends on:** nothing

## Why

Users move and rename filed documents in Obsidian or Explorer. The ledger and the rollback jobs record paths, so after
such a change `rollback` can fail part-way and `reclassify` splits a bundle that was moved by hand. The user is not told
until something goes wrong. The undo promise is the product's core guarantee, so drift should be found before it breaks
it, without the user having to remember to run a separate command. Watch mode makes this more pressing.

## User stories

- As a user who reorganised a few files by hand, I want the next microfiche command to notice and tell me, without
  running anything extra.
- As a user, I want microfiche to keep track of where a moved file is now, so rollback and reclassify keep working,
  without moving anything itself.

## Requirements

**Must**
- No new command. The check runs as part of the commands that already read the library: `sort`, `review`,
  `reclassify`, `rollback` and `config`.
- It compares `Ledger.current()` with the filesystem and classifies each filed item as: in place; moved (same content
  found elsewhere in the library); modified (same path, different content); or missing. Folder units filed whole are
  checked as one item.
- It is cheap enough to run every time: a stat per recorded path, and hashing only to look for the new place of a
  missing item, reading sizes first as the duplicate check does. On a library of thousands of items it must not add a
  noticeable delay; if it would, it checks only the items the command is about to use.
- **Changing commands** (`sort`, `review` and `reclassify --apply`, `rollback`), under the run lock, append a ledger
  record for each moved item so the ledger points at its new place. They never move, rename or delete a file because of
  drift. The record type is added to [data-model.md](../architecture/data-model.md).
- **Read-only commands and previews** (`sort --dry-run`, `reclassify` without `--apply`, `config`) only report; they
  write nothing, as today.
- The report is one summary line when there is drift ("2 filed items moved, 1 missing; recorded"), with details in the
  diagnostic log and with `-v`. Nothing is shown when everything is in place.
- `rollback` of a job whose files have moved uses the recorded new place; for a missing or modified file it stops before
  moving anything and says which files and why.

**Should**
- Include the drift summary in `--json` output, if `scriptable-output` is built first.
- Let `reclassify` treat a moved bundle as the bundle at its new place, instead of splitting it.

**Won't (this time)**
- A standalone `doctor` command (only if the background check proves too slow for some commands).
- Fixing rollback jobs in place. Jobs stay as recorded; the ledger carries the correction.
- Following a file outside the library.

## Acceptance criteria

- After moving one filed file to another category by hand, the next `sort` reports one moved item and records it; a
  second `sort` reports nothing.
- `sort --dry-run` reports the same drift and writes nothing.
- After editing a filed file, it is reported as modified; after deleting one, as missing; neither is recorded as moved.
- `rollback` of the job that filed the moved file restores it from its new place; with a missing file it moves nothing
  and names the file.
- On the 31 GB walkthrough library, the check adds less than an agreed time to `sort` (measure and record).
- `make check` and `make test` pass, and `data-model.md` documents the new record.

## Technical outline

Guidance for the spec, not binding.

- One `core` function (for example `ledger.check_drift(library)`) returns the classified items; the CLI decides whether
  to record and what to print, as it does for the lock and logging.
- Missing items are looked up by content hash with `duplicates.py::DuplicateIndex`, which already walks the library by
  size first.
- The new ledger record (`relocate`, name to confirm) keeps the append-only rule; `Ledger.current()` applies it.
- A bundle moved by hand: match on its recorded member hashes, accepting a folder whose members all match.

## Related

- [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp): "`doctor` / `verify` command", which this replaces with a
  background check.
- [mvp-followups-prd.md](mvp-followups-prd.md) D12 (detecting folders moved by hand), and the known limit that a bundle
  moved by hand is split by `reclassify`.

## Open questions

- Should `review` and `sort` skip the hash lookup when nothing is missing (the common case), so the cost is only stats?
- How should an item that was moved *and* edited be found, given its hash changed?
