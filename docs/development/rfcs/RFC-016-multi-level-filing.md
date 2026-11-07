# RFC-016: Multi-level filing

Status: Draft

**Background:** split from [RFC-014](RFC-014-filing-overhaul.md). It overlaps [RFC-004](RFC-004-filing-target-mode.md)
and serves [RFC-006](RFC-006-subcategories-depth-3.md); settle which of RFC-004 and this RFC survives before building.

## Multi-level filing

**Today.** `[library_structure] depth` is 1 or 2. At depth 2 a document is filed only if both group and category are
confident (`file_at = leaf_only` behaviour, as in [RFC-004](RFC-004-filing-target-mode.md)); otherwise it goes to
`review`. [RFC-011](archive/RFC-011-groups-without-categories.md) added filing into a group that has no category
folders, but not "group confident, category not".

**Proposal.** A `[library_structure]` setting, working name `multi_level_filing = true` (note the repo's config keys
use underscores, so not `multi-level-filing`), so that with `depth = 2`:

1. Resolve level 1 (group). If confident, continue; otherwise review.
2. Resolve level 2 (category) within the group. If confident, file into `group/category`.
3. If level 2 is not confident, file into the group folder (level 1) instead of sending the document to review.

Generalises to any depth as "file into the deepest level that is confident", which also serves
[RFC-006](RFC-006-subcategories-depth-3.md).

**Relationship to RFC-004.** This is the same behaviour RFC-004 calls `best_level` under `[sorting] file_at`. Decide
which setting survives (one place, not two). RFC-004's reviewer concerns still apply and should be measured before
building: a document parked in a group folder may be harder to find and then to re-file; a category name repeated under
several groups is a weak basis for a deeper filing; and `reclassify` must be able to move a parked document down later
when a category appears or the rules improve (a `keep` vs `move` rule for documents filed at a shallower level).

**Open questions.**
- Should a document parked at the group level be marked (ledger field, `classified_by`, or a reason) so `reclassify`
  and `review` can find it?
- Separate thresholds per level, or one threshold applied per level?
- Does it default off? (Proposal: yes, because filing nothing is safer than filing into a level the user did not
  expect.)
- Folder units: the dominant-category vote has to work at the shallower level when categories disagree but the group
  agrees.
- Tests: a depth-2 fixture where the group is clear and the category is not; sort, rollback and `reclassify` end to
  end; the calibration harness reports parked documents separately from misfiles.

## Next steps

1. Decide whether this merges with RFC-004 (one setting, not two).
2. Measure the RFC-004 reviewer concerns on the calibration corpus before building.
3. Record the decision as an ADR and link it to this RFC.
