# Development docs

Internal planning/design docs — not published to the user-facing docs site (see
`exclude_docs` in [mkdocs.yml](../../mkdocs.yml)).

- **[architecture.md](architecture.md)** — current. Describes the architecture as actually
  implemented; update it in place as decisions change, rather than adding a new dated file.
- **[mvp-roadmap.md](mvp-roadmap.md)** — current. What's done/partial/stub per CLI command and
  feature, the prioritized list of what's actually blocking MVP, and the future and deferred work.
- **[mvp-build-plan.md](mvp-build-plan.md)** — current. A staged, from-scratch process for
  building to MVP (six stages plus interim stages 4.1 to 4.10, each Plan/Design/Build/Test/Deploy), written to be dropped
  into a GitHub Project. A different lens than `mvp-roadmap.md`: process/sequencing rather
  than status. Covers the MVP only.
- **[feature-backlog.md](feature-backlog.md)** — current. Where a deferred or future item goes, and the features kept
  for beyond the MVP, with the design and where to restore removed code from: the Obsidian integration and the plugin
  architecture it should be built on.
- **[config-review.md](config-review.md)** — planned work. A review of the configuration: which hard-coded
  constants should become settings, `keep_folders`, a packaged defaults file, AI settings, and moving category
  hints out of the TOML into a library JSON file. Feeds Stage 4.1 of the build plan.
- **[operations-review.md](operations-review.md)** — planned work. A review of robustness and diagnostics against
  typical CLI file-organiser practice: name collisions, failure isolation, `sort --dry-run`, a run lock, logging,
  release packaging. Feeds Stages 4.2 to 4.4 and Stage 6 of the build plan.
- **[ai-classifier-options.md](ai-classifier-options.md)** — planned work. Chat-model versus decision-model
  classifiers for the AI fallback, the candidates (Jev, Clef, Nimble, none yet verified) and the rules for adopting
  one. Feeds the decision-model classifier in the feature backlog, under review.
- **[fuzzy-matching-options.md](fuzzy-matching-options.md)** — planned work. What `thefuzz` is (a wrapper over
  RapidFuzz), what was measured, the traps in switching, and why to switch as the last step of Stage 4.1.
- **[library-depth.md](library-depth.md)** — planned work. Library depth (one, two or three levels), non-library
  folders such as bundles filed by `keep_folders`. Feeds Stages 4.6 to 4.8; the optional filing target mode it
  once covered is in the feature backlog, under review.
- **[calibration.md](calibration.md)** — current. How the default confidence threshold was measured: the
  corpus and harness in `tests/calibration/`, the results, what they mean, and how to repeat them on your
  own documents.
- **[CONTEXT.md](../../CONTEXT.md)** — current. The project's domain glossary (library, group, category,
  unit, job, ledger, ...) and the words to avoid. Use these terms in code, docs and reviews.
- **[data-model.md](data-model.md)** — current. The ledger, `AuditEvent`/`Job` schemas,
  `audit.log` format and `.microfiche/` directory layout, as one authoritative page.
- **[module-diagram.md](module-diagram.md)** — two Mermaid diagrams: the module import graph, generated from
  the actual source imports by `make module-diagram` (not hand-maintained prose), and the `sort` pipeline's
  runtime data flow, written by hand (including what's implemented but not yet wired in, e.g. the `review` queue).
  Regenerate the graph rather than hand-edit it if it drifts.
- **[archive/](archive/)** — superseded design history, kept for context but not authoritative.
  Reading order: the original PRD → a three-option concepts brainstorm → concept 1a (SQLite-backed)
  → concept 1b (revised to filesystem-as-source-of-truth) → superseded by `architecture.md`.
- **[readme-template.md](readme-template.md)** — a reusable best-practices `README.md` template,
  not planning history.
- **[scratch.md](scratch.md)** — a personal notebook of snippets and commands worth keeping from guided
  build sessions. Not part of the product or the design record.
