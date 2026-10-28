# Archive

Finished work, one folder per piece: `YYYY-MM-<short-name>/`, for example `2026-10-mvp/`.

Each folder holds the `SPEC.md`, `plan.md` and `todo.md` that were moved here together from [`../`](../README.md) when
the work shipped. Never split them up, and don't edit them after archiving (fixing a link broken by a later move is
fine).

| Folder | What it is |
|---|---|
| [2026-10-mvp/](2026-10-mvp/plan.md) | The staged MVP build plan (Stages 1 to 6, with interim stages 4.1 to 4.10), shipped as `v0.1.6`. It predates the `SPEC.md`/`todo.md` workflow, so it is a `plan.md` only. What it left open is in [mvp-followups-prd.md](../../requirements/mvp-followups-prd.md). |
| [2026-10-library-init/](2026-10-library-init/SPEC.md) | `microfiche init` (post-MVP feature 1, [library-init-prd.md](../../requirements/library-init-prd.md)): set up, check and edit a library's configuration, and stop `sort`, `reclassify` and `propose-categories` without one. |
| [2026-10-ai-provider-setup/](2026-10-ai-provider-setup/SPEC.md) | `ai-provider-setup` (post-MVP step 2, [RFC-009](../../rfcs/RFC-009-ollama-model-setting.md), [ADR-004](../../adr/ADR-004-ai-provider-setup.md)): no default AI model, fix-it tips for provider failures, and a pre-run AI check. |
| [2026-10-folder-name-matching/](2026-10-folder-name-matching/SPEC.md) | `matching-precision`, first slice ([RFC-010](../../rfcs/RFC-010-folder-name-matching.md), [ADR-005](../../adr/ADR-005-folder-name-matching.md)): folder names, hints and text compared in one normalised spelling (`normalise_names`). Word boundaries and the ambiguity margin follow in their own plans. |
