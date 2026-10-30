# Plan: word-boundary matching

1. `contains_words(text, phrase)` helper beside `normalise_for_matching`, with tests (test first).
2. Use it in `match_category`, `match_group_hints` and the exact step of `match_group`, when normalising.
3. Boundary check on the fuzzy alignment span in `match_group`.
4. Re-run calibration (both corpora), decide the plural question, update pins and `calibration.md`.
5. Docs (how-to-use "Choosing names that work", limitations, roadmap), `make check`, `make test`, PR.
