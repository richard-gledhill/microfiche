# Sort as files arrive

Status: Accepted

Settled on 2026-10-31 ([ADR-012](../adr/ADR-012-watch-mode.md)).

- **Id:** `watch-mode` ([capability map](post-mvp-capability-map.md), #7)
- **Depends on:** `matching-precision`, `hint-learning`, `scriptable-output`, `drift-check`

## Why

Today filing happens only when the user remembers to run `sort`. Watch mode files documents shortly after they land in
the inbox, so the library stays organised without a manual step. It comes last because unattended filing is only
acceptable once confident misfiles are rare (`matching-precision`), the rules improve on their own (`hint-learning`),
the outcome can be reported to other tools (`scriptable-output`) and drift is noticed (`drift-check`).

## User stories

- As a user who saves attachments into `_sorting/` all day, I want them filed without running a command.
- As a user, I want to know what watch mode filed and what it left for review, and to undo a batch like any other job.

## Requirements

**Must**
- `microfiche watch` watches the inbox and runs the normal sort pipeline on new units, with every existing safeguard:
  the threshold, the collision and duplicate checks, the drift check, and one rollback-able job per batch.
- New units are found by **rescanning the inbox** with the existing scanner at a short interval. A missed or late file
  event can only delay a file, never lose it.
- A unit is processed only once it has stopped changing (size and modification time unchanged across two scans, taken
  without reading content), and the move stays a plain rename, which fails cleanly on a file that is still open. A file
  still being written or synced is never moved.
- Batching: a batch runs when some unit is stable and the scan itself was quiet, so a folder copied in is one job. One
  interval is the quiet period.
- The run lock is held only while a batch is filed, so `review` and `rollback` can run between batches. A lock timeout
  (`[watch] lock_timeout_seconds`, default 30) replaces "refuse at once" for watch mode; on a timeout the batch is retried
  on the next scan.
- `[watch] interval_seconds` (default 3600) and `--interval`; `--use-ai` is opt-in.
- Units held for review are not re-classified every batch; they are retried only when they change or when the config or
  library file changes.
- Stops cleanly on Ctrl-C, finishing the current batch so no job is half-filed.
- Works the same on a local disk, a network share and a OneDrive-synced folder.

**Should**
- A summary line per batch, and `--json`: one compact JSON line per batch (the `sort` document).

**Won't (this time)**
- File-system event libraries (`watchdog`). Polling the inbox is enough and adds no dependency; see the review below.
  Add `watchdog` later as an optional trigger only if polling's delay or cost is a measured problem.
- Running as a Windows service or a startup item; the user starts it.
- Watching anything but the inbox.

## Acceptance criteria

- A file written slowly into the inbox is filed only after it stops changing.
- Ten files copied in at once are filed as one job that `rollback --last` undoes.
- `review` can run while `watch` is idle; while a batch is filing, it waits for the lock up to the timeout.
- A unit held for review is not re-classified on every batch.
- Tests drive the scanning, stability and batching logic with a fake clock and a fake inbox; no real waiting or file
  watching in the suite.
- Checked by hand on a OneDrive-synced inbox: no placeholder is downloaded just by being scanned, and nothing is moved
  mid-sync.
- `make check` and `make test` pass; `docs/how-to-use.md` and the README describe `watch`.

## Technical outline

Guidance for the spec, not binding.

- [watchdog-review.md](../architecture/watchdog-review.md) found `watchdog` suitable only as a trigger: on Windows it
  gives no "finished writing" event and `ReadDirectoryChangesW` can drop events under load, so a rescan and a stability
  check are needed either way. Since the inbox is small, polling with `scanner.py::scan_sorting_inbox` is the simpler
  first build. Record the decision as an ADR.
- Each batch calls `run_sort` scoped to the stable units.
- Add the lock timeout to `runlock.py` (shared with a future `--force`).
- A small clock and scan seam, so the loop is tested without sleeping.

## Related

- [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp): "Watch mode" and "A lock timeout or `--force` override".
- [mvp-followups-prd.md](mvp-followups-prd.md) D9 (lock timeout).
- [watchdog-review.md](../architecture/watchdog-review.md): the `watchdog` research, with sources.

## Decisions

- **Settings:** `[watch] interval_seconds` (default 3600) and `lock_timeout_seconds` (30), with `--interval`. No separate
  quiet period: a batch needs a quiet scan.
- **AI:** `--use-ai`, off by default.
- **Busy lock:** wait up to the timeout, then retry next cycle.
- **`--json`:** one line per batch.
- **Ctrl-C:** finish the current batch.
- **OneDrive:** the scan is stat-only; the by-hand check on a synced inbox is left for the user.
