"""Adapter: an :class:`LLMProvider` presented as a rubric judge.

:class:`~evalpilot.evaluation.judge.RubricJudge` takes an async callable that
returns raw model text, then validates that text into a ``JudgeOutput``. This
module supplies that callable from a provider, so the judge seam needs no new
protocol — the provider is injected where a judge callable already goes.

The JSON shape the model is asked for is the one ``JudgeOutput`` validates, and
the validation stays in :mod:`evalpilot.evaluation.judge` where it already
lives. A model that returns anything else raises ``JudgeError`` there, which
:class:`~evalpilot.orchestration_eval.service.EvaluationService` already
catches: the judge failure is counted and the deterministic score is used
alone, so a flaky model cannot zero out a run.
"""

from __future__ import annotations

import json
from typing import Any

from evalpilot.evaluation.judge import JudgeResponse
from evalpilot.llm.prompts import build_judge_prompt
from evalpilot.llm.providers import LLMProvider
from evalpilot.llm.runtime import LLMRuntime


def build_judge_callable(
    runtime: LLMRuntime,
    *,
    timeout_seconds: float | None = None,
):
    """Return an async judge callable backed by ``runtime``, or ``None``.

    ``None`` when no provider is installed — deterministic mode, or live mode
    whose configuration is incomplete. The caller then leaves the judge unset,
    which is exactly the offline behaviour, rather than installing a judge that
    would fail on every case.
    """
    provider = runtime.provider
    if provider is None:
        return None
    return ProviderJudge(provider, runtime=runtime, timeout_seconds=timeout_seconds)


class ProviderJudge:
    """Calls a provider and returns its raw content for the judge to validate."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        runtime: LLMRuntime,
        timeout_seconds: float | None = None,
    ) -> None:
        self.provider = provider
        self.timeout_seconds = (
            runtime.timeout_seconds if timeout_seconds is None else timeout_seconds
        )

    async def __call__(self, request: Any) -> JudgeResponse:
        messages = build_judge_prompt(
            question=str(getattr(request, "question", "") or ""),
            answer_text=str(getattr(request, "answer_text", "") or ""),
            rubric=str(getattr(request, "rubric", "") or ""),
            criteria=list(getattr(request, "criteria", []) or []),
            context=getattr(request, "context", None),
        )
        result = await self.provider.complete_json(
            messages,
            # The narrowest schema that is honest here: the provider must still
            # guarantee a JSON object, but the verdict's shape is validated by
            # ``RubricJudge`` into ``JudgeOutput``, which is the only place
            # that knows the score's range and the criteria's form. Asserting a
            # shape here too would duplicate that rule, not add one.
            schema={"type": "object"},
            timeout_seconds=self.timeout_seconds,
        )
        # Re-serialize so the judge's own validator sees JSON text, exactly as
        # it would from any other adapter. One validation path, not two.
        return JudgeResponse(
            text=json.dumps(result.payload),
            usage=result.usage,
            model=result.model,
            call_id=result.call_id,
            provider=result.provider,
        )


__all__ = ["ProviderJudge", "build_judge_callable"]
