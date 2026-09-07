"""Common interface every AI provider (Ollama, OpenAI, ...) must implement."""

from __future__ import annotations

from typing import Protocol


class AIProvider(Protocol):
    """Minimal chat-completion interface microfiche's AI fallback needs from any provider."""

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` to the model and return its raw text response."""
        ...
