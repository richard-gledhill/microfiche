# Plan

The current piece of work: what is being built, how, and what is left. One piece of work at a time.

| File | What it is |
|---|---|
| `SPEC.md` | The technical spec for the current piece of work. Links to its source in [`../requirements/`](../requirements/README.md) and references `conventions.md`, `constraints.md` and `testing/` instead of restating them; it records only what is specific to this work. |
| `plan.md` | The implementation plan for `SPEC.md`. |
| `todo.md` | The task list for the plan. |
| [`archive/`](archive/README.md) | Finished work, one folder each. |

## Lifecycle

1. Write `SPEC.md`, then `plan.md` and `todo.md`. If this folder already holds an unfinished plan for different work,
   stop and ask before replacing it.
2. Build against them. Decisions that outlive the work become ADRs in [`../adr/`](../adr/README.md).
3. When the work ships, move `SPEC.md`, `plan.md` and `todo.md` together into `archive/YYYY-MM-<feature>/` (for
   example `archive/2026-10-mvp/`), and set the requirement's status to `Done`.
4. Start the next piece of work with a fresh `SPEC.md`.
