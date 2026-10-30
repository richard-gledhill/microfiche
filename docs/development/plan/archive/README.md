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
| [2026-10-word-boundary-matching/](2026-10-word-boundary-matching/SPEC.md) | `matching-precision`, slice A ([matching-precision-prd.md](../../requirements/matching-precision-prd.md)): group names, category names, hints and fuzzy group matches count only as whole words. The ambiguity margin follows in its own plan. |
| [2026-10-ambiguity-margin/](2026-10-ambiguity-margin/SPEC.md) | `matching-precision`, slice B ([matching-precision-prd.md](../../requirements/matching-precision-prd.md), [ADR-006](../../adr/ADR-006-ambiguity-margin.md)): `[classification] ambiguity_margin` holds a group or category stage when the evidence for two folders is too close to call. Completes `matching-precision`. |
| [2026-10-empty-group-filing/](2026-10-empty-group-filing/SPEC.md) | `empty-group-filing` ([RFC-011](../../rfcs/RFC-011-groups-without-categories.md), [ADR-007](../../adr/ADR-007-leaf-groups.md)): `[sorting] file_in_empty_groups` files a document that names a depth-2 group with no category folders straight into that group; `attachments` joins the default exclusions. |
