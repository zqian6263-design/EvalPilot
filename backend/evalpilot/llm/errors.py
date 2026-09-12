"""Typed LLM failures.

Every failure mode this package can hit has its own type, because the caller
has to *say why* it fell back to deterministic behaviour and "the model call
failed" is not an answer a reviewer can act on. A timeout is an infrastructure
problem; a schema violation is a prompt or model problem; a missing API key is
a configuration problem. They are recorded separately.

No exception in this module ever carries the API key. Messages are built from
the base URL host, the model id, a status code and the HTTP library's own error
text, never from the request headers.
"""

from __future__ import annotations


class LLMError(RuntimeError):
    """Base class for every failure raised by the live-LLM runtime."""


class LLMConfigurationError(LLMError):
    """The provider cannot be used as configured.

    Raised for a missing base URL, a missing API key, or an unusable timeout.
    Surfaces before any request is attempted.
    """


class LLMTransportError(LLMError):
    """The request never produced a usable HTTP response.

    Connection failures, DNS failures and non-2xx statuses all land here. The
    ``status`` attribute is set for the HTTP case and ``None`` otherwise.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class LLMTimeoutError(LLMTransportError):
    """The request exceeded its timeout.

    A subclass of :class:`LLMTransportError` so a caller that only cares "the
    call did not come back" can catch one type, while a caller building a
    fallback reason can still say "timeout" specifically.
    """


class LLMResponseError(LLMError):
    """The endpoint answered, but not with a usable completion.

    Malformed JSON, a missing ``choices`` array, or content that is not JSON
    at all when JSON was requested.
    """


class LLMSchemaError(LLMError):
    """The completion parsed as JSON but did not satisfy the requested schema.

    Distinct from :class:`LLMResponseError` because the two have different
    remedies: a malformed response is a transport problem, a schema violation
    is a model or prompt problem.
    """
