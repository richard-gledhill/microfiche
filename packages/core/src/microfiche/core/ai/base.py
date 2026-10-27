"""Common interface every AI provider (Ollama, OpenAI, ...) must implement, and how their failures are described."""

from __future__ import annotations

from typing import Literal, Protocol

from microfiche.core.utils.errors import describe_error

# region Constants and types

FailureKind = Literal["missing_package", "timeout", "unreachable", "not_found", "unauthorized"]
"""The provider failures that have a known next step."""


class AIProvider(Protocol):
    """Minimal chat-completion interface microfiche's AI fallback needs from any provider."""

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` to the model and return its raw text response."""
        ...


# endregion


# region Errors


class AIProviderError(Exception):
    """A provider failure that comes with a one-line next step.

    Attributes:
        detail: What went wrong, as ``describe_error`` wrote it for the original exception.
        tip: What to do about it.
    """

    def __init__(self, detail: str, tip: str) -> None:
        self.detail = detail
        self.tip = tip
        super().__init__(f"{detail}. {tip}")


# endregion


# region Public API


def failure_kind(err: BaseException) -> FailureKind | None:
    """Sort a client library's exception into a failure with a known next step.

    The providers wrap third-party libraries that share no exception base and are optional installs, so the
    exceptions are recognised by their builtin base, by their status code, or by their class names.

    Args:
        err: The exception a provider's client raised.

    Returns:
        The kind of failure, or ``None`` if it is not one of the known ones.
    """

    names = [cls.__name__ for cls in type(err).__mro__]
    status = getattr(err, "status_code", None)
    if isinstance(err, ModuleNotFoundError):
        return "missing_package"
    if isinstance(err, TimeoutError) or any("Timeout" in name for name in names):
        return "timeout"  # before "unreachable": a client's timeout often subclasses its connection error
    if isinstance(err, ConnectionError) or any("Connect" in name for name in names):
        return "unreachable"
    if status == 404:
        return "not_found"
    if status in (401, 403):
        return "unauthorized"
    return None


def tip_error(err: BaseException, tips: dict[FailureKind, str]) -> AIProviderError | None:
    """``err`` as an ``AIProviderError`` carrying the provider's tip for its kind, if it has one.

    Args:
        err: The exception a provider's client raised.
        tips: The provider's next step for each kind of failure it can advise on.

    Returns:
        The error to raise in its place, or ``None`` to let ``err`` propagate unchanged.
    """

    kind = failure_kind(err)
    if kind is None or kind not in tips:
        return None
    return AIProviderError(describe_error(err), tips[kind])


def describe_ai_failure(err: BaseException) -> str:
    """One line a person can act on: what failed and, where the provider knew it, what to do.

    Args:
        err: The exception a provider raised.

    Returns:
        ``describe_error(err)``, or an ``AIProviderError``'s detail followed by its tip.
    """

    if isinstance(err, AIProviderError):
        return f"{err.detail}. {err.tip}"
    return describe_error(err)


# endregion
