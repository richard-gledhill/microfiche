# Feature backlog

Features taken out of the MVP on purpose, and ideas for beyond it. Each one is a draft RFC in this folder, with enough
detail to bring it back: why it was deferred, what was removed and where to restore it from, the design to keep, and
the questions to settle before building it. Entries are placeholders, not commitments: none is tied to a release or
can block one, and they are not in priority order. See [README.md](README.md) for how an RFC is numbered and decided.

## Where a deferred or future item goes

Record an item once, in the first row that fits, and link to it from anywhere else.

| The item is... | It goes in |
|---|---|
| What the product should do, ready to specify | A new doc in [requirements/](../requirements/README.md); the work itself is specified in [plan/](../plan/README.md) |
| A gap, an improvement to what is built, or a small postponed item (OCR, a lock timeout, watch mode) | [mvp-roadmap.md](../requirements/mvp-roadmap.md#future-work-and-deferred-beyond-mvp) |
| A feature outside the MVP with a design to keep, code removed from the MVP, or an idea that needs specifying | A new `RFC-NNN-title.md` in this folder, listed below |

When an RFC is picked up, what the product should do moves to a requirement in
[requirements/](../requirements/README.md), the decision is recorded as an ADR, and the RFC's status is set (see
[README.md](README.md)). The [MVP build plan](../plan/archive/2026-10-mvp/plan.md) is archived; what it left open is in
[mvp-followups-prd.md](../requirements/mvp-followups-prd.md).

## The RFCs

| RFC | Status | What it is |
|---|---|---|
| [RFC-001: Plugin architecture](RFC-001-plugin-architecture.md) | Draft | How integrations plug into microfiche without `core` depending on them; requirements only, no design |
| [RFC-002: Obsidian integration](RFC-002-obsidian-integration.md) | Draft | `index.md` folder notes and `TagIndex.md` tag governance, removed from the MVP; to be the first plugin |
| [RFC-003: Opt-in flatten when the depth is reduced](RFC-003-opt-in-flatten.md) | Draft | A `reclassify` mode that moves items up after `depth` is lowered |
| [RFC-004: Filing target mode (`file_at`)](RFC-004-filing-target-mode.md) | Draft | File into the deepest confident level instead of sending the unit to review |
| [RFC-005: Decision-model classifier](RFC-005-decision-model-classifier.md) | Draft | A classifier that returns one option with a probability, beside the chat model |
| [RFC-006: Subcategories (depth 3)](RFC-006-subcategories-depth-3.md) | Draft | A third library level, gated on a calibration measurement |
| [RFC-007: Library creation (`init`) and group templates](RFC-007-group-templates.md) | Draft | Named group templates; `init` itself is built |
| [RFC-008: OCR for scanned PDFs](RFC-008-ocr-scanned-pdfs.md) | Draft | Read scanned PDFs that have no text layer |
| [RFC-009: Ollama model setting, failure tips and pre-run AI check](RFC-009-ollama-model-setting.md) | Accepted ([ADR-004](../adr/ADR-004-ai-provider-setup.md)) | No hardcoded Ollama model, a fix-it tip when the AI provider fails, and a hello-world check before `--use-ai` runs |
| [RFC-010: Folder-name matching](RFC-010-folder-name-matching.md) | Accepted ([ADR-005](../adr/ADR-005-folder-name-matching.md)) | Match folder names written with `-`, `_`, camelCase, `&` or other special characters, without lowering confidence; precedes the word-boundary work |
| [RFC-011: Groups without categories](RFC-011-groups-without-categories.md) | Accepted ([ADR-007](../adr/ADR-007-leaf-groups.md)) | At depth 2, file straight into a group that has no category folders instead of sending the unit to review; the narrow case of RFC-004 |
| [RFC-012: OpenAI-compatible AI hosts](RFC-012-openai-compatible-hosts.md) | Draft | An `[ai] base_url` for the `openai` provider so hosted services and local servers with an OpenAI-compatible API (and a key) work; the notice names the host |
