"""Local model inference via Ollama.

Keeps classification fully offline per the PRD's privacy constraints. Requires a running local
Ollama server and the optional `ollama` dependency (``uv sync --package core --extra ai``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from microfiche.core.ai.base import FailureKind, tip_error


@dataclass
class OllamaProvider:
    """Talks to a local Ollama server."""

    model: str
    host: str | None = None
    timeout: float | None = None

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` to the model and return its reply.

        Args:
            prompt: The prompt to complete.

        Returns:
            The model's reply text.
        """

        try:
            import ollama  # optional dependency, only needed when this provider is actually used

            options: dict[str, Any] = {}
            if self.host:
                options["host"] = self.host
            if self.timeout is not None:
                options["timeout"] = self.timeout
            client: Any = ollama.Client(**options)
            response: Any = client.chat(model=self.model, messages=[{"role": "user", "content": prompt}])
            return str(response["message"]["content"])
        except Exception as err:
            wrapped = tip_error(err, self._tips())
            if wrapped is None:
                raise
            raise wrapped from err

    def _tips(self) -> dict[FailureKind, str]:
        """What to do about each failure the Ollama client can raise."""

        return {
            "not_found": f"Run `ollama pull {self.model}`, or set [ai] model to one `ollama list` shows.",
            "unreachable": "Start Ollama (`ollama serve`), or check [ai] host. If it was running, it may have dropped the call (out of memory?).",
            "timeout": "Raise [ai] timeout, or use a smaller model.",
            "missing_package": "Install the ollama package (from a source checkout: `uv sync --package core --extra ai`).",
        }
