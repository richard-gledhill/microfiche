# Architecture

The design as it is built. Update these in place as decisions change, rather than adding dated files; record the
decision itself as an ADR in [`../adr/`](../adr/README.md).

| File | What it is |
|---|---|
| [overview.md](overview.md) | Start here. The library-aware sorting design: the library as the taxonomy, depth, the inbox and two-stage classification, sortable units, exclusions, the ledger, the CLI surface and the configuration layout. |
| [data-model.md](data-model.md) | The ledger, `AuditEvent`/`Job` schemas, the `audit.log` format and the `.microfiche/` layout, as one authoritative page. |
| [module-diagram.md](module-diagram.md) | The module import graph, generated from the source by `make module-diagram` (regenerate it, don't hand-edit), and the `sort` pipeline's data flow, written by hand. |
| [library-depth.md](library-depth.md) | Library depth (one, two or three levels) and non-library folders such as bundles filed whole. Depth 3 is in the [feature backlog](../rfcs/feature-backlog.md#subcategories-depth-3). |
| [ai-classifier-options.md](ai-classifier-options.md) | Research, not a decision: chat-model versus decision-model classifiers for the AI fallback, and the rules for adopting one. Feeds the [decision-model classifier](../rfcs/feature-backlog.md#decision-model-classifier) in the backlog. |
| [watchdog-review.md](watchdog-review.md) | Research, not a decision: whether the `watchdog` package suits [watch mode](../requirements/watch-mode-prd.md). It does, as a trigger only; polling the inbox is recommended first. |

User-facing explanations belong in the published MkDocs docs, not here.
