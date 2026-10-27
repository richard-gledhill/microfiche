# RFC-010: Folder-name matching: separators, case styles and special characters

Status: Draft

**Background:** raised on 2026-10-25 from a review of how folder names are matched against document text. Nothing built.
Found by reading the code and tests; the examples below were not run.

**What happens now.** `sort` never renames a folder: `apply_naming_rules` is applied to the filename only
(`filer.py::destination_for`). The folder name matters only for matching, and the matching is a literal, lowercased
substring test:

- **Group** (`rules/group_rules.py::match_group`): `group_name.lower() in text.lower()` is an exact match
  (confidence 1.0). Otherwise `rapidfuzz.fuzz.partial_ratio` against the whole text, accepted at
  `[classification] fuzzy_group_threshold` (default 85), with the score as the confidence.
- **Category** (`rules/keyword_rules.py::match_category`): `_normalize(name) in text.lower()` at
  `name_match_confidence` (0.9). `_normalize` only strips a leading `^\d+\s*` and lowercases. There is no fuzzy step.
- **Hints** (`match_category`, `match_group_hints`): `keyword.lower() in text.lower()`, literal.

So the folder's spelling has to appear in the text character for character:

| Folder | Text says | Result |
|---|---|---|
| `meeting-notes`, `meeting_notes`, `MeetingNotes` | `Meeting Notes` | no category match; hints or review |
| `01-meeting-notes`, `02_annual_report` | `Meeting Notes` | the prefix regex needs a space after the digits, so the name is left as `-meeting-notes` / `_annual_report` and never matches |
| `R&D`, `Terms & Conditions` | `R and D`, `Terms and Conditions` | no exact or category match |
| `Tom's Recipes` | `Toms Recipes` | no exact or category match |
| `project-alpha`, `ProjectAlpha` (group) | `Project Alpha` | probably saved by the fuzzy match (one or two edits in 13 characters, about 90), so it files but below 1.0; unverified |

The fuzzy step helps groups only, and it costs confidence: every character the folder has and the text does not takes
the score down, and a long name with several special characters can fall under the threshold of 85. A category has no
such step, so punctuation and separators make it all-or-nothing. Either way the cause is the folder's spelling, not the
document.

## Do special characters affect classification confidence?

By the code, yes, in two ways, and both are accidental:

1. **Group, fuzzy path.** The score is the confidence, so `Terms & Conditions` against text saying `Terms and
   Conditions` scores below an exact match, may land under 0.75 (the filing threshold) and go to review for no reason
   the user can see. A folder with no special characters in the same position would have matched exactly.
2. **Category and hints.** No score; a special character that is not in the text simply prevents the match.

A special character carries no meaning that should lower confidence. `R&D` and `R and D` name the same thing. The
proposal below removes the effect by comparing the same spelling on both sides, leaving confidence to measure how
well the name matches, not how the folder was typed.

## Proposal

Match on a normalised form of both the folder name and the text. **Folders and files on disk are never changed**:
the normal form is used for comparing only, and `Library.taxonomy()` still returns the folder names as written.

One shared function, `normalise_for_matching(text) -> str` (in `rules/`, used by `group_rules.py` and
`keyword_rules.py`), that:

1. Applies Unicode compatibility folding (NFKC) and `casefold()`.
2. Splits camelCase and PascalCase at the lower-to-upper boundary (`MeetingNotes` → `Meeting Notes`); this runs on a
   folder name only, before lowercasing, because document text has its own capitalisation.
3. Maps `&` to the word `and` (with spaces around it), so `R&D` and `R and D` both become `r and d`. (`+` and `@`
   need a decision; see below.)
4. Turns `-`, `_`, `.`, `,`, `;`, `:`, `/`, `\`, brackets, parentheses and quotation marks into a space, and removes
   apostrophes (`Tom's` → `toms`, matching `Toms` and, after step 4 on the text, `Tom's`).
5. Strips a leading order prefix in the usual styles: `01 `, `01-`, `01_`, `01.`, `01 - ` (digits then any run of
   spaces and `-_.)`), the one fix to `_normalize`.
6. Collapses runs of whitespace to one space and trims.

A name that normalises to nothing (`&`, `---`, `(  )`) can never match; the library file sync and `config` report it
once as unmatchable instead of silently skipping it. Two siblings that normalise to the same string (`meeting-notes`
and `meeting_notes`) are ambiguous today's first-found-wins would hide; they are reported the same way the
sync already reports two folders differing only by case.

Confidence stays what it is for the kind of evidence: a normalised match on a category name is still
`name_match_confidence`; on a group name it is an exact match (1.0), and the fuzzy path keeps scoring, now on the
normalised strings. A normalised match is not discounted: the folder name is the user's, and the same evidence in a
different spelling is the same evidence. Whether to discount it is a question below.

## Order with the word-boundary work

[matching-precision-prd.md](../requirements/matching-precision-prd.md) replaces the substring test with `\b`-anchored
matching and an ambiguity margin, and its outline already warns that `\b` misbehaves next to `C++` and `R&D`. This RFC
should land first, or together: after normalisation every name and the text are plain words separated by single
spaces, so a boundary test is `f" {name} " in f" {text} "` and the `\b` problem with special characters goes away.
Doing it the other way round means writing the lookaround for `&` and then throwing it away.

## Questions to settle before building it

- Always on, or a setting (`[classification] normalise_names`)? The proposal is always on, because it changes only
  which spelling is compared, never where a file goes, but it does change which documents file, so it needs the
  calibration run below.
- Discount a normalised match slightly (for example 0.9 → 0.85)? The risk is over-matching: `Notes` and `Meeting
  Notes` both match once separators are gone. The ambiguity margin in the precision requirement is the better tool.
- Which characters count as separators and which are dropped? `+` (`C++`) and `#` (`C#`) are part of a name's identity;
  `&` and `@` read as words. A short list in the config, or fixed?
- Unicode: fold accents (`Café` ↔ `Cafe`)? NFKC alone keeps them distinct.
- Apply the same normal form to keyword hints? Proposed yes (both sides), so a hint `r&d` matches `R and D`.
- Filename-glob rules (`match_by_filename`) use `fnmatch` on the lowered filename and are out of scope: a glob is
  already the user's explicit pattern.
- The library file's entry names stay exact (`can_be_entry_name`); matching an entry to its folder stays by `casefold`.
  Confirm normalisation must not leak into that.
- A leading prefix that is a date (`2024-03 Invoices`) or a version (`1.2 Design`) is not an order prefix; where is the
  line? Probably: strip only a prefix of 1 to 3 digits.

## Tests and docs it would need

- Parametrised tests on `normalise_for_matching`: snake, kebab, camel, Pascal, spaced, prefixed (`01 `, `01-`, `01_`,
  `01 - `), `&`, apostrophes, parentheses, accents, an all-punctuation name, and an idempotence check.
- `match_group` and `match_category` for each folder style against the same text, expecting the same result and the
  same confidence; `Terms & Conditions` against `Terms and Conditions` is an exact match (1.0), not a fuzzy score.
- Sync/`config` reporting for a name that normalises to nothing and for two siblings that collide.
- Calibration: add folders spelled with separators and `&` to the `tests/calibration/` corpus, re-run
  `uv run python tests/calibration/report.py`, update `docs/development/testing/calibration.md` and the pinned
  findings in `test_calibration.py`.
- Docs: `docs/how-to-use.md` (the section on picking names that work), the README's library-layout section, and
  `mvp-roadmap.md` (the current limitations list).
