# SPEC: word-boundary matching (`matching-precision`, slice A)

Source: [matching-precision-prd.md](../requirements/matching-precision-prd.md) (Accepted); slice A of two. The ambiguity
margin is slice B. Builds on [ADR-005](../adr/ADR-005-folder-name-matching.md). Style and bar:
[conventions.md](../conventions.md), [constraints.md](../constraints.md).

## Scope

- With `normalise_names` on, a group name, category name or keyword hint matches only as whole words:
  `f" {name} " in f" {text} "` on the normalised strings. `Car` no longer matches `carrier`, `care` or `scarf`.
- The fuzzy group match accepts a `partial_ratio_alignment` span only if it starts and ends on a word boundary of the
  normalised text, so a near-miss cannot land inside a longer word.
- `normalise_names = false` keeps the literal substring comparison (ADR-005: off restores literal matching).
- No new setting, no change to confidences, filename rules or `Library.taxonomy()`.

## Open until measured

- Whole-word matching stops a hint `lecture` matching `lectures`. Measure on the calibration corpora before deciding
  whether plurals need a rule.

## Done when

- `Car` does not match `carrier`, `care` or `scarf`; it matches `Car`, `car.` and `(Car)`.
- Fuzzy near-misses inside a longer word are refused; the corpus's fuzzy cases still file.
- Calibration re-run and recorded in `calibration.md`; pinned findings updated.
