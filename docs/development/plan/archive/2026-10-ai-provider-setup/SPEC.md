# SPEC: `ai-provider-setup`

Source: [RFC-009](../rfcs/RFC-009-ollama-model-setting.md), decided in [ADR-004](../adr/ADR-004-ai-provider-setup.md);
step 2 of the [capability map](../requirements/post-mvp-capability-map.md). Branch: `fix/ai-provider-setup`.

Style, the quality bar and test layout follow [conventions.md](../conventions.md), [constraints.md](../constraints.md)
and [testing/](../testing/README.md); they are not restated here. Only what is specific to this work follows.

## Objective

The AI model is always one the user chose, a provider failure says how to fix it, and `--use-ai` is tested once before
any document is classified.

## Scope

In: `core/ai/` (both providers, factory, a new check), `LLMClassifier.resolve_category`, the CLI's `_build_ai_classifier`
and the `sort` summary, `init`'s optional test prompt, docs. Out: any change to classification, the threshold, prompts or
config keys; `ai-second-opinion` (it depends on this).

## Design

### 1. No default model
- `OllamaProvider.model` and `OpenAIProvider.model` become required fields (no default); the `llama3` and `gpt-4o-mini`
  literals are deleted.
- `build_provider` raises `EmptyModelError(ConfigError)` when `config.model` is empty (the `model = {...} if ...`
  indirection goes). The message names `[ai] model`; for Ollama it adds that `ollama list` shows installed models and
  `ollama pull <name>` installs one, for OpenAI that it takes a model name such as one from the OpenAI model list.
  Order: the model check comes before the API-key check.
- `load_config` is unchanged; the packaged `model = ""` stays valid.

### 1a. Config comments that guide the user
Every `[ai]` comment says what to put there, with a typical value, and the four places that carry the same wording are
changed together: `core/defaults/microfiche-config.toml`, the example `microfiche/microfiche-config.toml`, the
`AIConfig` field docs in `core/config.py` (which feed the generated docs), and the sample in `docs/how-to-use.md`.
`init`'s walk-through prompts reuse the field text, so they follow. Wording, shown for the defaults file:

```toml
[ai]
# Who answers: "ollama" (runs on your machine) or "openai" (sends the text of each document it is asked about to
# OpenAI).
provider = "ollama"
# The model to ask. Required with --use-ai; there is no default. Ollama: a model you have pulled, e.g. "llama3.1"
# (`ollama list` shows them, `ollama pull <name>` installs one). OpenAI: a model name, e.g. "gpt-4o-mini".
model = ""
# Where the Ollama server is. Empty means Ollama's default address, http://localhost:11434. Set it for a server on
# another machine, e.g. "http://gpu-box:11434". Ollama only.
host = ""
# Seconds to wait for one answer. A first call can be slow while Ollama loads the model: raise this if it times out.
timeout = 120
```

`api_key_env`, `ai_confidence` and `max_document_chars` already say what they do; each gains a typical value only
(`"OPENAI_API_KEY"` is the usual name; `0.70` and `4000` stay as the defaults). Tests that pin the comment text
(`test_config.py`, the generated-doc and schema freshness tests) are updated with it; `make library-schema` and
`make docs-cli` are rerun.

### 2. Failure tips, kept in the providers
- `ai/base.py` gains `AIProviderError(Exception)` with `detail: str` and `tip: str`, and
  `describe_ai_failure(err) -> str`: `describe_error(err)` for any other exception, `"<detail>. <tip>"` for an
  `AIProviderError`. `AIProvider` (the Protocol) is unchanged; providers wrap what they know and re-raise with
  `from err`.
- `OllamaProvider.complete` maps: `ollama.ResponseError` with status 404 → ``run `ollama pull <model>`, or set [ai]
  model to one `ollama list` shows``; connection error → ``start Ollama (`ollama serve`), or check [ai] host``;
  timeout → ``raise [ai] timeout, or use a smaller model``; `ModuleNotFoundError` for `ollama` → ``install the ai extra
  (`uv sync --extra ai`)``. Anything else propagates unchanged.
- `OpenAIProvider.complete` maps the same kinds the same way (not found / authentication / connection / timeout /
  package missing) with OpenAI-appropriate tips (check `[ai] model`, check the key in `api_key_env`, check the network,
  raise `[ai] timeout`, install the extra).
- `LLMClassifier._ask` stores `describe_ai_failure(err)` as `failure` (and in its log line). Output stays capped at the
  existing 200 characters for the exception text; the tip is appended after, uncapped.

### 3. `sort` summary shows the failure
`render_sort_report` prints `SortReport.ai_unavailable` as a yellow line (as `review` does today:
`The AI fallback was unavailable (<failure>).`), straight to the console, so `-q` does not hide it. Applies to dry-run
too.

### 4. Pre-run check
- New `core/ai/check.py`: `AICheck(ok: bool, detail: str, seconds: float)` (frozen dataclass) and
  `check_ai(config: AIConfig) -> AICheck`. It calls `build_provider(config)` then
  `provider.complete("Reply with the single word: OK")`. Any exception, including `ConfigError` from `build_provider`,
  gives `ok=False` and `detail = describe_ai_failure(err)`. A non-empty reply gives `ok=True` and
  `detail = "<provider> <model> answered in <n.n> s"`; an empty reply gives `ok=False`, `detail = "the model returned an
  empty reply"`. The reply is not compared with `OK`. It sends no document text. Uses `[ai] timeout` as is.
- CLI `_build_ai_classifier(settings)` calls `check_ai` after the existing OpenAI/`max_document_chars` notices and before
  building the `LLMClassifier`; on `ok=False` it calls `_fail(detail)` (exit 1, printed directly, not via the logger
  alone). On success it prints the `detail` line unless `-q`.
- `sort` builds the classifier **before** `_locked`: the `use_ai` branch moves above the `with` block. `review` already
  builds it outside any lock; no change beyond the check. `sort --dry-run --use-ai` runs the check too.
- A failed check moves nothing and writes no job, ledger or audit line.
- The `build_provider` `ConfigError` path today ends in `_fail`; it is now reached through `check_ai`, keeping the same
  message and exit code.

### 5. `init` offers the test
After the settings walk-through, if the user changed any `[ai]` setting, `init` asks `Test the AI connection?`
(default no) and, on yes, runs `check_ai` against the saved config and prints its `detail`. A failed test never fails
`init` (the config is already saved). No automatic check; `init` does not prompt for the model. Prompt only, in
`cli/`; no logic of its own.

### 6. Quick win
`LLMClassifier.resolve_category` returns `CategoryMatch(name=None, confidence=0.0, reason="Group has no categories")`
without calling the provider when `taxonomy.categories_for(group)` is empty.

## Tests (test-first, fakes at the seams, no network or Ollama)

Mirror modules per conventions; names `test_<subject>_<scenario>_<result>`.

- `build_provider`: empty model refused for both providers with the tip; empty model reported before a missing key;
  non-empty model passes through unchanged.
- Providers: a fake `ollama` module/client raising each kind (404 `ResponseError`, connection error, timeout, missing
  package) gives the matching `AIProviderError`; an unrelated exception propagates untouched. Same for OpenAI.
- `describe_ai_failure`: plain exception vs `AIProviderError`.
- `LLMClassifier`: `failure` carries the tip; `resolve_category` skips the provider for an empty group (fake provider
  asserts no call) and still asks otherwise.
- `check_ai` (patch `microfiche.core.ai.check.build_provider`): ok, provider raises, empty reply, missing key, empty
  model.
- CLI: `sort --use-ai` with a failing check exits 1 before any file moves and writes no state, with and without `-q`;
  the same for `--dry-run` and for `review`; a passing check carries on; `sort` builds the classifier before taking the
  lock (a held lock with a failing check still reports the check, not the lock); the `sort` summary prints
  `ai_unavailable`, also under `-q`; `init` offers the test only after an `[ai]` change, default no, and a failed test
  does not fail `init`.

## Docs touched (per conventions.md, Docs)

- `docs/how-to-use.md` (`sort`, `review`, `init`: both Bash and PowerShell tabs, and Current limitations), the Usage
  section of `README.md`, and `make docs-cli`; `make library-schema` if the `model` field description changes.
- `requirements/mvp-roadmap.md`: remove the "`-q` hides the AI-unavailable warning" known gap; capability map step 2 →
  Done; RFC-009 stays Accepted, ADR-004 stays the record.
- `architecture/overview.md` and `module-diagram.md` (`make module-diagram`: `ai/check.py` is a new module).
- `requirements/ai-second-opinion-prd.md`: **ask the user first**; remove its model-availability requirement and make it
  depend on `ai-provider-setup`.

## Verification

`make check` and `make test` after the last change; the narrow tests while building. One manual `--use-ai` run against a
real Ollama (model present, model missing, server stopped) is noted in the PR; the OpenAI provider is not exercised by CI,
so the same manual run with `openai` 3.35 (Dependabot #88) is worth doing before merge.

## Open points for review

- `EmptyModelError` and `AIProviderError` are new names; both are small and replace the ad-hoc `ConfigError` text. Say if
  you would rather reuse `ConfigError` directly.
- Success of the check prints one line (suppressed by `-q`); say if it should be silent.
