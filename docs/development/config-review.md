# Configuration review

A review of what `microfiche-config.toml` holds today, what should move out of the code into it, and what
should move out of it. The outcome is planned as
[Stage 4.1 of the build plan](mvp-build-plan.md#stage-41--configuration-consolidation); the resulting
design is in [architecture.md §10](architecture.md#10-configuration-layout). This page keeps
the reasoning, so those two can stay short. Nothing here is built yet.

The repo is private and unpublished, so there are no existing libraries to migrate: the changes below
can be a hard cut.

## 0. The defaults already disagree

The code has two sources of defaults: the pydantic `Field` defaults in `core/config.py` and the template
`microfiche/microfiche-config.toml`. They conflict today:

| Setting | Code default | Template |
|---|---|---|
| `[obsidian] enabled` | `True` | `false` |
| `[category_hints]`, `[filing_rules]` | empty | sample data (`01 Requirements`, ...) |

One packaged defaults file (point 3) removes the drift.

## 1. Hard-coded constants to config

Move the scoring and matching knobs:

| Constant | Where | Now |
|---|---|---|
| `_HINT_MATCH_CONFIDENCE` | `rules/keyword_rules.py` | 0.75 |
| `_NAME_MATCH_CONFIDENCE` | `rules/keyword_rules.py` | 0.9 |
| `_FILENAME_MATCH_CONFIDENCE` | `rules/metadata_rules.py` | 0.95 |
| `_AI_CONFIDENCE` | `ai/llm_classifier.py` | 0.7 |
| `_FUZZY_MATCH_THRESHOLD` | `rules/group_rules.py` | 85 |
| `_FUZZY_MATCH_THRESHOLD` | `obsidian/tag_mapper.py` | 90 |
| `_MAX_DOCUMENT_CHARS` | `ai/llm_classifier.py` | 4000 |
| `top_n` | `library/category_suggester.py` | 5 |

Leave the rest fixed: file names such as `ledger.jsonl` and `audit.log`, `_CHUNK_SIZE`, `_MAX_REASON_CHARS`,
the Rich colour map and the stopword list. They are implementation detail, and a knob would only add ways
to break rollback and the ledger.

Why: `confidence_threshold` is the only dial today, so letting AI answers file means lowering it for
everything. With the scores in config, a library can keep the threshold at 0.75 and set the AI score to 0.8.
The roadmap already lists "make the AI score configurable".

Cautions:
- **Two dials, one effect.** The threshold is compared against these scores, and the default works because
  the hint score (0.75) equals the threshold (0.75). Keep them in one `[classification]` block and say in a
  comment that the relative values matter.
- **Plumb them in; don't read globals.** `RulesEngine` and `LLMClassifier` take the values in their
  constructors, so `Classifier` still owns the decision and resolvers only propose.
- **Calibration must still hold.** The defaults must reproduce today's numbers, so `tests/calibration/`
  keeps passing unchanged.
- Validate ranges: scores 0-1, fuzzy thresholds 0-100, `[ai] max_document_chars` at least 0, where 0 means unlimited and warns once per run.

## 2. `keep_folders` on by default, and in config

The option exists as a CLI flag. What is missing is the config key and the default. `scanner.py` carries a
TODO asking whether it should default to true, and `propose-categories` already hard-codes `True`.

- Config key: a new `[sorting]` section (`[library_structure]` describes shape, not behaviour), with
  `keep_folders = true`.
- CLI: `--keep-folders` stays a boolean switch, and a separate `--keep-folders-off` switch turns folders off for
  one run (no `--no-keep-folders`). Passing both is an error. Precedence: whichever flag is passed, then library
  config, then packaged default.
- Behaviour change: `sort` moves whole folders as one unit by default, and tied folders go to review.
  The `no` option also changes: today it ignores inbox folders, and it should instead file their documents
  one by one and then handle the emptied folder (remove it and record the removal, so rollback recreates
  it; keep it if anything is left inside).
  `architecture.md` §4 ("opt-in, off by default"), `how-to-use.md`, the README and `cli-reference.md` all
  say otherwise and change with it.

## 3. A packaged defaults file

Put the defaults inside the package, at `packages/core/src/core/defaults/microfiche-config.toml`, loaded
with `importlib.resources`:

- The repo-root `microfiche/` folder sits outside `src/`, so a built wheel would not include it.
- The loader reads the defaults, deep-merges the library's file over them, then validates. Tables merge key
  by key. Lists replace outright, because an `exclude` list that silently extends is surprising.
- The pydantic models stop owning defaults, which fixes point 0, and "ask before running on defaults"
  (see the roadmap) becomes easy: the loader knows which keys came from defaults.
- The defaults file holds real defaults only. Sample data stays in the template.
- A test asserts that the template and the defaults agree.

## 4. AI settings in the config

Nothing reads AI config today: `commands.py` hard-codes `LLMClassifier(OllamaProvider())`, which is why
`OpenAIProvider` is unreachable. A TOML entry does nothing without an `AIConfig` model, a
`build_provider(config)` factory in `core/ai`, and the CLI calling it.

**Tier 1, for the MVP.** `[ai]` with `provider = "ollama" | "openai"`, `model`, `host`, `timeout`, the AI
score from point 1 and `max_document_chars` (0 means unlimited, with a one-per-run warning about token usage, time and the context window). This replaces the unbuilt `--ai-provider` task in build-plan Stage 4. API keys never
go in the file; use `api_key_env = "OPENAI_API_KEY"`. Whether `--use-ai` stays a per-run switch or becomes
`[ai] enabled` is open.

**Tier 1.5, Stage 4.5.** A second kind of AI classifier, a decision model that returns one option from a fixed list with a probability, selected by `[ai] kind` and using its own probability as the confidence. See [ai-classifier-options.md](ai-classifier-options.md).

**Tier 2, deferred.** A `command` provider, where the config holds the command to run. It is a genuine seam
(`AIProvider` is one method, `complete(prompt) -> str`), and it would let users plug in llama.cpp, `llm`,
`claude -p`, or Ollama with their own flags. It waits on these design points:
- Run an argument list, never a shell: split a string with `shlex`, never `shell=True`. Bash and PowerShell
  quote differently, so a shell string would work on one and break on the other.
- Pass the prompt on stdin and read stdout. Add a timeout, and treat a non-zero exit as "AI unavailable"
  rather than crashing the run.
- Security: the config lives in the library folder, often a synced or shared vault, so a config that runs a
  command on `sort` lets anyone who can edit the vault run code. Needs an explicit opt-in such as
  `allow_command = true`, or reading the command only from a user-level config.

## 5. Other postponed settings

Worth doing in the MVP:
- `[sorting] keep_folders` (point 2).
- The signal strengths and fuzzy thresholds (point 1).
- `[ai]` (point 4).
- Wiring `[obsidian]` (`enabled`, `tag_mode`, `tag_index_path`) as part of Stage 5; the settings exist but
  nothing calls them.
- A `word_boundary` toggle for group matching, so the roadmap's "`Car` matches `carrier`" fix can ship as a
  setting.

Remove or validate, rather than wire:
- `levels` and `file_target_level` are documented as "not read by the code yet", and `depth` is only valid
  at 2. See point 6.
- `library_templates` is unused. See point 6.

Added by the [operations review](operations-review.md), in Stages 4.3 and 4.4: `[sorting] ignore` (inbox names
to skip, such as Office lock files), `[parsing] max_file_mb` (an oversize file goes to review) and `[logging]`
(`level`, `file`, `max_bytes`, `backup_count`).

Later: the ambiguity-check toggle, a `[review]` section, `index.md` generation settings. Define the Stage 5
ones when `review` and `index` are built.

## 6. Move templates and hints out of the config

### What the code does today

- `library_templates` is read by nothing outside the tests. `create_library_group` in `templates.py` has no
  caller, since there is no `init` command, and its docstring still says `library_templates.yaml`. Because
  it sits in `microfiche-config.toml`, a malformed entry fails validation on every `sort`
  (`test_config.py` pins this with `software_project = "oops"`).
- `classifier.py` passes `config.category_hints.categories` and `config.filing_rules.rules` into
  `RulesEngine`. Both are keyed by category name only, so one hint list applies to "01 Requirements" in
  every group.
- [architecture.md §1](architecture.md#1-the-library-is-the-taxonomy--categories-are-discovered-not-configured)
  says the library is the taxonomy; hints only help match folders that already exist.

### Pros and cons of a separate JSON file

| | For | Against |
|---|---|---|
| Separation | The config holds behaviour settings (thresholds, AI, `keep_folders`, `depth`); library shape and matching data sit elsewhere. A broken hint no longer blocks unrelated settings. | A second file and loader means a second set of error messages; `ConfigError` and `Library.config` must cover both. |
| Load timing | Templates are only needed when creating a library, so they need not be validated on every run. | Hints and filing rules are used on every sort, so those must still load and validate each time. |
| Tree shape | A recursive `{name, hints, children}` node suits a tree and need not change to describe more levels. | TOML also nests (`[categories."01 Requirements"]`); past depth 2 the headers get long but stay workable. |
| Writing | `json` is stdlib and reads and writes; TOML has only `tomllib`, which reads. `init`, or a future `review` "create new category", would need to write this data. | Writing JSON drops any hand-written layout. |
| Hand-editing | `$schema` plus a schema generated from the pydantic model (`model_json_schema()`) gives editor validation and autocomplete. | No comments, strict commas, everything quoted. Hints are what users edit most, and TOML's comments are friendlier. |
| Config scope | `microfiche-config.toml` becomes agnostic to folder structure, with only `depth` left. | `levels` and `file_target_level` need a new home or removal. |

JSON is the right choice, but "varying folder depths" is not the reason. The file format does not stop deeper
libraries: taxonomy discovery, the two-stage classifier and the filer are all hard-wired to group then
category, and `depth` accepts only 2. JSON's real advantages are machine-writability, a generated schema,
and a recursive node format that will not need redesigning later. Reject any `depth` other than 2 with a
clear error until the engine supports more.

### Decisions

- **Naming.** The plural `library_templates` suits a catalog of named templates; the singular suits a
  library's own file, "this library's template". That file is `.microfiche/microfiche-library.json`,
  mirroring `microfiche-config.toml`.
- **`library_templates`: delete it from the config now.** The catalog has no consumer until an `init`
  command exists, and dead data still gets validated. If `init` joins the MVP, ship the catalog as packaged
  JSON in `core/defaults/templates/`, using the same node schema as the library file. Fix the stale `.yaml`
  mentions in `templates.py` and `metadata_rules.py` at the same time.
- **Combine the schema, not the location or meaning.** A category node is `{name, hints, rules}` in one
  format. A template says what to create; a library's hints file says what to match against existing
  folders. The folders stay the authority on what exists: an entry with no folder is never filed into, and the
  file never creates or removes a folder. The file is created from the folders and kept in step (Stage 4.10). A library gets its own copy at creation and edits it from then on; if
  it merely referenced a shared template, a template change would silently alter its sorting.
- **`filing_rules` moves with the hints.** The rules point at category names, and the template's own TODO
  already says "review with category_hints". `naming_rules` stays in the TOML: those are regexes, not
  category data.
- **Hint scope.** A recursive tree of folders, so any depth fits. A `*` node applies to any folder at its level,
  which is today's behaviour (global by category name) without repeating hints; a node named for a group overrides
  or adds to it for that group only.
- **`levels` and `file_target_level`.** `levels` (the names "group" and "category") belongs with the shape,
  so it goes in the JSON or is deleted. `file_target_level` is derived and goes.

### Risks

- **Missing file.** A missing library file means most documents go to review. That gives the roadmap's "ask
  before running on defaults" item more weight.
- **Rewrites.** The calibration corpus libraries, `tests/core/test_config.py`, `tests/cli/test_app.py` and
  the `how-to-use.md` hint examples all use the TOML sections.
- **Comments.** The explanatory comments in the shipped TOML are lost in JSON. Put the explanations in the
  schema's `description` fields and in `how-to-use.md`.

No migration shim or tailored error for old `[category_hints]` sections: the repo is unpublished, so
`extra="forbid"` rejecting the old sections is enough.
