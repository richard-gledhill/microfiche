# Request for Change

A request for change (RFC) is a design question discussed before it is built: what to change, the options, and the
questions to settle.

**Tracker: TBC.** A GitHub Project for microfiche is not set up yet. Until it is, RFCs are stored here as local files:

- One file per RFC, named `RFC-NNN-title.md` (for example `RFC-001-plugin-architecture.md`), numbered in sequence.
- Start each file with a status line: `Status: Draft`, `Discussion`, `Accepted`, `Rejected` or `Superseded`.
- When an RFC is decided, record the outcome as an ADR in [`../adr/`](../adr/README.md), link the ADR and the RFC to
  each other, and set the RFC's status. Never delete an RFC; a rejected one keeps its reasoning. Once an accepted RFC's work has shipped, move it to
  [`archive/`](archive/) and fix the links to it; the index below keeps its row, pointing there.

When a GitHub Project is set up, the tracker becomes the single source of truth: new RFCs are GitHub issues labelled
`rfc`, local files are no longer added, and each open local RFC is moved to an issue and
linked from here.

| File | What it is |
|---|---|
| [feature-backlog.md](feature-backlog.md) | The index of the RFCs below, with their status, and where a deferred or future item goes. |
| [RFC-001-plugin-architecture.md](RFC-001-plugin-architecture.md) | Plugin architecture: how integrations plug in without `core` depending on them. |
| [RFC-002-obsidian-integration.md](RFC-002-obsidian-integration.md) | Obsidian integration: folder notes and tag governance, removed from the MVP, with where to restore them from. |
| [RFC-003-opt-in-flatten.md](RFC-003-opt-in-flatten.md) | Opt-in flatten when the library's depth is reduced. |
| [RFC-004-filing-target-mode.md](RFC-004-filing-target-mode.md) | Filing target mode (`[sorting] file_at`). |
| [RFC-005-decision-model-classifier.md](RFC-005-decision-model-classifier.md) | Decision-model classifier for the AI fallback. |
| [RFC-006-subcategories-depth-3.md](RFC-006-subcategories-depth-3.md) | Subcategories (depth 3). |
| [RFC-007-group-templates.md](RFC-007-group-templates.md) | Library creation and group templates, with the removed code and where to restore it from. |
| [RFC-008-ocr-scanned-pdfs.md](RFC-008-ocr-scanned-pdfs.md) | OCR for scanned PDFs. |
| [RFC-009-ollama-model-setting.md](archive/RFC-009-ollama-model-setting.md) | Ollama model setting, fix-it tips for AI provider failures, and a pre-run AI check. |
| [RFC-010-folder-name-matching.md](archive/RFC-010-folder-name-matching.md) | Folder-name matching: separators, case styles and special characters. |
| [RFC-011-groups-without-categories.md](archive/RFC-011-groups-without-categories.md) | Groups with no category folders: file straight into the group. |
| [RFC-012-openai-compatible-hosts.md](RFC-012-openai-compatible-hosts.md) | OpenAI-compatible AI hosts: a `base_url` so any service or local server with that API works. |
| [RFC-013-manual-review-findings.md](RFC-013-manual-review-findings.md) | Findings from a manual review (`init` exclusions, `propose-categories`, depth-2 group filing, HTML, ambiguity), and a test plan for a real library. |
