# Plan: ambiguity margin

1. `candidates` on `GroupMatch`/`CategoryMatch`; `ambiguity_margin` setting (model, defaults, example config).
2. `match_group`: collect all exact and fuzzy candidates, drop contained names, apply the margin (tests first).
3. `match_category`: collect name (0.90) and hint (0.75) candidates per category, same rules.
4. `RulesEngine` passes the margin; flat group stage does not fall through to hints on an ambiguous name.
5. `classify_unit`: ambiguous documents abstain from the folder vote.
6. Sweep the margin on both corpora, choose the default, update pins, `calibration.md`, user docs; `make check`/`make test`; PR.
