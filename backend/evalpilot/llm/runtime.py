"""Which LLM runtime a settings object resolves to.

This module is the one place that decides whether live mode is on, and it is
the only place that reads the API key. Everything downstream receives a
:class:`LLMRuntime` and a provider — never the settings' credential — so a
route, a report or an error message has nothing to leak.

The three states are deliberately distinct, because "live mode is on" and "the
model is reachable" are different claims and the UI has to be able to tell
them apart:

``deterministic``
    No provider. Nothing consults a model; the demo is byte-for-byte
    reproducible.
``live`` with ``configured=True``
    A provider is installed and the model is used where the contract allows.
``live`` with ``configured=False``
    The mode was requested but the configuration is incomplete. A provider is
    *not* installed, so the investigation and the judge behave exactly as in
    deterministic mode rather than attempting a request that must fail. The
    reason is carried in :attr:`LLMRuntime.configuration_error` and surfaced
    on ``GET /api/runtime``.

Falling back silently would be the wrong behaviour: an operator who set
``EVALPILOT_LLM_MODE=live`` and forgot the key should be told, not shown a
deterministic report that looks live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evalpilot.llm.providers import LLMProvider

MODE_DETERMINISTIC = "deterministic"
MODE_LIVE = "live"

#: The modes the contract names. Anything else is a configuration error.
KNOWN_MODES: tuple[str, ...] = (MODE_DETERMINISTIC, MODE_LIVE)


@dataclass
class LLMRuntime:
    """The resolved LLM configuration for one application container."""

    mode: str = MODE_DETERMINISTIC
    configured: bool = False
    provider: LLMProvider | None = None
    model: str | None = None
    base_url_host: str | None = None
    timeout_seconds: float = 45.0
    configuration_error: str | None = None
    #: Reasons any LLM call has fallen back during this process's lifetime.
    #: Bounded and de-duplicated; it is a status, not a log.
    fallback_reasons: list[str] = field(default_factory=list)

    @property
    def live(self) -> bool:
        """Live mode *with* a usable provider. The only state that calls out."""
        return self.mode == MODE_LIVE and self.provider is not None

    @property
    def fallback_active(self) -> bool:
        """An LLM call was attempted and did not produce usable output.

        ``False`` in deterministic mode: nothing was attempted, so nothing
        fell back. That distinction is why the flag is not simply
        ``mode == "live"``.
        """
        return bool(self.fallback_reasons)

    def record_fallback(self, reason: str) -> None:
        """Note why a call fell back, de-duplicated and bounded."""
        text = str(reason).strip()
        if not text or text in self.fallback_reasons:
            return
        self.fallback_reasons.append(text)
        del self.fallback_reasons[:-8]

    def status(self, *, tools: list[str]) -> dict[str, Any]:
        """The ``GET /api/runtime`` payload.

        Contains no credential of any kind: ``base_url_host`` is the URL's
        host only, and the key is not represented at all.
        """
        return {
            "mode": self.mode,
            "llm_configured": self.configured,
            "model": self.model,
            "base_url_host": self.base_url_host,
            "fallback_active": self.fallback_active,
            "tools": list(tools),
        }


def build_runtime(settings: Any) -> LLMRuntime:
    """Resolve ``settings`` into an :class:`LLMRuntime`.

    Import of the httpx client is deferred: in deterministic mode — the
    default, and the only mode the offline demo uses — nothing from the HTTP
    stack is loaded at all.
    """
    mode = str(getattr(settings, "llm_mode", MODE_DETERMINISTIC) or MODE_DETERMINISTIC)
    timeout = float(getattr(settings, "llm_timeout_seconds", 45.0) or 45.0)
    base_url = getattr(settings, "llm_base_url", None)
    api_key = getattr(settings, "llm_api_key", None)
    model = getattr(settings, "llm_model", None)

    runtime = LLMRuntime(mode=mode, timeout_seconds=timeout)

    if mode not in KNOWN_MODES:
        runtime.mode = MODE_DETERMINISTIC
        runtime.configuration_error = (
            f"unknown EVALPILOT_LLM_MODE {mode!r}; expected one of {list(KNOWN_MODES)}. "
            "Running deterministically."
        )
        return runtime

    if mode == MODE_DETERMINISTIC:
        return runtime

    missing = [
        name
        for name, value in (
            ("EVALPILOT_LLM_BASE_URL", base_url),
            ("EVALPILOT_LLM_API_KEY", api_key),
            ("EVALPILOT_LLM_MODEL", model),
        )
        if not str(value or "").strip()
    ]
    if missing:
        runtime.configuration_error = (
            f"live mode requested but {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not set; "
            "running deterministically"
        )
        return runtime

    if timeout <= 0:
        runtime.configuration_error = (
            f"invalid EVALPILOT_LLM_TIMEOUT_SECONDS {timeout:g}; "
            "running deterministically"
        )
        return runtime

    from evalpilot.llm.client import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        base_url=str(base_url),
        api_key=str(api_key),
        model=str(model),
        timeout_seconds=timeout,
    )
    runtime.configured = True
    runtime.provider = provider
    runtime.model = str(model).strip()
    runtime.base_url_host = provider.host
    return runtime


__all__ = [
    "KNOWN_MODES",
    "MODE_DETERMINISTIC",
    "MODE_LIVE",
    "LLMRuntime",
    "build_runtime",
]
