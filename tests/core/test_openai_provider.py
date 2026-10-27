"""Tests for the OpenAI provider, with a fake ``openai`` module standing in for the real one."""

import sys
import types
from typing import Any

import pytest
from microfiche.core.ai.base import AIProviderError
from microfiche.core.ai.openai_provider import OpenAIProvider

# region Test helpers


class _StatusError(Exception):
    """Stands in for an ``openai`` HTTP error, which carries a status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _Recorder:
    """What the fake ``openai`` module was asked to do, and what it will answer."""

    def __init__(self) -> None:
        self.client_kwargs: dict[str, Any] | None = None
        self.create_call: dict[str, Any] | None = None
        self.reply: str | None = "Acme Ltd"
        self.error: Exception | None = None


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()

    class Completions:
        def create(self, model: str, messages: list[dict[str, str]]) -> Any:
            recorder.create_call = {"model": model, "messages": messages}
            if recorder.error is not None:
                raise recorder.error
            message = types.SimpleNamespace(content=recorder.reply)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    class OpenAI:
        def __init__(self, **kwargs: Any) -> None:
            recorder.client_kwargs = kwargs
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=OpenAI))
    return recorder


# endregion


# region Public API


# region OpenAIProvider.complete


def test_openai_provider_complete_returns_reply_text(fake_openai: _Recorder) -> None:
    assert OpenAIProvider(model="gpt-4o").complete("Which group?") == "Acme Ltd"


def test_openai_provider_complete_no_reply_returns_empty_string(fake_openai: _Recorder) -> None:
    fake_openai.reply = None

    assert OpenAIProvider(model="gpt-4o").complete("Which group?") == ""


def test_openai_provider_complete_sends_prompt_to_named_model(fake_openai: _Recorder) -> None:
    OpenAIProvider(model="gpt-4o").complete("Which group?")

    assert fake_openai.create_call == {"model": "gpt-4o", "messages": [{"role": "user", "content": "Which group?"}]}


def test_openai_provider_complete_no_key_or_timeout_uses_client_defaults(fake_openai: _Recorder) -> None:
    OpenAIProvider(model="gpt-4o").complete("Which group?")

    assert fake_openai.client_kwargs == {}


def test_openai_provider_complete_passes_key_and_timeout_to_client(fake_openai: _Recorder) -> None:
    OpenAIProvider(model="gpt-4o", api_key="sk-test", timeout=30).complete("Which group?")

    assert fake_openai.client_kwargs == {"api_key": "sk-test", "timeout": 30}


@pytest.mark.parametrize(
    ("raised", "tip_part"),
    [
        (_StatusError("model not found", 404), "[ai] model"),
        (_StatusError("bad key", 401), "api_key_env"),
        (ConnectionError("down"), "network"),
        (TimeoutError("timed out"), "[ai] timeout"),
        (ModuleNotFoundError("No module named 'openai'"), "uv sync --extra ai"),
    ],
)
def test_openai_provider_complete_known_failure_raises_with_tip(
    fake_openai: _Recorder, raised: Exception, tip_part: str
) -> None:
    fake_openai.error = raised

    with pytest.raises(AIProviderError) as exc_info:
        OpenAIProvider(model="gpt-4o").complete("Which group?")

    assert tip_part in exc_info.value.tip
    assert exc_info.value.__cause__ is raised


def test_openai_provider_complete_unknown_failure_propagates_unchanged(fake_openai: _Recorder) -> None:
    fake_openai.error = ValueError("odd")

    with pytest.raises(ValueError, match="odd"):
        OpenAIProvider(model="gpt-4o").complete("Which group?")


# endregion


# region OpenAIProvider repr


def test_openai_provider_repr_hides_api_key() -> None:
    assert "sk-secret" not in repr(OpenAIProvider(model="gpt-4o", api_key="sk-secret"))


# endregion


# endregion
