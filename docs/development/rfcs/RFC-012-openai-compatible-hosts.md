# RFC-012: OpenAI-compatible AI hosts

Status: Draft

**Background:** raised on 2026-10-27, after the manual `--use-ai` checks for [RFC-009](archive/RFC-009-ollama-model-setting.md)
([ADR-004](../adr/ADR-004-ai-provider-setup.md)) could not exercise the OpenAI provider without an OpenAI key. Nothing
built.

**What happens now.** `[ai] provider` is `"ollama"` or `"openai"`. `OpenAIProvider` builds `OpenAI(api_key=..., timeout=...)`
with no `base_url`, so it can only reach `api.openai.com`. `[ai] host` is Ollama's address, and config validation
rejects it with any other provider (`HostWithoutOllamaError`). The privacy notice says "sent to OpenAI" whatever the
provider is.

So the OpenAI provider does **not** already cover other hosts. Many services and local servers speak the same chat
completions API as OpenAI, with a different address and their own key: hosted ones (OpenRouter, Groq, Together, Mistral,
DeepSeek and others), and local servers that are sometimes run with a key (vLLM, LM Studio, llama.cpp's server,
LiteLLM, and Ollama's own `/v1` endpoint). A user with one of those cannot use microfiche's AI fallback today unless
they have an OpenAI account.

**Why it matters.** It widens who can use `--use-ai` without a new provider per vendor, and it lets the OpenAI path be
tested without an OpenAI account (against a local compatible server).

## Proposal

- **One new setting, `[ai] base_url`**, used with `provider = "openai"` only: the address of an OpenAI-compatible
  server, such as `https://openrouter.ai/api/v1` or `http://localhost:1234/v1`. Empty means OpenAI's own address.
  `OpenAIProvider` passes it to the client as `base_url`. `host` stays Ollama-only, and `base_url` is rejected with
  `provider = "ollama"` in the same way `host` is rejected with `"openai"`.
- **The provider name stays `"openai"`** (it names the API, not the company), so no new provider class and no change to
  `LLMClassifier`, `check_ai` or the factory beyond passing `base_url` through. Whether to rename or alias it is a
  question below.
- **The notice and the check name the host.** The "text is sent to OpenAI" notice becomes "text is sent to
  `<host of base_url>`" when `base_url` is set, so the user sees where documents go; the pre-run check's line says it
  too (`openai gpt-4o-mini at openrouter.ai answered in 1.2 s`). The notice stays for a local address too, but says
  the address, because a `localhost` URL can be a tunnel or a proxy.
- **A key is not always needed.** Some local servers ignore it. The key variable is still read from
  `api_key_env`; whether an unset variable is an error when `base_url` is set is a question below.
- **Failure tips** gain the host: a connection failure with `base_url` set says to check `[ai] base_url`, not "your
  network connection".

Not in scope: providers whose API is not OpenAI-compatible (Anthropic's and Google's native APIs, Azure OpenAI's
deployment URLs and `api-version`, AWS Bedrock). Each would be its own provider class, like `OllamaProvider`; they are
listed in the questions only so the setting's name does not box them out.

## Questions to settle before building it

- **One address setting for both providers, or `base_url` beside `host`?** The proposal as written adds `base_url`
  (OpenAI-compatible only) next to `host` (Ollama only). That leaves two settings for the same idea, each rejected
  with the other's provider. The alternative merges them into one `[ai]` shape:
  - `provider`: the API style, `"ollama"` or `"openai"`;
  - `url`: where the server is, for either provider, empty meaning that provider's own default (renaming `host`);
  - `model`: unchanged;
  - `api_key_env`: the key variable, usable by either provider (Ollama behind a gateway can need a key).

  The rename needs no migration: microfiche has not had a public release, so no deprecation step or old-name
  fallback is needed. It does change the validators (`HostWithoutOllamaError` goes), the `init` prompts, the `[ai]`
  comments, the library schema if it names `host`, and the docs. Leaning to the merge, since keeping `host` and
  adding `base_url` means a rename later anyway; the first version stays smaller if `base_url` goes in alone.

- `base_url` on the `openai` provider, or a new provider name (for example `"openai-compatible"`) so the privacy
  notice and docs can be honest about "not OpenAI"? The proposal keeps one provider and makes the notice name the host.
- Is an unset key variable an error when `base_url` is set? Local servers often need none, and some SDK versions
  reject an empty key. Options: always require it (set it to any dummy for a local server), allow it empty with a
  placeholder passed to the client, or allow it only for `localhost` addresses.
- Reject a plain `http://` `base_url` for a non-local host (the key would travel in the clear)? Proposed yes, with a
  clear message.
- Should a `base_url` that already ends in `/chat/completions` be tolerated or corrected? (A common copy-paste slip.)
- How does `check_ai` tell the user the server answered but the model name is wrong? Compatible servers vary in the
  status they return for an unknown model (404, 400, or a 200 with an error body).
- Calibration: the saved AI answers in `tests/calibration/` were made with one model; a different host and model give
  different answers. Does `calibration.md` need a note that `ai_confidence` (0.70) is a single fixed trust level for
  whatever model answers?
- Timeout and context size differ widely by host; does `max_document_chars` (4000) still make sense as a default?
- Testing: no hosted account is needed if the suite fakes the client (as now) and one manual run goes against a local
  compatible server (LM Studio, or Ollama's `/v1`). Does that satisfy "the OpenAI provider is exercised", given no
  OpenAI key?

## Tests and docs it would need

- Config: `base_url` accepted with `openai`, rejected with `ollama`, rejected when not an `http(s)` URL, and the
  plain-`http` rule.
- `OpenAIProvider` passes `base_url` to a fake client only when set; `build_provider` passes it from the config.
- The notice and the `check_ai` line name the host; the connection-failure tip names `[ai] base_url`.
- Docs: the `[ai]` comments in the packaged defaults and the example config, the `AIConfig` field docs,
  `docs/how-to-use.md` (the AI section, both Bash and PowerShell tabs, and Current limitations), the Usage and
  configuration table of `README.md`, `make docs-cli` and `make library-schema` if the model changes, and the privacy
  wording wherever "sent to OpenAI" appears.
