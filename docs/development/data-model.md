# Data model: ledger, audit events, and rollback jobs

The target schema for everything microfiche writes to disk outside of the moved files
themselves. Everything lives under the library's dot-prefixed `.microfiche/` state folder
(`core.config.MICROFICHE_DIRNAME`, `Library.state_dir`), so Obsidian's file explorer hides it and no file ever gets
a companion file written next to it. Where the current implementation doesn't yet produce data
matching this, that's tracked as an open item in [mvp-roadmap.md](mvp-roadmap.md), not restated
here.

All of it is written by `core/filer.py` (`file_batch` and `rollback_job`); `core/ledger.py`
owns reading and writing the ledger file.

## Ledger (`.microfiche/ledger.jsonl`)

The record of what microfiche knows about each unit it has filed: where it went, what it was
classified as, and why. Append-only JSON lines — one `LedgerRecord`
(`core/models/ledger.py`) per line, never edited or deleted:

```json
{"event":"filed","job_id":"20261004-153012-a1b2c3","timestamp":"2026-10-04T15:30:12.481203","path":"Project Phoenix/02 Architecture/architecture_notes.md","original_path":"_sorting/architecture_notes.md","content_hash":"9f2c…","unit_type":"file","group":"Project Phoenix","category":"02 Architecture","group_reason":"Exact match on group name 'Project Phoenix'","category_reason":"Category name '02 Architecture' found in document text","confidence":0.9,"classified_by":"rules_engine"}
```

- **Key: `(path, content_hash)`.** `path` is relative to the library root with forward slashes,
  so the ledger stays valid if the library is moved between machines or OSes. `content_hash` is
  the SHA-256 of the file, or — for a folder unit — of a manifest of `relative path:file hash`
  lines for every file inside (`core/utils/hashing.py::unit_hash`). The hash lets a record be
  found again after a file is moved or renamed outside microfiche.
- **`classified_by`** names the resolver(s) that decided the classification: `rules_engine`, `ai_fallback`,
  or `rules_engine+ai_fallback` when each decided a different stage, or `user` for a choice made in `review`
  (its reasons read "Chosen in review" and its confidence is 1.0). (`folder_vote` marks a tied folder
  left for review; it never reaches the ledger because nothing is filed.)
- **`category` is `null` in a flat library** (`depth = 1`), which has no categories, and so is `category_reason`. A ledger
  can therefore hold records of both shapes if a library's depth is changed; the records are read as they were written.
- **Events.** `"filed"` is written when a unit is moved into the library. `"rolled_back"` is
  written when a rollback moves it out again; it carries only the identifying fields
  (`job_id`, `path`, `original_path`, `content_hash`, `unit_type`) and leaves the classification
  fields `null`.
- **Current state is derived, not stored.** `Ledger.current()` replays the history: a
  `rolled_back` record cancels the `filed` record with the same job and path, and a `filed`
  record whose `original_path` was an earlier record's `path` (a re-file) supersedes that
  earlier record — so rolling the re-file back brings the earlier record back.
  `Ledger.lookup(path, hash)` matches the exact pair first, then falls back to the hash alone
  only if exactly one current record has it (identical content filed twice is ambiguous), and
  never matches a file whose content has changed.
- **Corruption is loud.** An unreadable line raises `LedgerCorruptError` with its line number
  rather than being skipped — a bad line means a record of something microfiche did is missing.

Not recorded yet: `tags` (nothing extracts tags, and tag governance left the MVP with the Obsidian integration —
[feature-backlog.md](feature-backlog.md#obsidian-integration)), and the per-document breakdown behind a folder unit's
dominant-category vote ([architecture.md](architecture.md) §4).

This replaced the per-file `*.metadata.json` sidecars the earlier design wrote beside every
filed document: nothing ever read them, rollback left them behind, and they doubled the file
count of a vault. Existing sidecars from earlier builds are not migrated or read.

## `AuditEvent`

`core/models/audit_event.py` — one recorded action:

```python
class AuditEvent(BaseModel):
    original_path: Path
    new_path: Path | None = None
    action: AuditAction  # "move" | "rename" | "classify" | "override" | "rollback" | "remove_folder" | "restore_folder"
    timestamp: datetime
```

Of the seven `AuditAction` values, four are emitted today: `"move"` (from
`filer.py::file_batch`), `"rollback"` (from `filer.py::rollback_job`), and the pair
`"remove_folder"` and `"restore_folder"`. `"rename"`, `"classify"`, and `"override"` are defined for
future use — a rename-rules event, a classification-decision event, and a user-override event — but nothing produces
them yet. The `review` command does not use `"override"`: it files a person's choice as an ordinary `"move"`, recorded
in the ledger with `classified_by = "user"`.

`"remove_folder"` records an inbox folder that was removed because all of its files were filed and it was
left completely empty (`original_path` is the folder, `new_path` is `None`). It is only emitted when
`keep_folders` is off, since a folder kept whole moves as one unit. `"restore_folder"` is what
`rollback_job` writes when it recreates that folder. No file is deleted: only a folder with nothing in it.

## `Job`

`core/models/job.py` — the set of moves made by one `sort`, `reclassify --apply` or `review` filing:

```python
class Job(BaseModel):
    job_id: str                          # e.g. "20261004-153012-a1b2c3"
    created_at: datetime
    moves: list[AuditEvent]              # absolute paths; the moves, then any folder removals
    rolled_back_at: datetime | None      # set once rolled back; a job can't be rolled back twice
```

**Path:** `<library_root>/.microfiche/rollback/job_<id>.json`.

`core/filer.py` provides both directions:

- `file_batch(library, items)` — moves each unit into its `group/category` folder (its `group` folder in a flat library), then for
  every move appends to the ledger and the audit log, and saves the `Job`. The whole batch is
  checked for unresolved classifications before anything moves. A move is a plain rename
  (`core.utils.filesystem.safe_move`), so it either happens or changes nothing. If it fails (a file
  another program has open, a destination taken in the meantime, a permission error) the unit stays
  where it is, nothing is recorded for it, and the rest of the batch is filed. It returns a
  `FilingResult`: `job` (the saved job, or `None` if nothing moved, in which case nothing is
  written) and `failed` (each unit that stayed, with a one-line reason). The job therefore holds
  only moves that happened. After the last move, an
  inbox folder that the filed units came from (`SortableUnit.origin_folder`) is removed, with its
  empty sub-folders, if nothing at all is left in it; each removal is a `remove_folder` event in the
  job and the audit log. A removal is not a filed unit, so it has no ledger record.
- `DestinationClaims(library).claim(destination)` — used by `sort` and `reclassify` to plan a batch:
  it refuses a path that already exists or that another unit in the run has claimed, and says why.
  `file_batch` still refuses to overwrite as the last line of defence.
- `rollback_job(library_root, job_id)` — reverses the job's moves newest-first, recreating a removed
  folder (a `restore_folder` audit line) before the files that were in it go back,
  appends `rolled_back` ledger records and `rollback` audit lines, and sets `rolled_back_at`. It is safe
  to retry: if an earlier attempt stopped part-way, units already back at their original
  location are skipped. Raises `JobNotFoundError`, `JobAlreadyRolledBackError`,
  `JobMoveMissingError` (a unit is at neither location) or `FileExistsError` (something now
  occupies the original location). Job ids are restricted to letters, digits, `-` and `_`.
- `load_job` / `save_job` — read and write the job file.
- `latest_job(state_dir)` — the newest job (by `created_at`) that has not been rolled back, for `rollback --last`. A job file that
  cannot be read is skipped with a warning; if no readable job is left it raises `NoJobToRollBackError`, naming those files.

Rollback only ever moves things back and recreates folders; it deletes nothing.

## `audit.log`

`.microfiche/audit.log` — the human-readable trail shown by `microfiche audit`. One line is
appended per `AuditEvent`, with library-relative paths:

```text
2026-10-04T15:30:12 job=20261004-153012-a1b2c3 move _sorting/architecture_notes.md -> Project Phoenix/02 Architecture/architecture_notes.md
2026-10-04T15:30:12 job=20261004-153012-a1b2c3 remove_folder _sorting/weekly-pack -> -
2026-10-04T15:41:03 job=20261004-153012-a1b2c3 restore_folder _sorting/weekly-pack -> -
2026-10-04T15:41:03 job=20261004-153012-a1b2c3 rollback Project Phoenix/02 Architecture/architecture_notes.md -> _sorting/architecture_notes.md
```

Format: `<ISO timestamp, seconds> job=<id> <action> <from> -> <to>`. It is a log for people; the
ledger and the job file are the machine-readable records.

## `.microfiche/` directory layout

```text
<library_root>/.microfiche/
├── microfiche-config.toml # the library's settings — read, not written, by microfiche
├── microfiche-library.json # the library's hints and filing rules; created, and kept in step with the folders, by `sort`
│                          #   and `config --sync` (never changing an entry the user wrote)
├── microfiche-library.schema.json # editor schema for the file above (copied in with the template; not written by microfiche)
├── README.md              # the template's notes on these files (copied in with the template; not used by microfiche)
├── microfiche.log         # the diagnostic log (+ microfiche.log.1 ... .N when rotated); written by changing commands
├── lock                   # exists only while a changing run (sort, reclassify --apply, rollback, config --sync, review's filing) is going
├── ledger.jsonl           # append-only classification ledger (above)
├── audit.log              # human-readable trail; read by `microfiche audit`
└── rollback/
    └── job_<id>.json       # one Job per sort / reclassify --apply / review filing; read by `microfiche rollback`
```

`ledger.jsonl`, `audit.log` and `rollback/` are created the first time something is filed; a
`sort` that files nothing writes none of them (it may still write the log and the library file). A `sort --dry-run` writes nothing at all.
Only `microfiche-config.toml` is required to exist, and not even that: without it the built-in defaults apply.

`lock` is the run lock (`core/runlock.py`): JSON holding the `pid`, `command` and `started` time of the run that
took it, created atomically and removed when the run ends. A second changing command refuses to start while it
exists. If the recorded process is gone the lock is stale and is cleared; if the file cannot be read it counts as
held and is never cleared automatically.

## See also

- [architecture.md](architecture.md) §7 — why the ledger replaced per-file sidecars.
- [mvp-roadmap.md](mvp-roadmap.md) — tracks which parts of this schema aren't produced yet.
