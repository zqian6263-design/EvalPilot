"""LLM-judge protocol.

The judge is injected as an async callable, so this module depends on no LLM
SDK and no network stack. The callable receives the full
:class:`~evalpilot.evaluation.models.JudgeRequest` and returns the model's raw
text. That text is then validated into a :class:`JudgeOutput`; anything that is
not strict, in-range JSON raises :class:`JudgeError`.

Keeping validation here (rather than in the callable) means a judge cannot
silently return a plausible-looking but malformed verdict.
"""

from __future__ import annotations

import json
import math
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from .models import JudgeOutput, JudgeRequest

#: Default rubric used when a caller does not supply one.
DEFAULT_RUBRIC = (
    "Score the answer from 0.0 to 1.0 on how well it serves the question. "
    "Reward factual grounding in the provided context, directness, and a "
    "refusal when the request cannot be answered from the context. Penalise "
    "unsupported claims, contradictions, and unsafe compliance."
)

#: An async callable that turns a judge request into raw model text.
JudgeCallable = Callable[[JudgeRequest], Awaitable[str]]

_FENCE = "```"


class JudgeError(RuntimeError):
    """Raised when the judge call fails or returns an unusable verdict."""


def _strip_code_fence(raw: str) -> str:
    """Remove a single wrapping markdown fence, if present.

    Models frequently wrap JSON in ```json ... ```. That is a formatting
    quirk, not a schema violation, so it is tolerated here and nowhere else.
    """
    text = raw.strip()
    if not text.startswith(_FENCE):
        return text

    lines = text.splitlines()
    lines = lines[1:]  # drop the opening fence (and any language tag)
    if lines and lines[-1].strip() == _FENCE:
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_judge_output(raw: str) -> JudgeOutput:
    """Validate a raw judge response into a :class:`JudgeOutput`.

    Raises:
        JudgeError: if the text is not valid JSON, is not a JSON object, or
            does not satisfy the verdict schema.
    """
    candidate = _strip_code_fence(raw)

    try:
        payload: Any = json.loads(
            candidate,
            parse_constant=lambda name: _reject_json_constant(name),
        )
    except JudgeError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise JudgeError(f"Judge output is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise JudgeError(
            f"Judge output failed schema validation: expected a JSON object, got {type(payload).__name__}"
        )

    # ``confidence`` is optional in the contract; fill the neutral default so a
    # terse but otherwise valid verdict is not rejected.
    payload.setdefault("confidence", 0.5)

    try:
        return JudgeOutput.model_validate(payload)
    except ValidationError as exc:
        raise JudgeError(f"Judge output failed schema validation: {exc}") from exc


def _reject_json_constant(name: str) -> float:
    """Reject NaN/Infinity, which ``json.loads`` otherwise accepts."""
    raise JudgeError(f"Judge output is not valid JSON: {name} is not a JSON value")


class RubricJudge:
    """Wraps an injected async callable with strict output validation."""

    def __init__(
        self,
        judge_fn: JudgeCallable,
        *,
        rubric: str = DEFAULT_RUBRIC,
        criteria: list[str] | None = None,
    ) -> None:
        if not callable(judge_fn):
            raise TypeError("judge_fn must be an async callable")
        self.judge_fn = judge_fn
        self.rubric = rubric
        self.criteria = list(criteria or [])

    async def judge(self, request: JudgeRequest) -> JudgeOutput:
        """Score one answer, returning a validated verdict.

        Raises:
            JudgeError: if the callable raises, or its output is unusable.
        """
        try:
            raw = await self.judge_fn(request)
        except Exception as exc:  # noqa: BLE001 - the callable is untrusted
            raise JudgeError(f"judge call failed: {exc}") from exc

        if not isinstance(raw, str):
            raise JudgeError(
                f"Judge output failed schema validation: expected str, got {type(raw).__name__}"
            )

        return parse_judge_output(raw)


def build_judge_prompt(request: JudgeRequest) -> str:
    """Render a judge request into a plain-text prompt.

    Provided so that adapters onto concrete providers share one prompt shape.
    This module never calls it itself.
    """
    criteria = ", ".join(request.criteria) if request.criteria else "(none specified)"
    parts = [
        "You are a strict evaluation judge for a knowledge-base QA assistant.",
        f"Rubric:\n{request.rubric}",
        f"Criteria to score: {criteria}",
        f"Question:\n{request.question}",
        f"Answer under review:\n{request.answer_text}",
    ]
    if request.context:
        parts.append(f"Retrieved context:\n{request.context}")
    parts.append(
        "Reply with JSON only, shaped exactly as: "
        '{"score": <0..1>, "confidence": <0..1>, "rationale": "<text>", '
        '"criteria": [{"name": "<criterion>", "score": <0..1>, "rationale": "<text>"}]}'
    )
    return "\n\n".join(parts)


def is_finite(value: float) -> bool:
    """Guard used by callers that aggregate judge scores."""
    return math.isfinite(value)
