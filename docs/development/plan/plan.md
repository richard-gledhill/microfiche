# Plan: `ai-provider-setup`

Implements [SPEC.md](SPEC.md). Each step is test-first (red, green, refactor) and ends with its targeted tests passing
and a commit; `make check` and `make test` run at the end. Branch `fix/ai-provider-setup`, cut from an up-to-date
`main` after the docs branch (`docs/rfc-009-accepted`: RFC, ADR, SPEC, plan) is merged, or carried on it if the user
prefers one PR.

1. **Quick win.** `LLMClassifier.resolve_category` skips the provider when the group has no categories (SPEC §6). Test
   in `tests/core/test_llm_classifier.py` with a fake provider that fails if called.
2. **No default model.** `EmptyModelError`, `build_provider` refuses an empty model (before the key check), both
   providers' `model` lose their defaults (SPEC §1). Update `tests/core/test_ai_factory.py`, `test_ollama_provider.py`
   and `test_openai_provider.py`, whose providers are built without a model.
3. **Failure tips.** `AIProviderError` and `describe_ai_failure` in `ai/base.py`; both providers wrap their known
   failures; `LLMClassifier` stores `describe_ai_failure(err)` as `failure` (SPEC §2). Fake `ollama` and `openai`
   modules raise each kind.
4. **`check_ai`.** New `core/ai/check.py` with `AICheck` and `check_ai` (SPEC §4, core half). Tests patch
   `microfiche.core.ai.check.build_provider`.
5. **CLI wiring.** `_build_ai_classifier` runs `check_ai` and fails with exit 1; `sort` builds the classifier before
   `_locked`; the check also runs for `--dry-run` and `review`; `render_sort_report` prints `ai_unavailable`, `-q`
   included (SPEC §3, §4 CLI half). New `tests/cli/test_cli_ai_check.py` (or beside the existing sort tests if they
   already have the harness).
6. **`init` offer.** The "Test the AI connection?" prompt after an `[ai]` change; a failed test never fails `init`
   (SPEC §5). Tests in `tests/cli/test_cli_init.py`.
7. **Config comments.** Rewrite the `[ai]` comments in the four places and the tests that pin them (SPEC §1a); rerun
   `make library-schema` and `make docs-cli`.
8. **Docs.** `how-to-use.md` (both tabs, Current limitations), README Usage, `mvp-roadmap.md` (drop the `-q` gap),
   `architecture/overview.md`, `make module-diagram`, capability map step 2 → Done. Ask the user before editing
   `ai-second-opinion-prd.md`.
9. **Verify and ship.** `make check`, `make test`; manual `--use-ai` runs (model present, model missing, server
   stopped; OpenAI on 3.35 if a key is available); open the PR, merge with a merge commit once `ci-ok` passes; then
   archive `SPEC.md`, `plan.md`, `todo.md` to `archive/2026-10-ai-provider-setup/` and mark ADR/RFC links intact.

Order notes: step 2 breaks existing provider tests, so it changes them in the same commit. Steps 4 and 5 are split so
`check_ai` is covered without the CLI. Step 7 is last among code steps so wording changes never mask a logic failure.
