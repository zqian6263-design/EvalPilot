"""The provider seam.

:class:`LLMProvider` is the protocol every implementation satisfies, and
:class:`LLMResult` is what a call returns: the parsed payload plus the
provenance the contract requires on every LLM-generated step
(``data.source``, ``data.model``, ``data.llm_call_id``).

The protocol is async because the only implementation makes HTTP requests, and
it is deliberately narrow — two methods, both taking the same ``messages``
shape an OpenAI-compatible endpoint expects. Everything above this seam (the
investigation, the judge) depends on the protocol, never on httpx.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from evalpilot.llm.errors import LLMError

#: One chat message, in the OpenAI-compatible ``{"role", "content"}`` shape.
Message = dict[str, str]


@dataclass(frozen=True)
class LLMResult:
    """One successful structured completion, with its provenance.

    ``call_id`` is the trace id recorded as ``data.llm_call_id`` on every step
    the model produced, so a step in a report can be traced back to the exact
    call that generated it.
    """

    payload: dict[str, Any]
    model: str
    call_id: str
    provider: str
    source: str = "llm"
    usage: dict[str, int] | None = None

    def provenance(self) -> dict[str, Any]:
        """The three keys the contract puts on an LLM-generated step."""
        provenance = {
            "source": self.source,
            "model": self.model,
            "llm_call_id": self.call_id,
        }
        if self.usage is not None:
            provenance["usage"] = self.usage
        return provenance


@runtime_checkable
class LLMProvider(Protocol):
    """An OpenAI-compatible chat-completions endpoint, behind a schema.

    Implementations must:

    - never raise anything but an :class:`~evalpilot.llm.errors.LLMError`
      subclass, so a caller can build a fallback reason from a typed failure;
    - never include the API key in an error message, a return value, or a log;
    - validate the completion against the supplied ``schema`` and fail rather
      than returning a partially parsed payload.
    """

    #: Short identifier for the implementation, recorded on every result.
    name: str
    #: The model id the endpoint was configured with.
    model: str

    async def complete_json(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> LLMResult:
        """Return a schema-validated JSON object from the model.

        Raises:
            LLMError: a subclass, describing why the call could not be used.
        """
        ...

    async def complete_text(
        self,
        messages: list[Message],
        timeout_seconds: float | None = None,
    ) -> str:
        """Return the model's raw text content.

        Raises:
            LLMError: a subclass, describing why the call could not be used.
        """
        ...
