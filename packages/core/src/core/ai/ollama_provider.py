"""Local model inference via Ollama - keeps classification fully offline per the PRD's privacy
constraints. Requires a running local Ollama server and the optional `ollama` dependency
(``uv sync --extra ai``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OllamaProvider:
    """Talks to a local Ollama server."""

    model: str = "llama3"
    host: str | None = None

    def complete(self, prompt: str) -> str:
        import ollama  # optional dependency, only needed when this provider is actually used

        client: Any = ollama.Client(host=self.host) if self.host else ollama.Client()
        response: Any = client.chat(model=self.model, messages=[{"role": "user", "content": prompt}])
        return str(response["message"]["content"])
