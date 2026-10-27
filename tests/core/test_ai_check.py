"""Tests for the pre-run AI check, with a fake provider standing in for a real model."""

from pathlib import Path
from typing import Any

import pytest
from microfiche.core.ai.base import AIProviderError
from microfiche.core.ai.check import AICheck, check_ai
from microfiche.core.config import AIConfig, load_config

# region Test helpers


class _Provider:
    """Answers (or fails) as scripted and remembers the prompts it was sent."""

    def __init__(self, reply: str = "OK", error: Exception | None = None) -> None:
        self._reply = reply
        self._error = error
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self._error is not None:
            raise self._error
        return self._reply


def _settings(**overrides: Any) -> AIConfig:
    """The packaged ``[ai]`` settings with a model, and ``overrides`` applied."""
    return load_config(Path("does-not-exist")).ai.model_copy(update={"model": "llama3", **overrides})


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> _Provider:
    fake = _Provider()
    monkeypatch.setattr("microfiche.core.ai.check.build_provider", lambda config: fake)
    return fake


# endregion


# region Public API


# region check_ai


def test_check_ai_working_provider_ok_with_provider_model_and_time(provider: _Provider) -> None:
    result = check_ai(_settings())

    assert isinstance(result, AICheck)
    assert result.ok
    assert result.detail.startswith("ollama llama3 answered in ")
    assert result.seconds >= 0


def test_check_ai_sends_a_fixed_prompt_with_no_document_text(provider: _Provider) -> None:
    check_ai(_settings())

    assert provider.prompts == ["Reply with the single word: OK"]


def test_check_ai_any_non_empty_reply_is_ok(provider: _Provider) -> None:
    provider._reply = "Sure! Here you go: OK."

    assert check_ai(_settings()).ok


def test_check_ai_empty_reply_not_ok(provider: _Provider) -> None:
    provider._reply = "  \n"

    result = check_ai(_settings())

    assert not result.ok
    assert result.detail == "the model returned an empty reply"


def test_check_ai_provider_error_detail_has_tip(provider: _Provider) -> None:
    provider._error = AIProviderError("ResponseError: model not found", "Run `ollama pull llama3`.")

    result = check_ai(_settings())

    assert not result.ok
    assert result.detail == "ResponseError: model not found. Run `ollama pull llama3`."


def test_check_ai_other_exception_detail_is_described(provider: _Provider) -> None:
    provider._error = ValueError("boom")

    assert check_ai(_settings()).detail == "ValueError: boom"


def test_check_ai_given_provider_is_the_one_asked() -> None:
    given = _Provider(reply="OK")

    assert check_ai(_settings(model=""), given).ok  # no build, so the empty model is never looked at
    assert given.prompts == ["Reply with the single word: OK"]


def test_check_ai_empty_model_not_ok_with_tip() -> None:
    result = check_ai(_settings(model=""))

    assert not result.ok
    assert "[ai] model is empty" in result.detail


def test_check_ai_missing_openai_key_not_ok_naming_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = check_ai(_settings(provider="openai", model="gpt-4o"))

    assert not result.ok
    assert "OPENAI_API_KEY" in result.detail


# endregion


# endregion
