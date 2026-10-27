"""Cloud model inference via the OpenAI API - optional, per the PRD's "cloud LLM support" section.

Requires an API key in the environment and the optional `openai` dependency (``uv sync --extra ai``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpenAIProvider:
    """Talks to the OpenAI API."""

    model: str
    api_key: str | None = field(default=None, repr=False)
    timeout: float | None = None

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` to the model and return its reply.

        Args:
            prompt: The prompt to complete.

        Returns:
            The model's reply text, or an empty string if it returned none.
        """

        from openai import OpenAI  # optional dependency, only needed when this provider is actually used

        options: dict[str, Any] = {}
        if self.api_key:
            options["api_key"] = self.api_key
        if self.timeout is not None:
            options["timeout"] = self.timeout
        client: Any = OpenAI(**options)
        response: Any = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        return str(content) if content else ""
