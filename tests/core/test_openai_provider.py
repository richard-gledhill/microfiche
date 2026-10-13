"""Tests for the OpenAI provider, with a fake ``openai`` module standing in for the real one."""

import sys
import types
from typing import Any

import pytest
from microfiche.core.ai.openai_provider import OpenAIProvider

# region Test helpers


class _Recorder:
    """What the fake ``openai`` module was asked to do, and what it will answer."""

    def __init__(self) -> None:
        self.client_kwargs: dict[str, Any] | None = None
        self.create_call: dict[str, Any] | None = None
        self.reply: str | None = "Acme Ltd"


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()

    class Completions:
        def create(self, model: str, messages: list[dict[str, str]]) -> Any:
            recorder.create_call = {"model": model, "messages": messages}
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
    assert OpenAIProvider().complete("Which group?") == "Acme Ltd"


def test_openai_provider_complete_no_reply_returns_empty_string(fake_openai: _Recorder) -> None:
    fake_openai.reply = None

    assert OpenAIProvider().complete("Which group?") == ""


def test_openai_provider_complete_sends_prompt_to_named_model(fake_openai: _Recorder) -> None:
    OpenAIProvider(model="gpt-4o").complete("Which group?")

    assert fake_openai.create_call == {"model": "gpt-4o", "messages": [{"role": "user", "content": "Which group?"}]}


def test_openai_provider_complete_no_key_or_timeout_uses_client_defaults(fake_openai: _Recorder) -> None:
    OpenAIProvider().complete("Which group?")

    assert fake_openai.client_kwargs == {}


def test_openai_provider_complete_passes_key_and_timeout_to_client(fake_openai: _Recorder) -> None:
    OpenAIProvider(api_key="sk-test", timeout=30).complete("Which group?")

    assert fake_openai.client_kwargs == {"api_key": "sk-test", "timeout": 30}


# endregion


# region OpenAIProvider repr


def test_openai_provider_repr_hides_api_key() -> None:
    assert "sk-secret" not in repr(OpenAIProvider(api_key="sk-secret"))


# endregion


# endregion
