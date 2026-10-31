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
| [mvp-roadmap.md](mvp-roadmap.md): what is implemented vs. partial or deferred, per command and feature, and the future and deferred work. A living status doc, edited in place, so it has no status line | Current |
| [mvp-followups-prd.md](mvp-followups-prd.md): what the MVP build plan left open | Draft |
| [post-mvp-capability-map.md](post-mvp-capability-map.md): the post-MVP features, their ids, dependencies and build order. Start here for what to build next | Draft |
| [library-init-prd.md](library-init-prd.md): 1. `init`: set up, check and edit a library's configuration | Done |
| [matching-precision-prd.md](matching-precision-prd.md): 2. word-boundary matching and an ambiguity margin | Done |
| [hint-learning-prd.md](hint-learning-prd.md): 3. learn keyword hints from review choices | Done |
| [ai-second-opinion-prd.md](ai-second-opinion-prd.md): 4. ask the AI about hint-level matches | Done |
| [scriptable-output-prd.md](scriptable-output-prd.md): 5. `--json` output and filing without the prompts | Done |
| [drift-check-prd.md](drift-check-prd.md): 6. background drift check | Done |
| [watch-mode-prd.md](watch-mode-prd.md): 7. sort as files arrive | Done |
| [archive/](archive/): the original PRD (2026-07-07) and the concept docs that followed it, superseded by [architecture/overview.md](../architecture/overview.md). Reading order: the PRD, the concepts brainstorm, concept 1a (SQLite-backed), then concept 1b (the filesystem as the source of truth). | Superseded |
