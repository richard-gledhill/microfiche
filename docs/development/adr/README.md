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
| [ADR-004](ADR-004-ai-provider-setup.md) | AI provider setup: no default model, fix-it tips, pre-run check | Accepted |
| [ADR-005](ADR-005-folder-name-matching.md) | Folder-name matching compares a normalised spelling | Accepted |
| [ADR-006](ADR-006-ambiguity-margin.md) | Ambiguity margin: hold a stage when the evidence is too close to call | Accepted |
| [ADR-007](ADR-007-leaf-groups.md) | File into a group that has no category folders (opt-in setting) | Accepted |
| [ADR-008](ADR-008-hint-learning.md) | Learn keyword hints from review choices (opt-in) | Accepted |
| [ADR-009](ADR-009-ai-second-opinion.md) | Let the AI check low-confidence rules answers (opt-in) | Accepted |
| [ADR-010](ADR-010-scriptable-output.md) | A JSON output contract and a non-interactive `file` command | Accepted |
| [ADR-011](ADR-011-drift-check.md) | Notice files moved by hand, in the commands that already read the library | Accepted |
| [ADR-012](ADR-012-watch-mode.md) | Watch mode polls the inbox and files what has stopped changing | Accepted |

ADR-001 to ADR-003 were written as reviews before this folder existed; each keeps the review below its decision.
