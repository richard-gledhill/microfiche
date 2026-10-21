# RFC-009: Ollama model setting and failure tips

Status: Draft

**Background:** raised on 2026-10-21 from a review of how `[ai] model = ""` behaves with `provider = "ollama"`. Nothing
built.

**What happens now.** The packaged default is `model = ""`, documented as "the provider's own default". An empty
`model` passes config validation; `ai/factory.py::build_provider` leaves it out, so `OllamaProvider` falls back to its
hardcoded `model: str = "llama3"` (`ai/ollama_provider.py`). The user never chose that model and nothing tells them it
is being used.

If `llama3` is not pulled on the Ollama server, the `ollama` client raises `ollama.ResponseError` (a 404, worded along
the lines of `model "llama3" not found, try pulling it first`). `LLMClassifier._ask` catches it, keeps
`describe_error(err)` (`ResponseError: <first line>`, at most 200 characters) as its `failure`, and logs once:

```text
AI fallback unavailable (ResponseError: model "llama3" not found…): the rest of the run uses the rules only,
so anything only the AI could answer goes to review
```

The run carries on with the rules only. `sort` shows this only as that console log warning (hidden with `-q`); the
`sort` summary does not print `SortReport.ai_unavailable`. `review` also prints
`The AI fallback was unavailable (ResponseError: …).` There is no hint on how to fix it. With the `ai` extra missing,
the same path reports `ModuleNotFoundError: No module named 'ollama'`, again with no hint.

**Why it matters.** The user gets a model they did not pick, and when it is missing they see a raw exception with no
next step, after a run has already sent everything the AI would have answered to review.

## Actions

- **Remove the hardcoded model from `ai/ollama_provider.py`.** `OllamaProvider.model` has no default; the model always
  comes from `[ai] model`. An empty `model` with `provider = "ollama"` is caught before any document is classified
  (a `ConfigError` from `build_provider`, which `_build_ai_classifier` already turns into a clean CLI failure), with a
  tip such as: ``[ai] model is empty: set it to a model installed in Ollama (`ollama list` shows them, `ollama pull
  <name>` installs one).``
- **Give provider failures a tip on how to fix them.** Map the common Ollama failures to a one-line next step, kept
  with the `failure` text so `sort` and `review` show it:
  - model not found (`ResponseError`, status 404): ``run `ollama pull <model>`, or set [ai] model to one `ollama list`
    shows``;
  - server not reachable (connection error): ``start Ollama (`ollama serve`), or check [ai] host``;
  - timeout: ``raise [ai] timeout, or use a smaller model``;
  - the `ollama` package missing: ``install the ai extra (`uv sync --extra ai`)``.
- **Show the failure in the `sort` summary**, not only as a log line, so `-q` and a scrolled-away warning do not hide
  why documents went to review.

## Questions to settle before building it

- Validate an empty Ollama `model` in `load_config` (fails every command, even ones that never use the AI) or only in
  `build_provider` (fails only `--use-ai` runs)? The second is likely right.
- Should `microfiche init` ask for, or fill in, the Ollama model?
- Check once at the start of a run that the model exists (`ollama.Client.show`), so the user hears about it before
  the first document rather than part-way through?
- Does the OpenAI provider's hardcoded `model: str = "gpt-4o-mini"` get the same treatment, for consistency?
- Where does the tip mapping live: in each provider (which knows its own exception types) or in `LLMClassifier`?
- Tests it would need: an empty Ollama `model` refused with the tip; a fake client raising each failure kind and the
  matching tip in `failure`; the `sort` summary printing `ai_unavailable`; the `ai` extra missing.
