"""Local model inference via Ollama.

Keeps classification fully offline per the PRD's privacy constraints. Requires a running local
Ollama server and the optional `ollama` dependency (``uv sync --extra ai``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OllamaProvider:
    """Talks to a local Ollama server."""

    model: str = "llama3"
    host: str | None = None
    timeout: float | None = None

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` to the model and return its reply.

        Args:
            prompt: The prompt to complete.

        Returns:
            The model's reply text.
        """

        import ollama  # optional dependency, only needed when this provider is actually used

        options: dict[str, Any] = {}
        if self.host:
            options["host"] = self.host
        if self.timeout is not None:
            options["timeout"] = self.timeout
        client: Any = ollama.Client(**options)
        response: Any = client.chat(model=self.model, messages=[{"role": "user", "content": prompt}])
        return str(response["message"]["content"])
