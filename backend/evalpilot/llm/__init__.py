"""Optional live-LLM runtime.

The default EvalPilot deployment is deterministic, offline, and needs no API
key. This package adds the *optional* seam that turns a run's investigation
into one that also consults a real model, without weakening anything the
deterministic path guarantees:

- :class:`~evalpilot.llm.providers.LLMProvider` — the protocol a provider
  implements. It is async and returns validated JSON, never raw text.
- :mod:`~evalpilot.llm.errors` — typed failures, so a caller can distinguish
  "the network was down" from "the model returned nonsense" and record an
  explicit fallback reason for either.
- :mod:`~evalpilot.llm.schema` — the strict JSON-schema validator. A model
  response that does not satisfy the schema is a failure, not a best-effort
  parse.
- :mod:`~evalpilot.llm.client` — an OpenAI-compatible ``/chat/completions``
  client over ``httpx``, injectable so tests never touch the network.
- :mod:`~evalpilot.llm.prompts` — the prompt builders and the JSON shapes the
  investigation asks for.
- :mod:`~evalpilot.llm.apply` — sanitizes a validated proposal against the
  run's real scenario and evidence ids before anything is persisted.
- :mod:`~evalpilot.llm.runtime` — the one place the settings' mode and key are
  read, resolved into a provider or an explicit configuration error.

Everything the model produces here is *advisory*. Risk hypotheses, rationales
and recommendations are augmented with model output; the measured verdict,
risk level, blocking findings, evidence ids and counterfactual results are
never taken from a model.
"""

from __future__ import annotations

from evalpilot.llm.apply import sanitize_hypotheses, sanitize_rationale
from evalpilot.llm.client import OpenAICompatibleProvider
from evalpilot.llm.errors import (
    LLMConfigurationError,
    LLMError,
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTransportError,
)
from evalpilot.llm.providers import LLMProvider, LLMResult
from evalpilot.llm.runtime import (
    MODE_DETERMINISTIC,
    MODE_LIVE,
    LLMRuntime,
    build_runtime,
)
from evalpilot.llm.schema import validate_json_schema

__all__ = [
    "LLMConfigurationError",
    "LLMError",
    "LLMProvider",
    "LLMResponseError",
    "LLMResult",
    "LLMRuntime",
    "LLMSchemaError",
    "LLMTimeoutError",
    "LLMTransportError",
    "MODE_DETERMINISTIC",
    "MODE_LIVE",
    "OpenAICompatibleProvider",
    "build_runtime",
    "sanitize_hypotheses",
    "sanitize_rationale",
    "validate_json_schema",
]
