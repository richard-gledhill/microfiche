"""Cloud model inference via the OpenAI API - optional, per the PRD's "cloud LLM support" section.

Requires an API key in the environment and the optional `openai` dependency (``uv sync --package core --extra ai``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from microfiche.core.ai.base import FailureKind, tip_error


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

        try:
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
        except Exception as err:
            wrapped = tip_error(err, self._tips())
            if wrapped is None:
                raise
            raise wrapped from err

    def _tips(self) -> dict[FailureKind, str]:
        """What to do about each failure the OpenAI client can raise."""

        return {
            "not_found": "Check that [ai] model names a model your OpenAI account can use.",
            "unauthorized": "Check the key in the environment variable named by [ai] api_key_env.",
            "unreachable": "Check your network connection.",
            "timeout": "Raise [ai] timeout, or use a smaller model.",
            "missing_package": "Install the openai package (from a source checkout: `uv sync --package core --extra ai`).",
        }
