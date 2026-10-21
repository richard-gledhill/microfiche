# RFC-001: Plugin architecture

Status: Draft

**Background:** not started. Requirements only; there is no design and, deliberately, no code.
**Future feature update** (2026-10-19): drafted as a post-MVP requirement, then moved back to the feature backlog to be built after the
[post-MVP features](../requirements/post-mvp-capability-map.md). What the draft added is under
[Requirements drafted for it](#requirements-drafted-for-it).

**Why.** Obsidian is the first integration, and likely not the last (other note-taking or document tools). Integrating
each of them by adding modules and a config section to `core` would grow `core` with every tool and make each one
a permanent part of the product.

**Why not now.** [AGENTS.md](../../../AGENTS.md) says to add a seam only where something actually varies, and one
implementation is not a seam. With zero integrations in the MVP there is nothing to vary, and a framework designed
first would be shaped by guesses. Design it when the first integration is built, using that integration as the
test of the interface, and check it against a second use before treating it as stable.

## Requirements to design against

- **`core` does not depend on any integration.** The dependency points one way: an integration depends on `core`.
  The repo is already a uv workspace of `core` and `cli`, so an integration could be a third package (for example
  `packages/obsidian`) without `core` changing. This is an option, not a decision.
- **Extension points** the Obsidian work needs, in the order it needs them:
  1. A hook when a job finishes: sort, `reclassify --apply` and `rollback`, receiving the job and the folders it touched.
  2. A source of tag vocabulary, if tag governance returns.
  3. Settings of its own, validated like the rest of the config (an unknown setting is an error), under a namespace
     that cannot collide with core's sections.
  4. Optionally, a command of its own (such as the old `index`), registered without editing `cli/app.py`.
- **A plugin cannot break the core promise.** A plugin that fails must not fail, abort or half-apply a sort, and must
  not make a job impossible to roll back. This follows the existing per-unit failure isolation.
- **What a plugin writes must be accounted for.** Anything written into the library is either recorded in the job
  (so `rollback` undoes it) or recognisably generated (so `reclassify` and the duplicate check ignore it).
- **Off by default, explicit when on.** Same rule as the OpenAI provider: nothing that changes the library or sends
  data elsewhere runs unless the user turned it on, and a run says so.
- **Discovery.** How a plugin is found (a setting naming it, a Python entry point, or being installed at all) is
  open. Prefer the simplest thing that works for one plugin in the same repo.

## Requirements drafted for it

From the post-MVP draft (2026-10-19), to carry into a requirement when this is picked up:

- One extension point: a hook after a job finishes, covering `review` commits as well as `sort`, `reclassify --apply`
  and `rollback`.
- The hook receives a small summary type (the job id, the kind of run, the folders touched), not the `Job` model.
- Discovery by Python entry point (`microfiche.plugins`) is the likely simplest option; record the choice as an ADR.
- A run says which plugins ran. A plugin's settings live under its own namespace and are validated.
- The Obsidian modules are restored from `551eec9` into a `packages/obsidian` workspace package.
- Acceptance: with the Obsidian plugin on, a sort regenerates `index.md` in each folder it filed into; with it off,
  nothing is written; a plugin that raises leaves the job filed and rollback-able with one warning; `reclassify` and
  the duplicate check skip the generated notes.

## Tests it will need

Restore the removed `index.md` and tag governance tests, and add tests that the hook runs after sort, reclassify and
rollback, that a failing plugin does not fail a sort, and that `reclassify` and the duplicate check ignore generated
notes.

## Open questions

- Is an integration a separate package, or a module behind an optional extra like `ai`?
- Does the hook receive the `Job` model directly (coupling a plugin to its schema), or a smaller summary type?
- Do plugins need ordering or dependencies, or is one at a time enough?
- Should `review` (Stage 5) expose any hook, so that choices made there can feed a plugin? Probably not until a
  plugin needs it.
