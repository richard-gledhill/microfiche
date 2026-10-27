# ADR-004: AI provider setup: no default model, fix-it tips and a pre-run check

- **Status:** Accepted
- **Date:** 2026-10-27
- **Decision:** The model is always one the user chose: neither provider has a hard-coded default, and an empty
  `[ai] model` is refused by `build_provider`. Provider failures carry a one-line fix-it tip, supplied by the provider.
  `--use-ai` runs of `sort` and `review` make one hello-world call before any document is classified, outside the run
  lock, and a failed check stops the command with exit 1. See [Decisions](#decisions).
- **Source:** [RFC-009](../rfcs/RFC-009-ollama-model-setting.md)

## Context

With `[ai] model = ""` (the packaged default), `OllamaProvider` fell back to a hard-coded `llama3` the user never chose.
When that model was not pulled, the user saw a raw `ResponseError` part-way through a run, after the first failure had
switched the AI off and sent everything only the AI could answer to review; `-q` hid even that. `OpenAIProvider` had the
same shape with `gpt-4o-mini`, where the unchosen default is a billed hosted model.

## Decisions

- **No default model.** `OllamaProvider.model` and `OpenAIProvider.model` lose their defaults. `build_provider` raises a
  `ConfigError` for an empty `model`, with a tip (for Ollama: `ollama list` shows installed models, `ollama pull <name>`
  installs one). The check is in `build_provider`, not `load_config`, so only `--use-ai` runs fail; the packaged
  `model = ""` stays valid for rules-only use.
- **Fix-it tips live in each provider.** The provider knows its own exception types, so it maps them to a tip (model not
  found, server unreachable, timeout, `ollama` package missing); `LLMClassifier` and the check stay provider-agnostic.
  The tip is kept with `failure`, so `sort` and `review` show it, and `sort`'s summary prints `ai_unavailable`, which
  `-q` does not hide.
- **Pre-run check.** `core/ai/check.py::check_ai(config) -> AICheck(ok, detail, seconds)` builds the provider and calls
  `complete` once. Any exception becomes `describe_error` plus the tip; any non-empty reply is success. It sends no
  document text, runs for `sort --dry-run --use-ai` too, and uses the normal `[ai] timeout` (the timeout tip names the
  setting).
- **A failed check aborts.** The command exits 1 before anything is moved, with the message printed directly. The user
  asked for AI, nothing has moved, and rerunning costs nothing; warning and continuing is the behaviour this replaces.
- **Outside the lock.** `sort` runs the check before taking `.microfiche/lock`, so a slow timeout never holds it. The
  check reads nothing from the library.
- **`init` offers, never runs.** After the walk-through changes an `[ai]` setting, `init` asks "Test the AI
  connection?" (default no), a thin prompt over `check_ai`. No automatic check: a fresh install may lack Ollama or the
  `ai` extra, and with `openai` it would be an unrequested hosted call. `init` does not ask for the model.
- **Hello-world replaces `ollama.Client.show`.** It proves the model loads and answers, works for both providers through
  the one `AIProvider` interface, and warms the model; an Ollama-only "exists" method would add no seam.

## Alternatives considered

- Validate in `load_config`: fails every command, even ones that never use the AI.
- Warn and continue: the "did not notice" problem.
- A longer timeout for the check: the first real call could still time out, hiding the problem until mid-run.
- Keep the `gpt-4o-mini` default: leaves an unchosen billed model.

## Consequences

- An existing OpenAI user with `model = ""` now gets a clear error on `--use-ai` and must set a model.
- `--use-ai` costs one small call per run, and with Ollama it loads the model, so the first real answer is not slow.
- `ai-second-opinion` no longer needs its own model-availability check; it depends on `ai-provider-setup`.
