# ADR-006: Ambiguity margin: hold a stage when the evidence is too close to call

- **Status:** Accepted
- **Date:** 2026-10-28
- **Decision:** The rules collect every candidate at each stage and hold the stage, with the close candidates named, when
  the runner-up is within `[classification] ambiguity_margin` (default 0.1) of the best. The margin is applied in
  `match_group` and `match_category`, not in `Classifier`. An exact group name settles the group stage against fuzzy
  candidates. See [Decisions](#decisions).
- **Source:** [matching-precision-prd.md](../requirements/matching-precision-prd.md), slice B

## Context

Both stages returned the first match: `match_group` the first exact name in folder order, `match_category` the first
category whose name or hint appeared. A document naming two groups was filed under whichever sorted first, and calibration
showed a higher confidence threshold cannot prevent it ([calibration.md](../testing/calibration.md#ambiguity-margin)).

## Decisions

- **Collect, then choose.** `rules/ambiguity.py::choose` takes every `Candidate` (name, confidence, reason, matched
  words) and returns a winner or the close set. `best - other <= margin` is held (rounded to 6 places so 0.9 - 0.75 is
  exactly 0.15). The result does not depend on folder, entry or hint order.
- **In the rules, not the classifier.** The PRD outline had `Classifier` apply the margin. The rules are the only
  resolver with ranked evidence, and keeping `Resolver` unchanged leaves the AI fallback free to answer a held stage.
  `GroupMatch` and `CategoryMatch` gain `candidates`, which is also what a later `review` picker needs.
- **Longest name wins.** A candidate whose words are a whole-word part of another candidate's (`Home` in `Home
  Insurance`) is dropped, so a name is not ambiguous with its own prefix.
- **An exact group name settles the group stage against fuzzy candidates.** Sibling names that merely look alike
  (`Project X`, `Project Y`: fuzzy 0.89) are a property of the folders, not evidence from the document. Two exact names, or
  fuzzy-only candidates, are still compared by the margin.
- **Filename rules stay decisive**: they are tried before `match_category` and never reach the margin.
- **Flat libraries hold an ambiguous name** instead of falling through to the group hints.
- **Folder units:** a document held as ambiguous at either stage casts no vote. Ties are held as before; the margin is a
  confidence distance, so it has no meaning for vote counts.
- **Default 0.1.** Swept at 0, 0.05, 0.1, 0.15 and 0.2: 0 to 0.1 are identical on the corpora; 0.15 is the first value that
  holds a category name (0.90) beside another category's hint (0.75), losing a correct filing and removing no misfile.

## Alternatives considered

- Apply the margin in `Classifier` over ranked candidates from the resolver: a wider `Resolver` protocol for no gain.
- Include fuzzy candidates against an exact name: holds documents that name one group exactly because of how folders are
  named.
- A vote-share margin for folder units: a second margin setting with no measurement behind it.
- Default 0: simpler to explain, but a hair's-breadth difference between two fuzzy scores would pick a winner.

## Consequences

- Documents that name two groups, or hit two categories by hint, now go to review where they used to file under the first.
  On the corpus: misfiles 24 → 6 together with word boundaries, correct filings unchanged.
- A real library with more fuzzy scores may separate margins 0 to 0.1; long documents mention more groups, so the cost in
  held correct filings is unmeasured.
- Candidates in `review` (so the user picks one directly) is a follow-up; until then they appear in the reason text.
