# ADR-011: Notice files moved by hand, in the commands that already read the library

- **Status:** Accepted
- **Date:** 2026-10-30
- **Decision:** `sort`, `review`, `reclassify`, `rollback` and `config` compare the ledger with the filesystem. An item
  that is gone from its recorded place but found elsewhere by content is recorded as moved, by a new append-only
  `relocated` ledger record, only by commands that already change the library. Nothing is ever moved because of drift.
  See [Decisions](#decisions).
- **Source:** [drift-check-prd.md](../requirements/drift-check-prd.md)

## Context

Users move and rename filed documents in Obsidian or Explorer. The ledger and rollback jobs record paths, so afterwards
`rollback` can fail part-way and `reclassify` splits a bundle moved by hand. The undo promise is the core guarantee, so
drift should be noticed before it breaks it, without a separate command to remember.

## Decisions

- **No new command.** The check is a core function over `Ledger.current()` and the filesystem; the CLI decides whether to
  record and what to print, as it does for the lock and logging.
- **Cheap by construction.** A stat per recorded path says whether it is in place. Only when something is missing is the
  library walked for its new place, sizes first, hashing only same-size files, as the duplicate check does.
- **States:** in place; moved (same content found at one other place in the library); modified; missing. A folder filed
  whole is one item, matched by its members' recorded hashes.
- **Modified is found on demand only.** The ledger keeps a content hash, not a size or modification time, and hashing every
  filed file on every command would not be cheap. A command reports `modified` for the files it already reads
  (`reclassify`, and `rollback` for the job it undoes). `sort` does not hash filed files, so it never reports an edit. No
  new fields are added to `filed` records.
- **Moved and edited counts as missing.** Its hash changed, so it cannot be found by content. It is reported missing,
  never recorded as moved, and the log lists same-named files in the library as a hint. No matching by name or size: a
  wrong guess in an append-only ledger is worse than a gap.
- **Recording.** Commands that already take the run lock (`sort`, `review`, `reclassify --apply`, `rollback`) append a
  `relocated` record for each moved item; `sort --dry-run`, `reclassify` without `--apply` and `config` only report.
  `Ledger.current()` applies the record. The jobs on disk are not edited: the ledger carries the correction. The record is
  described in `data-model.md`.
- **`rollback` follows the ledger.** A moved file is restored from its new place. A **modified** file is moved back like
  any other (rollback moves files and never changes them) and the edit is noted. A **missing** file stops the rollback
  before anything moves, naming the file.
- **Reporting.** One line when there is drift ("2 filed items moved, 1 missing; recorded"), on stderr, with details in the
  log and with `-v`; nothing when all is in place. With `--json`, an added optional `drift` object (counts and items with
  path, state and new place) in the sort, reclassify, rollback and review-queue documents. Adding an optional field needs
  no `version` bump.
- **`reclassify`** treats a bundle moved by hand as the bundle at its new place, because `Ledger.folder_units()` follows
  the `relocated` records.

## Alternatives considered

- Recording size and modification time in `filed` records so any command can report edits by stat: extra ledger fields and
  no answer for older records.
- Stopping `rollback` for a modified file (the PRD's draft): blocks an undo over a harmless edit.
- A standalone `doctor` command: the PRD's Won't unless the background check proves too slow.
- Guessing a moved-and-edited file by name and size.

## Consequences

- `sort` can say a file moved or is missing but not that it was edited. The PRD's acceptance criterion about edits is met by
  `reclassify` and `rollback`.
- The ledger gains an event type; every reader that replays it (`current`, `folder_units`, `lookup`) must apply it.
- A library of thousands of items pays one stat each per command, and a walk of the library only when something is missing.
