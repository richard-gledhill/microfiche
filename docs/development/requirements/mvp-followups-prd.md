# MVP follow-ups

Status: Draft

The items the [MVP build plan](../plan/archive/2026-10-mvp/plan.md) left open when it was archived after `v0.1.6`
(released 2026-10-14): unfinished release steps, and everything a stage recorded as **Deferred**. They are collected
here so nothing is lost with the archive. None is scheduled; each needs a spec in [`../plan/`](../plan/README.md)
before it is built.

Where an item is already tracked elsewhere, the last column links to it, and that doc stays the source of truth for its
design. When an item is picked up or dropped, update it here and in the linked doc in the same change.

## Release close-out (Stage 6)

| # | Item | Why it is open | Tracked in |
|---|---|---|---|
| R1 | Publish the documentation site for the tagged release | GitHub Pages is not enabled for the repository, so the site has not been published | — |
| R2 | Check `gh release download` against the `v0.1.6` release | Listed as "still to do after the release exists"; the release has both wheels attached, but the download-and-install check was not recorded | — |
| R3 | Raise the coverage floor (`fail_under = 95`) | It starts at 95 so a branch one OS does not run cannot fail the build, and was to be raised once the Linux figure is known | — |

## Deferred from the build stages

| # | Item | From | Tracked in |
|---|---|---|---|
| D1 | An `init` command and a template catalog | Stage 4.1 | [feature-backlog.md](../rfcs/feature-backlog.md#library-creation-init-and-group-templates); `init` in [library-init-prd.md](library-init-prd.md) |
| D2 | A `command` AI provider (needs a decision on running commands from a config inside a shared library) | Stage 4.1 | [architecture/overview.md §10](../architecture/overview.md#10-configuration-layout) |
| D3 | Per-group hint overrides. A named group entry in the library file now adds its own hints to the `*` entry's, so confirm what, if anything, is still missing before building | Stage 4.1 | — |
| D4 | Renaming on collision (a suffix setting) | Stage 4.2 | [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp) |
| D5 | Moving duplicates to `_sorting/duplicates/` (a `[sorting] duplicates = "leave" \| "quarantine"` setting, which needs a scanner skip rule and its own collision handling) | Stage 4.2 | [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp) |
| D6 | Duplicate checking of folder units kept whole | Stage 4.2 | [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp) |
| D7 | A persistent hash cache keyed by path, size and modification time | Stage 4.2 | [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp) |
| D8 | A hash of the parsed text, to catch a re-saved copy whose bytes differ | Stage 4.2 | — |
| D9 | A lock timeout or `--force` override for the run lock | Stage 4.3 | [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp); the timeout in [watch-mode-prd.md](watch-mode-prd.md) |
| D10 | Nested-library detection | Stage 4.3 | [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp) |
| D11 | Structured (JSON) log output, and log shipping | Stage 4.4 | [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp) |
| D12 | Detecting folders moved by hand that the ledger doesn't know about (a bundle moved by hand is split by `reclassify`; pinned by a test) | Stage 4.8 | [mvp-roadmap.md](mvp-roadmap.md#release-stage-6) (known limit), and the `doctor` / `verify` command in [Deferred beyond MVP](mvp-roadmap.md#deferred-beyond-mvp); [drift-check-prd.md](drift-check-prd.md) |
| D13 | A description or aliases per library file entry, and sending them to the AI (a privacy decision) | Stage 4.10 | — |
| D14 | A Markdown way to read and write the library file's model | Stage 4.10 | — |
| D15 | Rename detection beyond reporting a possible rename | Stage 4.10 | — |
| D16 | Creating folders from the library file | Stage 4.10 | — |
| D17 | A `sort --dry-run` preview that shows what the library file sync would add | Stage 4.10 | [mvp-roadmap.md](mvp-roadmap.md#configuration-consolidation-stage-41) (Stage 4.10, "Still open") |
| D18 | Ranked suggestions in `review` from a decision model | Stage 5 | [feature-backlog.md](../rfcs/feature-backlog.md#decision-model-classifier) |
| D19 | An extra `review` prompt per level at depth 3 | Stage 5 | [feature-backlog.md](../rfcs/feature-backlog.md#subcategories-depth-3) |
| D20 | Going back to an item in `review` once it is passed | Stage 5 | [mvp-roadmap.md](mvp-roadmap.md#review-stage-5) |
| D21 | Learning hints from `review` choices | Stage 5 | [mvp-roadmap.md](mvp-roadmap.md#review-stage-5); [hint-learning-prd.md](hint-learning-prd.md) |
