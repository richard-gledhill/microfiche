# ADR-005: Folder-name matching compares a normalised spelling

- **Status:** Accepted
- **Date:** 2026-10-27
- **Decision:** Group names, category names and keyword hints are matched against document text through one shared
  `normalise_for_matching()`, behind `[classification] normalise_names` (default on). Folders and files on disk are
  never renamed. A normalised match is not discounted. See [Decisions](#decisions).
- **Source:** [RFC-010](../rfcs/RFC-010-folder-name-matching.md)

## Context

Matching was a literal, lowercased substring test, so `meeting-notes`, `meeting_notes`, `MeetingNotes`, `01-meeting-notes`,
`R&D` and `Tom's Recipes` never matched the text they obviously name, and on the group fuzzy path punctuation lowered
confidence for a reason the user could not see.

## Decisions

- **One function, `rules/` module**, used by `group_rules.py` and `keyword_rules.py`: NFKD with combining marks dropped
  (so `Café` matches `Cafe`) then `casefold()`; camelCase/PascalCase split on folder names only; `&` → `and`, `@` → `at`;
  `+` and `#` are kept as part of a name (`C++`, `C#`); other punctuation becomes a space; apostrophes are removed;
  whitespace collapsed and trimmed. The character list is fixed, not configurable.
- **Order prefix:** strip 1 to 3 leading digits followed by spaces and `-_.)` separators. A longer digit run (`2024-03
  Invoices`) or digit-dot-digit version (`1.2 Design`) is not a prefix.
- **A setting, default on:** `[classification] normalise_names = true`. Off restores the literal comparison. It is a
  setting because it changes which documents file. The `init` walk-through does not list it yet.
- **No discount.** A normalised group match is exact (1.0), a category name match stays `name_match_confidence`; the fuzzy
  path keeps scoring, now on normalised strings. Over-matching (`Notes` vs `Meeting Notes`) is for the ambiguity margin in
  [matching-precision](../requirements/matching-precision-prd.md).
- **Hints are normalised on both sides**, so hint `r&d` matches `R and D`.
- **Library-file entry names stay exact** (`can_be_entry_name`); matching an entry to its folder stays by `casefold`.
  Filename-glob rules are untouched.
- **Reporting:** a name that normalises to nothing, and two siblings that normalise equal, are reported as warnings by
  the library file sync and by `config`, next to the existing case-only duplicate warning. Sorting is not blocked.
- **Lands before the `\b` work.** After normalisation a boundary test is `f" {name} " in f" {text} "`.

## Alternatives considered

- Always on, no setting: simpler, but gives users no way back if a library's matches shift.
- Discount normalised matches: reintroduces spelling-dependent confidence.
- Fold only NFKC, keep accents distinct: PDF and email text often loses accents.
- Configurable separator list: config surface for a rare need.
- Error on collisions: too strict for a read-only concern.

## Consequences

- Some documents that went to review now file. Needs a calibration run: add separator-, `&`- and prefix-named folders
  to `tests/calibration/`, update `docs/development/testing/calibration.md` and the pinned findings.
- New setting to document: packaged defaults, `docs/how-to-use.md`, README, generated CLI reference and `init`.
- `Library.taxonomy()` still returns names as written.
