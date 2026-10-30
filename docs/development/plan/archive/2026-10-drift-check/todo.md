# Todo: drift check

- [x] `relocated` ledger event and `Ledger.relocations()`
- [x] `check_drift`, `record_moves`, `find_modified` with tests
- [x] `rollback_job` follows relocations, stops before moving for a missing unit, moves back an edited one
- [x] CLI wiring and `drift` in the JSON documents
- [x] Docs and data model; `make check`, `make test`
- [x] PR
- [ ] Follow-up: time the search on the 31 GB library; consider recording size at filing to narrow it
