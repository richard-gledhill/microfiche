# SPEC: drift check (`drift-check`)

Source: [drift-check-prd.md](../../../requirements/drift-check-prd.md), decided in
[ADR-011](../../../adr/ADR-011-drift-check.md).

## Scope

- `core/drift.py`: `check_drift` (stat per `Ledger.current()` path; for missing ones, unaccounted files of the same extension,
  or folders of the same name, matched by hash, exactly one match = moved), `record_moves` (a `relocated` ledger record per
  moved unit), `find_modified` (hash on demand, for files a command already reads).
- `Ledger.current()` applies `relocated` like a re-filing; `Ledger.relocations()` lists the places a unit has been.
- `rollback_job` takes a unit from its relocated place, stops before moving anything if any unit is gone (naming all), moves
  an edited one back (`edited=`), and rolls back every hop in the ledger.
- CLI: `_check_drift` in `sort`, `review`, `file`, `reclassify`, `rollback`, `config` (records only under the lock), a warning
  line, details in the log, an optional `drift` object in the `--json` documents.
