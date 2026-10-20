# Matching precision: word boundaries and an ambiguity margin

Status: Draft

- **Id:** `matching-precision` ([capability map](post-mvp-capability-map.md), #2)
- **Depends on:** nothing (built after `library-init`, which is smaller and unblocks new users)

## Why

A document filed confidently into the wrong folder is the failure that costs microfiche its users' trust: the user has
to notice it, find it and move it back. Calibration showed a higher threshold cannot prevent this, because the confident
mistakes score *higher* than the cautious right answers ([calibration.md](../testing/calibration.md#summary)). Two causes
account for most of them:

- **Substring matches.** A group or category name matches inside another word, so `Car` files documents mentioning
  `carrier`, `care` or `scarf` at full confidence (0 of 2 right on the corpus).
- **Several names in one document.** When a document names two groups, `match_group` returns whichever comes first in
  the group list, so the answer depends on folder order, not on the document. A prototype that held such documents for
  review cut misfiles from 24 to 8 on the corpus, at a cost of 2 correct filings (89 to 87).

Holding *every* document with more than one candidate would also hold clear cases, such as a document that names its
own group and mentions another only through a weak fuzzy match. So a document is held only when the evidence for two
candidates is too close to call: their confidences are within a **margin** of each other.

## User stories

- As a user with short group names (`Car`, `Home`, `Tax`), I want a name to match only as a whole word, so unrelated
  documents are not filed under it.
- As a user whose documents mention other projects in passing, I want a document whose evidence is split between two
  groups to be held for review with the candidates listed, rather than filed under whichever folder sorts first.
- As a user, I want a document with one clearly stronger candidate to still be filed, even if a weaker one exists.

## Requirements

**Must**
- Match group names, category names and keyword hints on word boundaries. A name still matches when surrounded by
  punctuation, at the start or end of the text, or with a leading order prefix on the folder (`01 Requirements`).
- Apply the same boundary rule to fuzzy group matches, so a fuzzy match cannot land inside a longer word.
- At each stage (group, then category within the resolved group), collect every candidate with its confidence. If the
  runner-up's confidence is within the margin of the best one's, leave the unit unresolved at that stage and send it to
  review; the reason names the candidates and their confidences. Otherwise the best candidate wins as today.
- The margin is a setting, `[classification] ambiguity_margin` (name to confirm), from 0 to 1. Its shipped default is
  chosen by calibration and recorded in [calibration.md](../testing/calibration.md). The packaged defaults file is the
  only place the default lives.
- The result must not depend on the order of folders or of entries in the library file.
- Re-run the calibration, record the new numbers in [calibration.md](../testing/calibration.md), and update the pinned
  findings in `tests/calibration/test_calibration.py`.

**Should**
- Keep a filename rule decisive: a filename rule match is not overridden by an ambiguity found in the text.
- Folder units: apply the margin to the vote, so a near tie between two categories goes to review as an exact tie does
  today.
- Show the competing candidates in `review`, so the user can pick one directly.

**Won't (this time)**
- Weighting by position or frequency (title over body, counts). Revisit with calibration on real, longer documents.

## Acceptance criteria

- `Car` does not match `carrier`, `care` or `scarf`; it matches `Car`, `car.` and `(Car)`.
- A document naming `Phoenix` and `Atlas` exactly (both 1.00) goes to `needs_review` with both names and confidences in
  its reason, whatever the folder order.
- A document naming `Phoenix` exactly and matching `Atlas` only fuzzily, with the gap wider than the margin, is filed
  under `Phoenix`.
- Two categories matched only by hints (both 0.75) are held; a category-name match (0.90) beside another category's hint
  (0.75) files under the named category if 0.15 is wider than the margin.
- `ambiguity_margin = 0` holds only exact ties.
- On the calibration corpus at the default threshold, misfiles fall and correct filings fall by no more than the
  prototype's 2. The exact numbers are recorded in `calibration.md`.
- Folder units still vote document by document; a document left ambiguous casts no vote.
- `make check` and `make test` pass.

## Technical outline

Guidance for the spec, not binding.

- `rules/group_rules.py` and `rules/keyword_rules.py`: replace `name.lower() in lowered` with a compiled, escaped
  `\b`-anchored pattern per name, case-insensitive. Check how `\b` behaves next to non-word characters in names
  (`C++`, `R&D`); a lookaround on `\w` may be needed instead.
- Fuzzy: use RapidFuzz `partial_ratio_alignment` to get the matched span, and accept it only if the span sits on word
  boundaries ([ADR-002](../adr/ADR-002-switch-to-rapidfuzz.md)).
- Collect every match, not the first: the resolvers return ranked candidates with confidences, and `Classifier`
  applies the margin, so the resolvers only propose.
- The scores are fixed per kind of evidence (1.00 group name, 0.95 filename rule, 0.90 category name, 0.85 to 0.99
  fuzzy, 0.75 hint), so the margin effectively decides which kinds of evidence can outvote each other. Calibrate it at
  a few values (0, 0.05, 0.1, 0.15) and choose the one with the best misfile and auto-filing trade-off.
- The new setting goes in the packaged defaults, the `microfiche/` template, `MicroficheConfig` and the README's
  configuration table.
- Fake resolvers in `tests/core/test_classifier.py` for the ambiguity cases; boundary cases as parametrised tests on the
  rule modules.

## Related

- [mvp-roadmap.md](mvp-roadmap.md#future-work): "Match group names on word boundaries" and "Ambiguity check", which
  this requirement absorbs.
- The `Car` known limit in [mvp-roadmap.md](mvp-roadmap.md#release-stage-6) and the docs' "Current limitations".

## Open questions

- What default margin? Decided by calibration; record the trade-off at each value tried.
- Does the margin compare against the runner-up only, or count every candidate within it (which matters for the reason
  text, not the outcome)?
