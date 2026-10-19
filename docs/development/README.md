# Development docs

Everything about *building* microfiche lives here. This folder is excluded from the MkDocs site
(`exclude_docs` in [mkdocs.yml](../../mkdocs.yml)), so nothing in it is published. Anything users should read belongs in
the MkDocs part of `docs/`, one level up.

| Path | What goes there |
|---|---|
| [`constraints.md`](constraints.md) | The measured, tool-enforced quality bar: the gates, type checking, lint, coverage, and never silencing a check. Read before writing code; never weaken it to make a change pass. |
| [`conventions.md`](conventions.md) | The judgement-based style guide: design, code, module layout, tests, docs and git. Read before writing code. |
| [`mvp-roadmap.md`](mvp-roadmap.md) | What is implemented vs. partial or deferred, per command and feature, plus future work and small postponed items. Check it before assuming a feature is wired. |
| [`feature-backlog.md`](feature-backlog.md) | Features outside the MVP with a design to keep, and code removed from the MVP with where to restore it from. |
| [`requirements/`](requirements/README.md) | PRDs, product briefs and user stories, with the original PRD and concept docs in `archive/`. |
| [`plan/`](plan/README.md) | The current piece of work (`SPEC.md`, `plan.md`, `todo.md`), plus an `archive/` of finished work, including the MVP build plan. |
| [`rfcs/`](rfcs/README.md) | A pointer only: RFCs are GitHub issues labelled `rfc`. |
| [`adr/`](adr/README.md) | Architecture decision records, `ADR-NNN-title.md`, sequential, never deleted. |
| [`architecture/`](architecture/README.md) | The design as built: overview, data model, module diagrams, library depth, AI classifier research. |
| [`testing/`](testing/README.md) | Test strategy and measurements, including the confidence-threshold calibration. |
| [`operations/`](operations/README.md) | Runbooks, rollback plans, postmortems. |

The domain glossary is [CONTEXT.md](../../CONTEXT.md) at the repo root; use its terms in code, docs and reviews.

## Where a new doc or item goes

| The item is... | It goes in |
|---|---|
| What the product should do, and why | A new `requirements/<feature>-prd.md` |
| A design question that needs discussion | An `rfc` issue |
| A decision that outlives the work | A new ADR in `adr/` |
| The spec, plan and tasks for the work in progress | `plan/` |
| A gap, an improvement to what is built, or a small postponed item | [mvp-roadmap.md](mvp-roadmap.md#future-work-and-deferred-beyond-mvp) |
| A feature outside the MVP with a design to keep, or code removed from it | [feature-backlog.md](feature-backlog.md) |
| How the system works as built | `architecture/`, updated in place |

Record an item once, and link to it from anywhere else.

## From requirement to shipped work

1. **Requirement**: a person writes `requirements/<feature>-prd.md` with `Status: Draft`, and marks it `Accepted`
   when it is ready to build.
2. **RFC**: a design question that needs discussion is raised as an `rfc` issue.
3. **ADR**: a decided RFC, or any decision that outlives the work, is recorded in `adr/` and linked both ways with
   its issue.
4. **Plan**: write `plan/SPEC.md`, linking its requirement, then `plan.md` and `todo.md`. Build against them.
5. **Archive**: when the work ships, move the spec, plan and todo together into `plan/archive/YYYY-MM-<feature>/` and
   set the requirement's status to `Done`. Update `architecture/` and `mvp-roadmap.md` in the same change. Start the
   next piece of work with a fresh `SPEC.md`.

`plan.md` and `todo.md` do not exist until a piece of work creates them. See [AGENTS.md](../../AGENTS.md) for the paths
agents must use.
