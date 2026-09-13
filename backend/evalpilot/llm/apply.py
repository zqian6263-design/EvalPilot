"""Turning a validated proposal into something safe to persist.

The model's JSON is treated as untrusted input even after it satisfies the
schema. Schema validation proves the *shape* is right; it proves nothing about
whether a scenario id exists, whether an evidence id is real, or whether the
model quietly decided to disagree with the measured verdict.

So everything a model proposes passes through here first:

- scenario ids are intersected with the run's own scenario ids;
- evidence ids are intersected with the ids the caller actually offered;
- a proposed verdict or risk level that disagrees with the measured one is
  discarded, not negotiated;
- free text is length-capped and stripped.

A hypothesis left with no surviving scenario id is dropped: it would be a claim
the run's evidence cannot locate, and the investigation's evidence rule
forbids persisting one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from evalpilot.llm.prompts import (
    MAX_RATIONALE_CHARS,
    MAX_RECOMMENDATIONS,
)

#: Cap on a proposal's free text, matching the schema's own bound.
MAX_CLAIM_CHARS = 400
MAX_MECHANISM_CHARS = 400
MAX_DISCARDED_CHARS = 200


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _known_ids(values: Any, allowed: set[str]) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    kept: list[str] = []
    for value in values:
        candidate = str(value)
        if candidate in allowed and candidate not in kept:
            kept.append(candidate)
    return kept


def sanitize_hypotheses(
    payload: Mapping[str, Any],
    *,
    known_scenarios: set[str],
    known_kinds: Sequence[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return ``(usable hypotheses, discarded reasons)``.

    Usable means: the kind is one the investigation understands, the claim and
    mechanism are non-empty, and at least one cited scenario id exists in the
    run. Anything else is discarded with a reason, which is recorded so a
    reader can see the model proposed something and it was not used.
    """
    raw = payload.get("hypotheses")
    hypotheses: list[dict[str, Any]] = []
    discarded: list[str] = [
        _text(reason, MAX_DISCARDED_CHARS)
        for reason in (payload.get("discarded") or [])
        if str(reason or "").strip()
    ]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return hypotheses, discarded

    allowed_kinds = set(known_kinds)
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        kind = _text(item.get("kind"), 64)
        claim = _text(item.get("claim"), MAX_CLAIM_CHARS)
        mechanism = _text(item.get("mechanism"), MAX_MECHANISM_CHARS)
        scenarios = _known_ids(item.get("scenario_ids"), known_scenarios)

        if kind not in allowed_kinds:
            discarded.append(f"unknown hypothesis kind {kind!r}")
            continue
        if not claim or not mechanism:
            discarded.append(f"hypothesis {kind!r} had no claim or mechanism")
            continue
        if not scenarios:
            discarded.append(
                f"hypothesis {kind!r} cited no scenario that exists in this run"
            )
            continue

        confidence = item.get("confidence")
        hypotheses.append(
            {
                "kind": kind,
                "claim": claim,
                "mechanism": mechanism,
                "scenarios": scenarios,
                "confidence": (
                    round(float(confidence), 4)
                    if isinstance(confidence, (int, float))
                    and not isinstance(confidence, bool)
                    else None
                ),
            }
        )
    return hypotheses, discarded


def sanitize_replay_interventions(
    payload: Mapping[str, Any],
    *,
    known_scenarios: set[str],
    allowed_interventions: Sequence[str],
) -> tuple[list[dict[str, str]], list[str]]:
    """Return the replay actions the execution layer is allowed to run.

    A replay choice is a proposed experiment, not a finding. It still has to
    name a regressed scenario that exists in this run and an intervention that
    the counterfactual engine can actually execute; invalid choices are
    rejected and recorded rather than guessed into a valid-looking plan.
    """
    raw = payload.get("replay_interventions")
    accepted: list[dict[str, str]] = []
    rejected: list[str] = []
    if raw is None:
        return accepted, rejected
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return accepted, ["replay_interventions was not an array"]

    allowed = set(allowed_interventions)
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            rejected.append("replay intervention was not an object")
            continue
        scenario_id = _text(item.get("scenario_id"), 128)
        intervention = _text(item.get("intervention"), 64)
        rationale = _text(item.get("rationale"), 300)
        if scenario_id not in known_scenarios:
            rejected.append(
                f"replay intervention cited unknown scenario {scenario_id!r}"
            )
            continue
        if scenario_id in seen:
            rejected.append(f"duplicate replay intervention for {scenario_id!r}")
            continue
        if intervention not in allowed:
            rejected.append(
                f"replay intervention {intervention!r} is not executable"
            )
            continue
        if not rationale:
            rejected.append(f"replay intervention for {scenario_id!r} had no rationale")
            continue
        seen.add(scenario_id)
        accepted.append(
            {
                "scenario_id": scenario_id,
                "intervention": intervention,
                "rationale": rationale,
            }
        )
    return accepted, rejected


def sanitize_rationale(
    payload: Mapping[str, Any],
    *,
    allowed_evidence: Sequence[str],
    measured_verdict: str,
    measured_risk: str,
) -> dict[str, Any]:
    """Return the usable parts of a rationale, with disagreements recorded.

    ``verdict_disagreement`` is set when the model echoed a verdict or risk
    level other than the measured one. The text is still usable as commentary
    — it is an explanation of a decision it misread — but the disagreement is
    surfaced rather than hidden, and the measured values are what the caller
    keeps.
    """
    allowed = set(allowed_evidence)
    rationale = _text(payload.get("rationale"), MAX_RATIONALE_CHARS)
    recommendations = [
        _text(item, MAX_CLAIM_CHARS)
        for item in (payload.get("recommendations") or [])
        if str(item or "").strip()
    ][:MAX_RECOMMENDATIONS]

    proposed_verdict = _text(payload.get("verdict"), 32) or None
    proposed_risk = _text(payload.get("risk_level"), 32) or None

    disagreement: list[str] = []
    if proposed_verdict is not None and proposed_verdict != measured_verdict:
        disagreement.append(
            f"model proposed verdict {proposed_verdict!r}, measured was {measured_verdict!r}"
        )
    if proposed_risk is not None and proposed_risk != measured_risk:
        disagreement.append(
            f"model proposed risk {proposed_risk!r}, measured was {measured_risk!r}"
        )

    return {
        "rationale": rationale,
        "evidence_ids": _known_ids(payload.get("evidence_ids"), allowed),
        "recommendations": recommendations,
        "proposed_verdict": proposed_verdict,
        "proposed_risk_level": proposed_risk,
        "verdict_disagreement": disagreement,
    }


__all__ = [
    "sanitize_hypotheses",
    "sanitize_rationale",
    "sanitize_replay_interventions",
]
