# `--json` output and filing without the prompts

Status: Draft

- **Id:** `scriptable-output` ([capability map](post-mvp-capability-map.md), #5)
- **Depends on:** nothing

## Why

Every command prints for a person, and `review` needs a terminal. Nothing can be scripted: a user cannot file a held
document from a script, a shortcut or another tool, and watch mode and integrations have no stable output to act on.
A machine-readable surface is the groundwork for both.

## User stories

- As a user with a script or shortcut, I want to file one held document into a folder I choose, with the same safety
  checks as `review`.
- As a developer integrating microfiche, I want `sort`, `reclassify`, `audit` and `review`'s queue as JSON, with a
  documented shape that does not change without notice.

## Requirements

**Must**
- `--json` on `sort` (including `--dry-run`), `reclassify`, `audit` and `config` writes one JSON document to stdout and
  nothing else there. Warnings and progress go to stderr or are suppressed.
- The JSON includes what the human output shows: filed, needs-review, duplicates and failures, each with its reasons,
  and the job id.
- A JSON Schema for each output is generated from the models and committed, with a test that fails when it is stale (as
  for `microfiche-library.schema.json`).
- A non-interactive command (`microfiche file <unit> --to <group>[/<category>]`, name to confirm) files one inbox unit
  through the same checks and the same one-job commit as `review`, recorded as `classified_by = "user"`.
- Exit codes are unchanged and documented; a refused choice (collision, duplicate, unknown folder) exits non-zero with
  the reason in the JSON.
- No document text in the JSON.

**Should**
- `review --list --json` prints the review queue without prompting.
- A `version` field in each JSON document.

**Won't (this time)**
- Structured log output ([mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp)).
- An HTTP API.

## Acceptance criteria

- `sort --dry-run --json` output parses, validates against its schema, and lists every inbox unit once.
- `file` of a held document into an existing category files it as one job that `rollback --last` undoes.
- `file` into a taken name, onto a duplicate, or into a folder that does not exist is refused with a non-zero exit and
  the reason.
- `docs/how-to-use.md`, the README and `docs/cli-reference.md` document `--json` and `file`.
- `make check` and `make test` pass.

## Technical outline

Guidance for the spec, not binding.

- `SortReport` and the reclassify result types are dataclasses holding `Path`s; serialise them through explicit
  Pydantic output models in `cli` (not `core`), so the JSON shape is a deliberate contract and can be schema-generated.
- `file` builds a `ReviewSession` (`start`, `decide`, `commit` in `core/review.py`), so the checks are written once.

## Related

- [mvp-roadmap.md](mvp-roadmap.md#deferred-beyond-mvp): "`--json` output for scripting".
- [mvp-roadmap.md](mvp-roadmap.md#release-stage-6): "`review` cannot be scripted".

## Open questions

- Is the JSON shape versioned with the package, or separately?
- Should `file` accept several units in one call (one job)?
