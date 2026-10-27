"""Tests for the Ollama provider, with a fake ``ollama`` module standing in for the real one."""

import sys
import types
from typing import Any

import pytest
from microfiche.core.ai.base import AIProviderError
from microfiche.core.ai.ollama_provider import OllamaProvider

# region Test helpers


class _StatusError(Exception):
    """Stands in for ``ollama.ResponseError``, which carries a status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _Recorder:
    """What the fake ``ollama`` module was asked to do."""

    def __init__(self) -> None:
        self.client_kwargs: dict[str, Any] | None = None
        self.chat_call: dict[str, Any] | None = None
        self.error: Exception | None = None


@pytest.fixture
def fake_ollama(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            recorder.client_kwargs = kwargs

        def chat(self, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
            recorder.chat_call = {"model": model, "messages": messages}
            if recorder.error is not None:
                raise recorder.error
            return {"message": {"content": "Acme Ltd"}}

    monkeypatch.setitem(sys.modules, "ollama", types.SimpleNamespace(Client=Client))
    return recorder


# endregion


# region Public API


# region OllamaProvider.complete


def test_ollama_provider_complete_returns_reply_text(fake_ollama: _Recorder) -> None:
    assert OllamaProvider(model="llama3").complete("Which group?") == "Acme Ltd"


def test_ollama_provider_complete_sends_prompt_to_named_model(fake_ollama: _Recorder) -> None:
    OllamaProvider(model="mistral").complete("Which group?")

    assert fake_ollama.chat_call == {"model": "mistral", "messages": [{"role": "user", "content": "Which group?"}]}


def test_ollama_provider_complete_no_host_or_timeout_uses_client_defaults(fake_ollama: _Recorder) -> None:
    OllamaProvider(model="llama3").complete("Which group?")

    assert fake_ollama.client_kwargs == {}


def test_ollama_provider_complete_passes_host_and_timeout_to_client(fake_ollama: _Recorder) -> None:
    OllamaProvider(model="llama3", host="http://gpu-box:11434", timeout=30).complete("Which group?")

    assert fake_ollama.client_kwargs == {"host": "http://gpu-box:11434", "timeout": 30}


@pytest.mark.parametrize(
    ("raised", "tip_part"),
    [
        (_StatusError("model 'llama3' not found", 404), "ollama pull llama3"),
        (ConnectionError("Failed to connect to Ollama"), "ollama serve"),
        (TimeoutError("timed out"), "[ai] timeout"),
        (ModuleNotFoundError("No module named 'ollama'"), "uv sync --package core --extra ai"),
    ],
)
def test_ollama_provider_complete_known_failure_raises_with_tip(
    fake_ollama: _Recorder, raised: Exception, tip_part: str
) -> None:
    fake_ollama.error = raised

    with pytest.raises(AIProviderError) as exc_info:
        OllamaProvider(model="llama3").complete("Which group?")

    assert tip_part in exc_info.value.tip
    assert exc_info.value.__cause__ is raised


def test_ollama_provider_complete_unknown_failure_propagates_unchanged(fake_ollama: _Recorder) -> None:
    fake_ollama.error = ValueError("odd")

    with pytest.raises(ValueError, match="odd"):
        OllamaProvider(model="llama3").complete("Which group?")


# endregion


# endregion
