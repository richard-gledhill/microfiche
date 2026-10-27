# Plan: folder-name matching

1. `normalise_for_matching` with parametrised tests (test first).
2. Thread `normalise` through `group_rules` and `keyword_rules`; `RulesEngine` reads `normalise_names`.
3. Add the `normalise_names` setting (model, packaged defaults, example config, `init` walk-through if it lists settings).
4. Warnings for unmatchable and colliding names in the sync and `config`.
5. Calibration corpus and docs.
6. `make check`, `make test`; PR.
