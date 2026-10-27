"""Builds the AI provider that the library's ``[ai]`` settings name."""

from __future__ import annotations

import os

from microfiche.core.ai.base import AIProvider
from microfiche.core.ai.ollama_provider import OllamaProvider
from microfiche.core.ai.openai_provider import OpenAIProvider
from microfiche.core.config import AIConfig, EmptyModelError, MissingApiKeyError

# region Public API


def build_provider(config: AIConfig) -> AIProvider:
    """Build the provider named by ``config.provider``, with its model, address and timeout.

    The model is always the one the user named: there is no provider default. The OpenAI key is read from the
    environment variable named by ``api_key_env``; it is never part of the configuration.

    Args:
        config: The library's ``[ai]`` settings.

    Returns:
        The provider to hand to ``LLMClassifier``.

    Raises:
        EmptyModelError: If ``model`` is empty (a ``ConfigError``).
        MissingApiKeyError: If the provider is ``"openai"`` and its key variable is unset or empty (a
            ``ConfigError``).
    """

    if not config.model:
        raise EmptyModelError(config.provider)
    if config.provider == "openai":
        api_key = os.environ.get(config.api_key_env, "")
        if not api_key:
            raise MissingApiKeyError(config.api_key_env)
        return OpenAIProvider(model=config.model, api_key=api_key, timeout=config.timeout)
    return OllamaProvider(model=config.model, host=config.host or None, timeout=config.timeout)


# endregion
