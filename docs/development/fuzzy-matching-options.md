# Fuzzy matching options

microfiche uses fuzzy string matching to match group names. It also used it for tags, until the Obsidian integration
was removed from the MVP ([feature-backlog.md](feature-backlog.md#obsidian-integration)); the tag parts below are
kept as history. This page records what `thefuzz` actually is, how it
compares with RapidFuzz and the other options, what was measured, and when in the build plan to switch. It feeds
[Stage 4.1](mvp-build-plan.md#stage-41--configuration-consolidation) of the build plan. The switch was made as the last Build step of Stage 4.1; the "Outcome" section at the end
records what was done and what it showed.

## Where it is used

| Where | Call | What for |
|---|---|---|
| `rules/group_rules.py` | `fuzz.partial_ratio(group, text)` for every group name, on every document | A near-miss of a group's name in the document text (`Projct Phoenix`), scored 0 to 100 and compared with `[classification] fuzzy_group_threshold` (85). This is on the `sort` path. |
| `obsidian/tag_mapper.py` | `process.extractOne(candidate, canonical_tags)` | Map an extracted tag onto the library's `TagIndex.md` vocabulary. Never called from `sort`; removed with the Obsidian integration. |

## What `thefuzz` is

`thefuzz` 0.22.1 is a thin wrapper over RapidFuzz. Its `fuzz.partial_ratio` is RapidFuzz's `partial_ratio` with the
score rounded to an integer, and `RapidFuzz` is already installed as `thefuzz`'s only dependency (3.14.5 in
`uv.lock`). So this is not a choice between two engines: it is a choice between using the engine through a wrapper
and using it directly.

| | `thefuzz` | `rapidfuzz` |
|---|---|---|
| Latest release in `uv.lock` | 0.22.1, January 2024 | 3.14.5, April 2026 |
| Type information | none published (a mypy override is needed) | ships `py.typed` |
| `partial_ratio` signature | `(s1, s2)` | `(s1, s2, *, processor=None, score_cutoff=None)` |
| Score | `int`, rounded | `float` |
| Match position | not available | `partial_ratio_alignment` returns where the match starts and ends |

## What was measured

One machine, synthetic text (random words, 30 group names), best of three runs. The absolute numbers will differ
elsewhere; the ratios are the point.

| Test | `thefuzz` | `rapidfuzz` |
|---|---|---|
| `partial_ratio`, 30 groups against a 4,000-character document | 0.65 ms | 0.61 ms |
| the same against 20,000 characters | 2.38 ms | 2.37 ms |
| the same against 200,000 characters | 30.5 ms | 30.0 ms |
| the same, 20,000 characters, with `score_cutoff=85` (a simplified loop) | not available | 1.19 ms (4.38 ms without it) |
| tag matching: 20 queries against 500 tags (`extractOne`) | 9.5 ms | 5.6 ms |

- **Switching the function alone gains nothing**: the wrapper's overhead for `partial_ratio` is within noise.
- **The real gain is `score_cutoff`.** Only the group scores at or above the threshold matter, and RapidFuzz can stop
  early once a score cannot reach it. `thefuzz`'s `partial_ratio` has no such argument.
- **Neither is a bottleneck.** Group matching costs about 2 ms per 20,000-character document. Parsing a PDF or Word
  file is likely to cost more, though that was not measured here. Speed is a reason to take the cheap win, not to rush.
- **Accuracy is unchanged.** With RapidFuzz patched in for the group match (float scores, and again rounded to
  integers), the calibration report ([calibration.md](calibration.md)) is byte-for-byte identical to the
  `thefuzz` report on the 136-document corpus.

## Traps when switching

1. **`extractOne` preprocesses by default in `thefuzz`, not in RapidFuzz.** `thefuzz.process.extractOne` lowercases
   and strips punctuation before comparing (its `full_process`). `rapidfuzz.process.extractOne` does nothing by
   default, so `Python` and `python` would stop matching. Pass `processor=rapidfuzz.utils.default_process`. This is
   the one place a plain import swap changes behaviour, and `tag_mapper` needs a test that pins it.
   **It also deletes accented letters.** For its default scorer `thefuzz` forces the text to ASCII, which removes
   Latin-1 letters such as `é` and `ü` (`café` becomes `caf`) but not other scripts. That gives false matches
   (`ber` matches `über`, `nave` matches `naïve`, both at 100) and some accidental good ones (`munchen` matches
   `münchen` at 92). RapidFuzz's `default_process` keeps accents.
2. **Scores become floats.** `84.6` used to round to `85` and pass a threshold of 85. Round the score before the
   comparison to keep that exactly.
3. **`rapidfuzz` must be declared.** Once code imports it, `deptry` expects it in `core`'s dependencies, and
   `thefuzz` (and its mypy override in the root `pyproject.toml`) can go.

## What switching enables

- **`score_cutoff`** for the group match, as above.
- **Word-boundary matching.** The roadmap's open item "`Car` matches `carrier`" has two halves. The exact check
  (`group_name in text`) needs a regular expression with `\b`, whatever the library. The fuzzy check can use
  `partial_ratio_alignment` to find where the near-miss sits and apply the same boundary test to that stretch of text.
  That feature is still unscheduled (see [mvp-roadmap.md](mvp-roadmap.md), Future work); this page only records that
  RapidFuzz makes the fuzzy half possible.
- **A shorter dependency list**: one fewer package, and the `thefuzz` locked here dates from January 2024.

## Alternatives

These are from general knowledge and were **not** benchmarked here; none gives a reason to leave RapidFuzz.

| Option | Verdict |
|---|---|
| `difflib` (standard library) | No dependency, but it has no "best matching substring" score, so it cannot do the group match, and it is much slower. |
| `Levenshtein` / `python-Levenshtein` | Same author as RapidFuzz; edit distance and ratio only, with no partial (substring) match. |
| `jellyfish` | Edit distances and phonetic matching (Soundex, Metaphone). Phonetics is not what group names need. |
| `textdistance` | Many algorithms in pure Python: slower, with no substring score. |
| `regex` (approximate matching) | Fuzzy substring matching with `{e<=2}`, but hard to score, tune and explain, and slower. |

## Outcome

The switch was made with the rounding kept, so a raw score of 84.6 still counts as 85. RapidFuzz is also given a
`score_cutoff` of the threshold less one, which can only skip scores that could not have rounded up to the threshold.

- **Accuracy:** the calibration report is unchanged at the default (113 filed, 89 right, 24 wrong). On 6,000
  random group-match cases and 6,000 random ASCII tag-mapping cases, the old `thefuzz` code and the new code gave
  identical results.
- **Speed:** the real group match, 30 groups against a 20,000-character document, went from 2.81 ms to 1.55 ms
  (1.8 times faster). The 3.7 times in the table above was a simplified loop, not this function.
- **One deliberate behaviour change:** tag matching now keeps accents, as above. `tag_mapper` was never called from
  `sort`, so no user saw either behaviour, and it has since been removed with the Obsidian integration. Whether to
  fold accents on purpose (so `munchen` matches `münchen`) is still open and is listed in
  [feature-backlog.md](feature-backlog.md#obsidian-integration).

## Recommendation and timing

Depend on `rapidfuzz` directly, and do it **as the last Build step of Stage 4.1**, as its own commit:

1. **It must land before `v0.1.5`.** Stage 4.1 made `fuzzy_group_threshold` a user-facing setting. Today its
   documentation names `thefuzz`'s score and the type is a rounded integer. Settling the library before that ships
   means users never see the meaning change.
2. **The tools it needs now exist.** The calibration harness and the configurable threshold are both in place, so
   "the report is unchanged" is a test, not a hope.
3. **It had to land before the tag work**, which was to wire `tag_mapper` into `sort` under `[obsidian]`, the one
   place where the preprocessing trap bites. That work left the MVP, so this reason no longer drives the timing;
   reasons 1, 2 and 4 stand.
4. **It is small and independent.** Two files change, apart from dependency metadata and docs, so a separate commit
   (or a separate branch, if the Stage 4.1 branch is already large) keeps the review easy.

The steps are in the Stage 4.1 section of [mvp-build-plan.md](mvp-build-plan.md). Word-boundary matching stays in
Future work until it is measured on real documents.
