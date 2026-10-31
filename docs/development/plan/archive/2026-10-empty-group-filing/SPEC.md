# SPEC: empty-group filing (`empty-group-filing`)

Source: [RFC-011](../../../rfcs/archive/RFC-011-groups-without-categories.md), decided in [ADR-007](../../../adr/ADR-007-leaf-groups.md).
Style and bar: [conventions.md](../../../conventions.md), [constraints.md](../../../constraints.md).

## Scope

- `[sorting] file_in_empty_groups` (default false). When true, at depth 2 a group with no category folders is a leaf:
  `Classifier` sets `category = None` for it and takes confidence from the group alone, without asking any resolver for
  a category. `ClassificationResult.folders` is then `(group,)`.
- `Taxonomy.is_leaf(group)`: true when the group has no categories. It takes a group only: `Taxonomy` holds no data
  below the category level, so RFC-006 generalises it when depth 3 exists (a departure from ADR-007's "takes a path").
- A folder unit's vote counts a leaf group as `(group, None)`, as in a flat library (already the case).
- `review`: `(group,)` is a place when the setting is on and the group has no categories (existing or planned); the
  prompt offers to file straight into such a group. `reclassify` needs no change (`filed_under` accepts the group).
- `sort` and `review` report how many units went straight into a group for lack of categories.
- `attachments` joins the default `[exclusions] exclude`.
- No change to hints, rules, the ledger or the audit log.

## Done when

- With the setting on, a unit naming an empty group is filed in it by `sort`, `review` can choose it, `reclassify` keeps
  it; with it off, behaviour is unchanged. Verified by tests through `run_sort`, `ReviewSession`, `plan_reclassify`.
- Docs, defaults, example config and generated CLI reference are current.
