# SPEC: ambiguity margin (`matching-precision`, slice B)

Source: [matching-precision-prd.md](../requirements/matching-precision-prd.md) (Accepted); slice B of two. Builds on
[ADR-005](../adr/ADR-005-folder-name-matching.md) and the archived word-boundary plan. Style and bar:
[conventions.md](../conventions.md), [constraints.md](../constraints.md).

## Scope

- `[classification] ambiguity_margin` (0 to 1). At each stage the rules collect every candidate with its confidence. If
  the runner-up is within the margin of the best (`best - other <= margin`), the stage is unresolved and the reason lists
  every candidate within the margin of the best. `0` holds only exact ties.
- **Where it lives.** `match_group` and `match_category` apply the margin, so `Resolver` is unchanged and the AI fallback
  is still asked about a held stage. This departs from the PRD outline (which has `Classifier` apply it) because the
  rules are the only resolver with ranked evidence. `GroupMatch` and `CategoryMatch` gain `candidates`: the names held
  between, empty otherwise (also what the `review` follow-up needs).
- **Longest name wins.** A candidate whose name is a whole-word part of another matched candidate's name is dropped
  (`Home` inside `Home Insurance`), so a long name is not "ambiguous" with its own prefix.
- **An exact group name settles the group stage against fuzzy candidates.** Sibling names that merely look alike
  (`Project X`, `Project Y`: fuzzy 0.89) are a property of the folders, not evidence, so they never hold a document that
  names one group exactly. Two exact names, or fuzzy-only candidates, are still compared by the margin.
- **Filename rules stay decisive** (already tried before `match_category`; a test pins it).
- **Folder units.** A document left ambiguous at either stage casts no vote; ties are held as today.
- A flat library: an ambiguous name match is held, not passed on to the hints.

## Open until measured

- The default margin: sweep 0, 0.05, 0.10, 0.15 on both corpora; record each in `calibration.md`.

## Done when

- The PRD's acceptance criteria hold, `ambiguity_margin = 0` holds only exact ties, and results do not depend on folder
  or hint order.
- Calibration re-run and recorded; pinned findings updated; docs and config template current.
