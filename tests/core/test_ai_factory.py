"""Tests for building the configured AI provider."""

from pathlib import Path
from typing import Any

import pytest
from microfiche.core.ai.factory import build_provider
from microfiche.core.ai.ollama_provider import OllamaProvider
from microfiche.core.ai.openai_provider import OpenAIProvider
from microfiche.core.config import AIConfig, ConfigError, load_config

# region Test helpers


def _settings(**overrides: Any) -> AIConfig:
    """The packaged ``[ai]`` settings with ``overrides`` applied."""
    return load_config(Path("does-not-exist")).ai.model_copy(update=overrides)


# endregion


# region Public API


# region build_provider


def test_build_provider_default_settings_give_ollama_with_its_own_defaults() -> None:
    provider = build_provider(_settings())

    assert provider == OllamaProvider(timeout=120)


def test_build_provider_ollama_settings_passed_through() -> None:
    provider = build_provider(_settings(model="mistral", host="http://gpu-box:11434", timeout=30))

    assert provider == OllamaProvider(model="mistral", host="http://gpu-box:11434", timeout=30)


def test_build_provider_openai_reads_key_from_named_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_OPENAI_KEY", "sk-test")

    provider = build_provider(_settings(provider="openai", api_key_env="MY_OPENAI_KEY", model="gpt-4o", timeout=30))

    assert provider == OpenAIProvider(model="gpt-4o", api_key="sk-test", timeout=30)


def test_build_provider_openai_empty_model_uses_provider_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    provider = build_provider(_settings(provider="openai"))

    assert isinstance(provider, OpenAIProvider)
    assert provider.model == OpenAIProvider().model


@pytest.mark.parametrize("value", [None, ""])
def test_build_provider_openai_missing_key_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", value)

    with pytest.raises(ConfigError, match="OPENAI_API_KEY") as exc_info:
        build_provider(_settings(provider="openai"))

    assert "environment variable" in str(exc_info.value)


def test_build_provider_ollama_ignores_openai_key_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert isinstance(build_provider(_settings()), OllamaProvider)


# endregion


# endregion
