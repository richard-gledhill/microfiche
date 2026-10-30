# SPEC: hint learning (`hint-learning`)

Source: [hint-learning-prd.md](../../../requirements/hint-learning-prd.md), decided in
[ADR-008](../../../adr/ADR-008-hint-learning.md). Style and bar: [conventions.md](../../../conventions.md),
[constraints.md](../../../constraints.md).

## Scope

- `[learning]` config: `enabled` (default false), `min_decisions` (3), `max_hints_per_run` (3), `min_word_length` (4).
- `learned_hints` on a library-file entry; `LibraryFile.hints_for` returns the user's hints then the learned ones;
  `learned_hints_for` returns only the learned. A `*` entry cannot hold them.
- `core/learning.py::learn_hints`, run at the end of `ReviewSession.commit` when a job was filed: words in at least 60%
  (and two) of the documents the ledger records as filed by the user into a category, in none under a sibling category,
  not a stop word, name word or known hint, not rejected. Written with `write_library_file`; each hint is appended to the
  ledger as a `hint_learned` event, which is how a hint the user deleted is remembered.
- A match on a learned hint says "Learned keyword hint" in its reason; `SortReport.by_learned_hint` counts them and
  `sort` prints it. `review` prints each hint learned and how to remove it.
- `tests/calibration/learning_sim.py` simulates held-out learning on the corpus.

## Not in scope

`reclassify` does not teach; `rollback` does not remove hints; no confirm prompt; no list/reset command.
