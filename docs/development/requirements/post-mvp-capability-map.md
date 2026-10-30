# Post-MVP capability map

Status: Draft

The features proposed for after `v0.1.6`, one requirement each, with the order to build them in. This map is the index:
a feature is picked up by its id, and its requirement is `<id>-prd.md` in this folder. Ids are stable and are not
renamed once a requirement is accepted.

The theme, in order: **adoption** for a new library, **trust** in what is filed automatically, **less review work**, then
the **automation and integrity** groundwork that makes unattended filing safe. Bug fixes raised as RFCs after the map
was drafted (RFC-009 to RFC-011) are slotted in where they unblock or protect a feature.

The **#** is the feature's number in its requirement doc and does not change; **Step** is the build order. A bug fix
has no requirement doc yet: its RFC is the source until its questions are settled, then it is specified like a
feature.

| Step | # | Id | Requirement | Theme | Depends on | Status |
|---|---|---|---|---|---|---|
| 1 | 1 | `library-init` | [`init`: set up, check and edit a library's configuration](library-init-prd.md) | Adoption | — | Done |
| 2 | — | `ai-provider-setup` | [RFC-009: Ollama model setting, failure tips and a pre-run AI check](../rfcs/RFC-009-ollama-model-setting.md) | Bug fix | — | Done ([ADR-004](../adr/ADR-004-ai-provider-setup.md), PR #95) |
| 3 | 2 | `matching-precision` | [Word-boundary matching and an ambiguity margin](matching-precision-prd.md), starting with [RFC-010: folder-name normalisation](../rfcs/RFC-010-folder-name-matching.md) | Trust, bug fix | — | Done ([ADR-005](../adr/ADR-005-folder-name-matching.md), [ADR-006](../adr/ADR-006-ambiguity-margin.md)) |
| 4 | — | `empty-group-filing` | [RFC-011: groups with no category folders](../rfcs/RFC-011-groups-without-categories.md) | Bug fix | `matching-precision` (same classifier code) | Done ([ADR-007](../adr/ADR-007-leaf-groups.md)) |
| 5 | 3 | `hint-learning` | [Learn keyword hints from review choices](hint-learning-prd.md) | Less review work | `matching-precision` | Draft |
| 6 | 4 | `ai-second-opinion` | [Ask the AI about hint-level matches](ai-second-opinion-prd.md) | Less review work | `matching-precision`, `ai-provider-setup` | Draft |
| 7 | 5 | `scriptable-output` | [`--json` output and filing without the prompts](scriptable-output-prd.md) | Automation groundwork | — | Draft |
| 8 | 6 | `drift-check` | [Background drift check](drift-check-prd.md) | Integrity | — | Draft |
| 9 | 7 | `watch-mode` | [Sort as files arrive](watch-mode-prd.md) | Zero-touch filing | `matching-precision`, `hint-learning`, `scriptable-output`, `drift-check` | Draft |

**Build order:** `library-init` (done) → `ai-provider-setup` → `matching-precision` (RFC-010 first) →
`empty-group-filing` → `hint-learning`, `ai-second-opinion` (either order) → `scriptable-output` → `drift-check` →
`watch-mode`.

Why this order:

- **`library-init` first.** Every new user meets it, it is self-contained, and it ends silent runs on defaults. Its
  settings walk-through also gives the later features' new settings (the ambiguity margin, learning, AI verification)
  a place to be changed without editing TOML. Shipped in PR #75.
- **`ai-provider-setup` next.** It is a defect in what already ships: with `[ai] model = ""`, Ollama silently uses a
  hard-coded `llama3` nobody chose, and when that model is missing the user gets a raw `ResponseError` part-way through
  a run, which `-q` hides. It is small and confined to `ai/` and the CLI's AI setup.
  - *Quick win carried with it:* `LLMClassifier.resolve_category` asks the AI even when a group has no categories
    (an empty list in the prompt). Skipping that call is a one-line guard, independent of RFC-011's decisions.
- **`matching-precision` before anything that changes what gets filed.** A confident misfile does the most damage to
  trust, and calibration shows a higher threshold cannot prevent one ([calibration.md](../testing/calibration.md#summary)).
  `hint-learning` and `ai-second-opinion` are measured against the corrected rules.
  - *RFC-010 folded in as its first slice.* Folder names written `kebab-case`, `snake_case`, `CamelCase` or with a
    `01-` prefix never match by name today, so their documents go to review for no visible reason. Normalising names
    and text first also removes the `\b` problem with `R&D` and `C++` that the word-boundary work would otherwise
    have to work around, and one calibration run covers both.
- **`empty-group-filing` after `matching-precision`, before `hint-learning`.** Nothing is misfiled today, so it is less
  urgent than the steps above, and it needs decisions first (a setting or always on, placeholder groups, `attachments`
  in the default exclusions). It touches the same classifier code as `matching-precision`, so it follows it, and it
  goes before `hint-learning` so the review queue that learning trains on is not padded with these units.
- **`ai-second-opinion` after `ai-provider-setup`.** Its requirement asks for a model-availability check before the first
  document; RFC-009's pre-run check covers that more fully. When RFC-009 is accepted, that requirement should be
  removed from [ai-second-opinion-prd.md](ai-second-opinion-prd.md) and the PRD should depend on `ai-provider-setup`
  instead.
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
- [Filing target mode (`file_at`)](../rfcs/RFC-004-filing-target-mode.md); [RFC-011](../rfcs/RFC-011-groups-without-categories.md)
  is its narrow special case and is planned above.
- [Decision-model classifier](../rfcs/RFC-005-decision-model-classifier.md)
- Renaming on collision ([mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp)): sending a collision to review is the
  safer default.

## How a feature moves through the docs

1. Its requirement here moves from `Draft` to `Accepted` when the owner agrees it is ready to build. A bug fix's RFC
   moves to `Accepted` once its questions are settled, with the outcome recorded as an ADR.
2. The work is specified in [`../plan/SPEC.md`](../plan/README.md), which links to the requirement (or RFC and ADR), then
   planned in `plan.md` and `todo.md`. One feature at a time.
3. A decision that outlives the work becomes an ADR in [`../adr/`](../adr/README.md).
4. When it ships, the plan is archived, the requirement is set to `Done`, and
   [mvp-roadmap.md](mvp-roadmap.md) and [architecture/](../architecture/README.md) are updated in the same change. Any
   backlog entry or roadmap item it absorbed is removed there and links here instead.
