# Architecture decision records

One file per decision, named `ADR-NNN-title.md` (for example `ADR-001-configuration-layout.md`). Numbers are
sequential: continue the existing sequence. ADRs are never deleted; a reversed decision gets a new ADR that supersedes
the old one, and the old one's status says so.

Each ADR opens with its status, date and the decision in a few lines, then records the context, the alternatives
considered and why they lost, and the consequences. The `.adr-dir` file at the repo root points ADR tools here.

| ADR | Decision | Status |
|---|---|---|
| [ADR-001](ADR-001-configuration-layout.md) | Configuration layout: packaged defaults, settings vs. library file | Accepted |
| [ADR-002](ADR-002-switch-to-rapidfuzz.md) | Switch from `thefuzz` to `rapidfuzz` | Accepted |
| [ADR-003](ADR-003-operational-safety.md) | Operational safety: collisions, duplicates, moves, run lock, failure isolation | Accepted |

ADR-001 to ADR-003 were written as reviews before this folder existed; each keeps the review below its decision.
