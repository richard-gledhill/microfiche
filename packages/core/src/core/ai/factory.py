"""Builds the AI provider that the library's ``[ai]`` settings name."""

from __future__ import annotations

import os

from core.ai.base import AIProvider
from core.ai.ollama_provider import OllamaProvider
from core.ai.openai_provider import OpenAIProvider
from core.config import AIConfig, MissingApiKeyError

# region Public API


def build_provider(config: AIConfig) -> AIProvider:
    """Build the provider named by ``config.provider``, with its model, address and timeout.

    An empty ``model`` leaves the choice to the provider's own default. The OpenAI key is read from the
    environment variable named by ``api_key_env``; it is never part of the configuration.

    Args:
        config: The library's ``[ai]`` settings.

    Returns:
        The provider to hand to ``LLMClassifier``.

    Raises:
        MissingApiKeyError: If the provider is ``"openai"`` and its key variable is unset or empty (a
            ``ConfigError``).
    """

    model = {"model": config.model} if config.model else {}
    if config.provider == "openai":
        api_key = os.environ.get(config.api_key_env, "")
        if not api_key:
            raise MissingApiKeyError(config.api_key_env)
        return OpenAIProvider(**model, api_key=api_key, timeout=config.timeout)
    return OllamaProvider(**model, host=config.host or None, timeout=config.timeout)


# endregion
