"""Tests for the Ollama provider, with a fake ``ollama`` module standing in for the real one."""

import sys
import types
from typing import Any

import pytest
from core.ai.ollama_provider import OllamaProvider

# region Test helpers


class _Recorder:
    """What the fake ``ollama`` module was asked to do."""

    def __init__(self) -> None:
        self.client_kwargs: dict[str, Any] | None = None
        self.chat_call: dict[str, Any] | None = None


@pytest.fixture
def fake_ollama(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            recorder.client_kwargs = kwargs

        def chat(self, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
            recorder.chat_call = {"model": model, "messages": messages}
            return {"message": {"content": "Acme Ltd"}}

    monkeypatch.setitem(sys.modules, "ollama", types.SimpleNamespace(Client=Client))
    return recorder


# endregion


# region Public API


# region OllamaProvider.complete


def test_ollama_provider_complete_returns_reply_text(fake_ollama: _Recorder) -> None:
    assert OllamaProvider().complete("Which group?") == "Acme Ltd"


def test_ollama_provider_complete_sends_prompt_to_named_model(fake_ollama: _Recorder) -> None:
    OllamaProvider(model="mistral").complete("Which group?")

    assert fake_ollama.chat_call == {"model": "mistral", "messages": [{"role": "user", "content": "Which group?"}]}


def test_ollama_provider_complete_no_host_or_timeout_uses_client_defaults(fake_ollama: _Recorder) -> None:
    OllamaProvider().complete("Which group?")

    assert fake_ollama.client_kwargs == {}


def test_ollama_provider_complete_passes_host_and_timeout_to_client(fake_ollama: _Recorder) -> None:
    OllamaProvider(host="http://gpu-box:11434", timeout=30).complete("Which group?")

    assert fake_ollama.client_kwargs == {"host": "http://gpu-box:11434", "timeout": 30}


# endregion


# endregion
