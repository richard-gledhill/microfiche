# Plan: drift check

1. Ledger `relocated` event, `current()`, `relocations()`.
2. `drift.py` and its tests (moved, missing, moved+edited, ambiguous, bundles, edited).
3. `rollback_job`: relocations, preflight, edited, hop records.
4. CLI wiring, `--json` drift, docs, data model.
