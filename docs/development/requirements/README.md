# Requirements

What the product should do and why: PRDs, product briefs and user stories. Written and owned by people, and
long-lived: a requirement outlasts the plans that build it.

- Name each doc `<feature>-prd.md`, for example `auth-flow-prd.md`.
- Start each doc with a status line: `Status: Draft`, `Accepted`, `Done` or `Superseded`. Update it when the work
  ships (`Done`) or a newer doc replaces it (`Superseded`, linking the replacement).
- Move an abandoned or superseded doc to `archive/` rather than deleting it.

The technical spec for the work goes in [`../plan/SPEC.md`](../plan/README.md), which links back to its requirement
here. Agents don't edit an existing doc here without asking, and create a new one only when asked.

| Doc | Status |
|---|---|
| [mvp-followups-prd.md](mvp-followups-prd.md): what the MVP build plan left open | Draft |
| [archive/](archive/): the original PRD (2026-07-07) and the concept docs that followed it, superseded by [architecture/overview.md](../architecture/overview.md). Reading order: the PRD, the concepts brainstorm, concept 1a (SQLite-backed), then concept 1b (the filesystem as the source of truth). | Superseded |
