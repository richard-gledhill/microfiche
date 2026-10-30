# ADR-010: A JSON output contract and a non-interactive `file` command

- **Status:** Accepted
- **Date:** 2026-10-30
- **Decision:** `--json` prints one versioned JSON document to stdout, from explicit output models in `cli` with committed
  JSON Schemas; a new `microfiche file` command files held inbox units without prompts, through `ReviewSession`. Built in
  two PRs. See [Decisions](#decisions).
- **Source:** [scriptable-output-prd.md](../requirements/scriptable-output-prd.md)

## Context

Every command prints for a person and `review` needs a terminal, so nothing can drive microfiche: a shortcut cannot file a
held document, and `watch-mode` and integrations have no stable output to act on.

## Decisions

- **Two PRs.** A: `--json` on `sort` (including `--dry-run`), `reclassify`, `audit`, `config`, `rollback` and
  `review --list`. B: `file`, with its own JSON result.
- **Output models live in `cli`, not `core`.** `SortReport`, the reclassify proposals and the rest are dataclasses holding
  `Path`s and live objects. Explicit Pydantic models in `cli` make the shape a deliberate contract, and the JSON Schema for
  each is generated from them and committed, with a test that fails when it is stale (as for
  `microfiche-library.schema.json`).
- **One JSON document on stdout and nothing else there.** Human text is suppressed with `--json`. Progress, warnings and
  the OpenAI notice go to stderr, so a script can read stdout whatever the run said.
- **Versioned separately from the package.** Each document has a `version` integer, starting at 1, bumped only for a
  breaking change and described in its schema, so a bugfix release never changes what a script sees.
- **No document text.** The JSON carries paths relative to the library, names, folders, confidences and reasons, never
  the contents of a document.
- **Exit codes are unchanged.** A refused choice (name taken, duplicate, unknown folder) exits non-zero with the reason in
  the JSON.
- **`file <unit>... --to <group>[/<category>]`** files one or more inbox units, named relative to the inbox, into one
  destination as one job (`rollback` undoes it), recorded as `classified_by = "user"`. It builds a `ReviewSession`, so the
  checks (a place that exists, the name free, not a duplicate, content unchanged) are written once. Different destinations
  are separate calls. It plans no new folders: a script that wants a new category makes the folder.
- **`review --list --json`** prints the queue (each unit, the classifier's suggestion and reason) without prompting.

## Alternatives considered

- Serialising the core dataclasses directly: ties the public contract to internal types.
- Versioning with the package: every release looks like a possible break.
- One unit per `file` call: a script gets a job per file and no atomic batch.
- Structured log output and an HTTP API: the PRD's Won't.

## Consequences

- A stable surface for `watch-mode` and integrations; its shape is a promise, so changes need a `version` bump.
- Seven JSON schemas to commit and keep fresh, one per output.
- `cli` gains an `output/` package of models; `core` is unchanged apart from anything the models need exposed.
