"""Tests for sorting provider failures into kinds and describing them with a fix-it tip."""

import pytest
from microfiche.core.ai.base import AIProviderError, describe_ai_failure, failure_kind

# region Test helpers


class ResponseError(Exception):
    """Stands in for a client library's HTTP error, which carries a status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class APIConnectionError(Exception):
    """Stands in for a client library's connection error, which is not a builtin ``ConnectionError``."""


class APITimeoutError(APIConnectionError):
    """Stands in for a client library's timeout, which subclasses its connection error."""


# endregion


# region Public API


# region failure_kind


@pytest.mark.parametrize(
    ("err", "kind"),
    [
        (ModuleNotFoundError("No module named 'ollama'"), "missing_package"),
        (ResponseError("model not found", 404), "not_found"),
        (ResponseError("bad key", 401), "unauthorized"),
        (ResponseError("forbidden", 403), "unauthorized"),
        (ConnectionError("refused"), "unreachable"),
        (APIConnectionError("down"), "unreachable"),
        (TimeoutError("timed out"), "timeout"),
        (APITimeoutError("timed out"), "timeout"),  # a timeout wins over the connection error it subclasses
        (ResponseError("overloaded", 503), None),
        (ValueError("anything else"), None),
    ],
)
def test_failure_kind_sorts_known_failures(err: Exception, kind: str | None) -> None:
    assert failure_kind(err) == kind


# endregion


# region describe_ai_failure


def test_describe_ai_failure_plain_exception_is_describe_error() -> None:
    assert describe_ai_failure(ValueError("boom")) == "ValueError: boom"


def test_describe_ai_failure_provider_error_appends_tip() -> None:
    err = AIProviderError("ResponseError: model not found", "Run `ollama pull x`.")

    assert describe_ai_failure(err) == "ResponseError: model not found. Run `ollama pull x`."


# endregion


# endregion
