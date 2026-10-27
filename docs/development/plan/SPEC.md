# SPEC: folder-name matching (`matching-precision`, first slice)

Source: [RFC-010](../rfcs/RFC-010-folder-name-matching.md), decided in [ADR-005](../adr/ADR-005-folder-name-matching.md).
Style and bar: [conventions.md](../conventions.md), [constraints.md](../constraints.md).

## Scope

- `core/rules/normalise.py::normalise_for_matching(text, *, folder_name=False) -> str`. `folder_name=True` also splits
  camelCase and strips a 1-3 digit order prefix; document text and hints use `folder_name=False`.
- `match_group`, `match_category` and `match_group_hints` take `normalise: bool` and compare normalised strings when
  true. Confidences are unchanged (no discount). The word-boundary test is the next slice, not this one.
- `[classification] normalise_names` (bool, default true); `RulesEngine` passes it through.
- Warnings, in the library file sync and `config`: a folder name that normalises to nothing; two siblings that
  normalise equal.
- Library-file entry names, `Library.taxonomy()` and filename globs are untouched.

## Done when

- Each folder style (snake, kebab, camel, Pascal, prefixed, `&`, apostrophe, accent) matches the same text with the
  same group/category and confidence as the plain spelling.
- Calibration corpus has separator-named folders; `calibration.md` and pinned findings updated.
- `how-to-use.md`, README, packaged defaults, example config, generated CLI reference and schema are current.
