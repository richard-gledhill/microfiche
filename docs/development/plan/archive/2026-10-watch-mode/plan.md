# Plan: watch mode

1. Stat-only `snapshot_inbox`, `only=` on the scan and `run_sort`, `run_lock(timeout=)`.
2. `[watch]` settings (config, defaults, example config, `init` tests).
3. `watcher.py` and its tests on a fake clock and inbox.
4. The `watch` command: batch under the lock, drift check, summary line, `--json`, Ctrl-C.
5. Docs, capability map, roadmap; `make check`, `make test`.
