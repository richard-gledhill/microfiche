# SPEC: watch mode (`watch-mode`)

Source: [watch-mode-prd.md](../../../requirements/watch-mode-prd.md), decided in
[ADR-012](../../../adr/ADR-012-watch-mode.md).

## Scope

- `scanner.py`: `snapshot_inbox` (stat-only: name, size, mtime per inbox entry; a folder's signature covers its files) and
  `scan_sorting_inbox(only=)`, which opens only the named entries.
- `organizer.run_sort(only=)`: sorts just those inbox entries.
- `runlock.run_lock(timeout=)`: polls for the lock until the timeout, then raises `RunLockedError`.
- `watcher.py`: `Watcher` (stability across two scans, a batch only on a quiet scan, held units retried only when they or the
  config/library file change, lock timeout skips the batch, any failure reported and retried, `stop()` finishes the batch),
  with a `Clock` seam and a snapshot function so tests use fakes.
- Config: `[watch] interval_seconds` (3600) and `lock_timeout_seconds` (30), in the packaged defaults, the example config
  and the `init` walk-through.
- CLI: `watch` (`--interval`, `--use-ai` checked once at start, `--json` as one compact `sort` document per batch or an
  `error` line, `-v`/`-q`), the drift check each batch, Ctrl-C finishes the current batch.

## Not done

- A by-hand check on a OneDrive-synced inbox (PRD acceptance): left to the user.
