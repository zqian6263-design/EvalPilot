"""Fakes for the live-LLM tests.

Everything here is offline by construction. Two kinds of fake are provided:

- :class:`ScriptedProvider` — a provider whose responses the test dictates, so
  success, schema violations, malformed JSON, timeouts and transport failures
  can each be exercised without a socket.
- :func:`openai_transport` — an ``httpx.MockTransport`` that speaks the
  OpenAI-compatible envelope, so the real client is exercised end to end
  against a canned HTTP response.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from evalpilot.llm.errors import LLMError
from evalpilot.llm.providers import LLMResult, Message

#: A key that must never appear in a response body, a log, or an exception.
CANARY_KEY = "sk-canary-must-never-leak-0123456789"

#: A valid hypothesis proposal citing a scenario the demo run really has.
VALID_HYPOTHESES: dict[str, Any] = {
    "hypotheses": [
        {
            "kind": "domain:returns",
            "claim": "The compression step also affects returns answers",
            "mechanism": "Clause removal is not limited to the escalated domains.",
            "scenario_ids": ["prompt-injection-password"],
            "confidence": 0.4,
        }
    ],
    "discarded": [],
}

#: A valid rationale that *agrees* with the measured decision.
VALID_RATIONALE: dict[str, Any] = {
    "rationale": "The measured drop and the replay agree: compression removal repairs it.",
    "evidence_ids": [],
    "recommendations": ["Re-run the adversarial scenarios after restoring the guard."],
}

#: A rationale that tries to override the measured verdict.
OVERRIDING_RATIONALE: dict[str, Any] = {
    "verdict": "allow",
    "risk_level": "low",
    "rationale": "I judge this safe to ship despite the measured failures.",
    "evidence_ids": [],
    "recommendations": [],
}


class ScriptedProvider:
    """A provider that returns whatever the test queued for it.

    ``responses`` is a list of either a payload dict (returned as a successful
    :class:`~evalpilot.llm.providers.LLMResult`) or an exception instance
    (raised). Each call pops the next entry; the last entry repeats, so a test
    does not have to enqueue one response per call.
    """

    name = "scripted-fake"

    def __init__(
        self,
        responses: list[Any],
        *,
        model: str = "fake-model",
        call_id: str = "fake-call-id",
    ) -> None:
        self.responses = list(responses) or [{}]
        self.model = model
        self.call_id = call_id
        self.calls: list[list[Message]] = []
        self.schemas: list[dict[str, Any]] = []

    def _next(self) -> Any:
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]

    async def complete_json(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> LLMResult:
        self.calls.append(list(messages))
        self.schemas.append(schema)
        item = self._next()
        if isinstance(item, BaseException):
            raise item
        return LLMResult(
            payload=dict(item),
            model=self.model,
            call_id=self.call_id,
            provider=self.name,
        )

    async def complete_text(
        self,
        messages: list[Message],
        timeout_seconds: float | None = None,
    ) -> str:
        self.calls.append(list(messages))
        item = self._next()
        if isinstance(item, BaseException):
            raise item
        return json.dumps(item)


def openai_transport(
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
    *,
    content: str | None = None,
    status_code: int = 200,
) -> httpx.MockTransport:
    """An ``httpx.MockTransport`` that answers like a chat-completions endpoint.

    With no arguments it returns a well-formed envelope wrapping ``content``
    (or an empty JSON object).
    """
    if handler is not None:
        return httpx.MockTransport(handler)

    body = content if content is not None else "{}"

    def _respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"choices": [{"message": {"role": "assistant", "content": body}}]},
        )

    return httpx.MockTransport(_respond)


def recording_handler(
    content: str,
    *,
    status_code: int = 200,
    seen: list[httpx.Request] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """A transport handler that records every request it receives."""

    def _handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(
            status_code,
            json={"choices": [{"message": {"content": content}}]},
        )

    return _handler


__all__ = [
    "CANARY_KEY",
    "OVERRIDING_RATIONALE",
    "ScriptedProvider",
    "VALID_HYPOTHESES",
    "VALID_RATIONALE",
    "LLMError",
    "openai_transport",
    "recording_handler",
]
