# Post-MVP capability map

Status: Draft

The features proposed for after `v0.1.6`, one requirement each, with the order to build them in. This map is the index:
a feature is picked up by its id, and its requirement is `<id>-prd.md` in this folder. Ids are stable and are not
renamed once a requirement is accepted.

The theme, in order: **adoption** for a new library, **trust** in what is filed automatically, **less review work**, then
the **automation and integrity** groundwork that makes unattended filing safe.

| # | Id | Requirement | Theme | Depends on |
|---|---|---|---|---|
| 1 | `library-init` | [`init`: set up, check and edit a library's configuration](library-init-prd.md) | Adoption | — |
| 2 | `matching-precision` | [Word-boundary matching and an ambiguity margin](matching-precision-prd.md) | Trust | — |
| 3 | `hint-learning` | [Learn keyword hints from review choices](hint-learning-prd.md) | Less review work | `matching-precision` |
| 4 | `ai-second-opinion` | [Ask the AI about hint-level matches](ai-second-opinion-prd.md) | Less review work | `matching-precision` |
| 5 | `scriptable-output` | [`--json` output and filing without the prompts](scriptable-output-prd.md) | Automation groundwork | — |
| 6 | `drift-check` | [Background drift check](drift-check-prd.md) | Integrity | — |
| 7 | `watch-mode` | [Sort as files arrive](watch-mode-prd.md) | Zero-touch filing | `matching-precision`, `hint-learning`, `scriptable-output`, `drift-check` |

**Build order:** `library-init` → `matching-precision` → `hint-learning`, `ai-second-opinion` (either order) →
`scriptable-output` → `drift-check` → `watch-mode`.

Why this order:

- **`library-init` first.** Every new user meets it, it is self-contained, and it ends silent runs on defaults. Its
  settings walk-through also gives the later features' new settings (the ambiguity margin, learning, AI verification)
  a place to be changed without editing TOML.
- **`matching-precision` before anything that changes what gets filed.** A confident misfile does the most damage to
  trust, and calibration shows a higher threshold cannot prevent one ([calibration.md](../testing/calibration.md#summary)).
  `hint-learning` and `ai-second-opinion` are measured against the corrected rules.
- **`hint-learning` before `watch-mode`.** Learning without prompts is what makes the review queue shrink on its own;
  watch mode then files more with no one watching.
- **`scriptable-output` and `drift-check` before `watch-mode`.** Unattended filing needs a machine-readable report to act
  on, and must notice when files were moved outside microfiche.

## Future feature updates

Planned after the features above, and kept in the [feature backlog](../rfcs/feature-backlog.md) with their design until
they are picked up:

- [OCR for scanned PDFs](../rfcs/RFC-008-ocr-scanned-pdfs.md): independent, so it can move earlier if
  scanned documents turn out to be common in real libraries.
- [Plugin architecture](../rfcs/RFC-001-plugin-architecture.md), with the
  [Obsidian integration](../rfcs/RFC-002-obsidian-integration.md) as its first plugin.

## Not planned

These stay in the backlog, under review, because none has a measured need and the features above address the same
problems more cheaply:

- [Subcategories (depth 3)](../rfcs/RFC-006-subcategories-depth-3.md)
- [Filing target mode (`file_at`)](../rfcs/RFC-004-filing-target-mode.md)
- [Decision-model classifier](../rfcs/RFC-005-decision-model-classifier.md)
- Renaming on collision ([mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp)): sending a collision to review is the
  safer default.

## How a feature moves through the docs

1. Its requirement here moves from `Draft` to `Accepted` when the owner agrees it is ready to build.
2. The work is specified in [`../plan/SPEC.md`](../plan/README.md), which links to the requirement, then planned in
   `plan.md` and `todo.md`. One feature at a time.
3. A decision that outlives the work becomes an ADR in [`../adr/`](../adr/README.md).
4. When it ships, the plan is archived, the requirement is set to `Done`, and
   [mvp-roadmap.md](mvp-roadmap.md) and [architecture/](../architecture/README.md) are updated in the same change. Any
   backlog entry or roadmap item it absorbed is removed there and links here instead.
