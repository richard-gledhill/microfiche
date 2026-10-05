"""Cloud model inference via the OpenAI API - optional, per the PRD's "cloud LLM support" section.

Requires an API key in the environment and the optional `openai` dependency (``uv sync --extra ai``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OpenAIProvider:
    """Talks to the OpenAI API."""

    model: str = "gpt-4o-mini"

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` to the model and return its reply.

        Args:
            prompt: The prompt to complete.

        Returns:
            The model's reply text, or an empty string if it returned none.
        """

        from openai import OpenAI  # optional dependency, only needed when this provider is actually used

        client: Any = OpenAI()
        response: Any = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        return str(content) if content else ""
