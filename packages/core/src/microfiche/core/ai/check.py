"""A one-call test of the configured AI, run before a ``--use-ai`` command touches any document."""

from __future__ import annotations

import time
from dataclasses import dataclass

from microfiche.core.ai.base import AIProvider, describe_ai_failure
from microfiche.core.ai.factory import build_provider
from microfiche.core.config import AIConfig

# region Constants and types

_PROMPT = "Reply with the single word: OK"


@dataclass(frozen=True)
class AICheck:
    """What the check found.

    Attributes:
        ok: Whether the provider answered.
        detail: One line for the user: who answered and how fast, or what failed and what to do about it.
        seconds: How long the call took.
    """

    ok: bool
    detail: str
    seconds: float


# endregion


# region Public API


def check_ai(config: AIConfig, provider: AIProvider | None = None) -> AICheck:
    """Ask the configured provider one question that has nothing to do with any document.

    Any reply counts: models are chatty, so the answer is not compared with ``OK``. With Ollama the call also
    loads the model, so the first real answer is not slow. It uses the normal ``[ai] timeout``.

    Args:
        config: The library's ``[ai]`` settings.
        provider: The provider to test, when the caller has built it already. Built from ``config`` when omitted.

    Returns:
        The result. It never raises: a missing key, an empty model, a missing package and a provider failure all
        come back as ``ok=False`` with the reason, and a fix where the provider knew one, in ``detail``.
    """

    started = time.perf_counter()
    try:
        reply = (provider or build_provider(config)).complete(_PROMPT)
    except Exception as err:
        return AICheck(ok=False, detail=describe_ai_failure(err), seconds=time.perf_counter() - started)
    seconds = time.perf_counter() - started
    if not reply.strip():
        return AICheck(ok=False, detail="the model returned an empty reply", seconds=seconds)
    return AICheck(ok=True, detail=f"{config.provider} {config.model} answered in {seconds:.1f} s", seconds=seconds)


# endregion
