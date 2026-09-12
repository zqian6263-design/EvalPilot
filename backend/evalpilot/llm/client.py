"""OpenAI-compatible chat-completions client over ``httpx``.

One implementation, one endpoint shape: ``POST {base_url}/chat/completions``
with ``Authorization: Bearer <key>``. That is what DeepSeek, OpenAI and most
compatible gateways speak, so one client covers the documented setup.

Two properties matter more than the plumbing:

**The key never leaves this module.** It is used to build one header and is
never included in a return value, an exception message, or a log line. Error
text is built from the base URL's *host*, the status code and the HTTP
library's own message.

**``transport`` is injectable.** Tests pass ``httpx.MockTransport`` and the
suite never opens a socket. There is no code path here that reaches the
network unless an ``httpx`` client does.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import httpx

from evalpilot.clock import new_id
from evalpilot.llm.errors import (
    LLMConfigurationError,
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTransportError,
)
from evalpilot.llm.providers import LLMResult, Message
from evalpilot.llm.schema import validate_json_schema

#: Some gateways require it; harmless everywhere. The contract asks for an
#: OpenAI-compatible endpoint, and every one of them accepts this shape.
JSON_RESPONSE_FORMAT: dict[str, str] = {"type": "json_object"}

#: Default when neither the call nor the settings supply one.
DEFAULT_TIMEOUT_SECONDS = 45.0

#: Cap on a completion. Generous enough for a handful of hypotheses or one
#: rationale; low enough that a runaway generation cannot stall an
#: investigation.
MAX_TOKENS = 1024


class OpenAICompatibleProvider:
    """An :class:`~evalpilot.llm.providers.LLMProvider` over HTTP.

    Args:
        base_url: Endpoint root, e.g. ``https://api.deepseek.com``. A trailing
            slash is tolerated, as is a base URL that already ends in
            ``/v1``.
        api_key: Secret. Used for one header and nothing else.
        model: The model id sent in the request body.
        timeout_seconds: Default per-request timeout.
        transport: Optional ``httpx`` transport. Tests inject
            ``httpx.MockTransport`` here; production leaves it ``None``.
    """

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = api_key or ""
        self.model = (model or "").strip()
        self.timeout_seconds = (
            DEFAULT_TIMEOUT_SECONDS if timeout_seconds is None else float(timeout_seconds)
        )
        self._transport = transport

    # -- the contract --------------------------------------------------------

    async def complete_json(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> LLMResult:
        """Request JSON, parse it, and validate it against ``schema``.

        Raises:
            LLMConfigurationError: the provider is unusable as configured.
            LLMTimeoutError: the request exceeded its timeout.
            LLMTransportError: the request never produced a usable response.
            LLMResponseError: the response was not a usable completion.
            LLMSchemaError: the completion parsed but violated the schema.
        """
        self._check_configured()
        content = await self._post(
            messages,
            timeout_seconds=timeout_seconds,
            force_json=True,
        )
        payload = _parse_json_object(content)
        validate_json_schema(payload, schema)
        return self._result(payload)

    async def complete_text(
        self,
        messages: list[Message],
        timeout_seconds: float | None = None,
    ) -> str:
        """Request a plain-text completion.

        Raises:
            LLMConfigurationError: the provider is unusable as configured.
            LLMTimeoutError: the request exceeded its timeout.
            LLMTransportError: the request never produced a usable response.
            LLMResponseError: the response was not a usable completion.
        """
        self._check_configured()
        return await self._post(messages, timeout_seconds=timeout_seconds)

    # -- internals -----------------------------------------------------------

    def _check_configured(self) -> None:
        """Fail before the request, not after, when configuration is missing."""
        if not self.base_url:
            raise LLMConfigurationError(
                "no LLM base URL is configured (set EVALPILOT_LLM_BASE_URL)"
            )
        if not self.api_key:
            raise LLMConfigurationError(
                "no LLM API key is configured (set EVALPILOT_LLM_API_KEY)"
            )
        if not self.model:
            raise LLMConfigurationError(
                "no LLM model is configured (set EVALPILOT_LLM_MODEL)"
            )

    @property
    def host(self) -> str:
        """The base URL's host, for status reporting. Never the full URL."""
        return urlsplit(self.base_url).netloc or urlsplit(self.base_url).path

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    async def _post(
        self,
        messages: list[Message],
        *,
        timeout_seconds: float | None,
        force_json: bool = False,
    ) -> str:
        timeout = float(
            self.timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        if timeout <= 0:
            raise LLMConfigurationError(
                f"invalid LLM timeout {timeout}; it must be greater than zero"
            )

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": MAX_TOKENS,
            "stream": False,
        }
        if force_json:
            body["response_format"] = JSON_RESPONSE_FORMAT

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=timeout,
            ) as client:
                response = await client.post(
                    self.endpoint,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"LLM request to {self.host} timed out after {timeout:g}s"
            ) from exc
        except httpx.HTTPError as exc:
            # ``httpx`` error text describes the connection, not the request
            # headers, so it is safe to forward.
            raise LLMTransportError(
                f"LLM request to {self.host} failed: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise LLMTransportError(
                f"LLM endpoint {self.host} returned HTTP {response.status_code}",
                status=response.status_code,
            )

        return _extract_content(response, self.host)

    def _result(self, payload: dict[str, Any]) -> LLMResult:
        return LLMResult(
            payload=payload,
            model=self.model,
            call_id=new_id(),
            provider=self.name,
        )


def _extract_content(response: httpx.Response, host: str) -> str:
    """Pull ``choices[0].message.content`` out of a completion envelope.

    Raises:
        LLMResponseError: if the body is not JSON, or does not carry a string
            message content.
    """
    try:
        envelope = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMResponseError(
            f"LLM endpoint {host} returned a body that is not JSON: {exc}"
        ) from exc

    if not isinstance(envelope, dict):
        raise LLMResponseError(
            f"LLM endpoint {host} returned {type(envelope).__name__}, expected an object"
        )

    try:
        message = envelope["choices"][0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMResponseError(
            f"LLM endpoint {host} returned a completion without "
            "choices[0].message.content"
        ) from exc

    if not isinstance(content, str):
        raise LLMResponseError(
            f"LLM endpoint {host} returned "
            f"{type(content).__name__} content, expected a string"
        )
    return content


def _parse_json_object(content: str) -> dict[str, Any]:
    """Parse model content that is supposed to be a single JSON object.

    A wrapping markdown fence is stripped first: models emit it routinely, it
    is a formatting quirk rather than a schema violation, and the judge
    protocol already tolerates it. Nothing else is tolerated.

    Raises:
        LLMResponseError: if the text is not valid JSON, or is not an object.
        LLMSchemaError: if the text contains NaN or Infinity, which are not
            JSON values but which ``json.loads`` accepts by default.
    """
    text = _strip_code_fence(content)
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise LLMResponseError(f"LLM returned content that is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LLMResponseError(
            f"LLM returned a JSON {type(payload).__name__}, expected an object"
        )
    return payload


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()[1:]  # drop the opening fence and any language tag
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _reject_json_constant(name: str) -> float:
    raise LLMSchemaError(
        f"LLM output failed schema validation: {name} is not a JSON value"
    )


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "JSON_RESPONSE_FORMAT",
    "MAX_TOKENS",
    "OpenAICompatibleProvider",
]
