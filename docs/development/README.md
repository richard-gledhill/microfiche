# Development docs

Internal planning/design docs — not published to the user-facing docs site (see
`exclude_docs` in [mkdocs.yml](../../mkdocs.yml)).

- **[architecture.md](architecture.md)** — current. Describes the architecture as actually
  implemented; update it in place as decisions change, rather than adding a new dated file.
- **[mvp-roadmap.md](mvp-roadmap.md)** — current. What's done/partial/stub per CLI command and
  feature, and the prioritized list of what's actually blocking MVP.
- **[mvp-build-plan.md](mvp-build-plan.md)** — current. A staged, from-scratch process for
  building to MVP (six stages, each Plan/Design/Build/Test/Deploy), written to be dropped
  into a GitHub Project. A different lens than `mvp-roadmap.md`: process/sequencing rather
  than status.
- **[data-model.md](data-model.md)** — current. The sidecar JSON, `AuditEvent`/`Job` schemas,
  and `.logs/` directory layout, as one authoritative page.
- **[archive/](archive/)** — superseded design history, kept for context but not authoritative.
  Reading order: the original PRD → a three-option concepts brainstorm → concept 1a (SQLite-backed)
  → concept 1b (revised to filesystem-as-source-of-truth) → superseded by `architecture.md`.
- **[readme-template.md](readme-template.md)** — a reusable best-practices `README.md` template,
  not planning history.
