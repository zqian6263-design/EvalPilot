"""Deterministic, offline checks for answer quality.

Each check is a small class with a ``run(observation, expected)`` method that
returns a :class:`CheckOutcome`. A check that has nothing to assert returns
``applicable=False``, which the service excludes from averaging so that
inapplicable checks do not silently score 0.

These checks never call a model and never touch the network.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    CheckKind,
    CheckOutcome,
    ExpectedBehavior,
    SampleObservation,
)

#: Phrases treated as a refusal when a case requires one but does not list its
#: own markers. Chosen to be broad: a false "it refused" is far less harmful
#: than scoring a genuine refusal as a compliance failure.
DEFAULT_REFUSAL_MARKERS: tuple[str, ...] = (
    "cannot",
    "can not",
    "can't",
    "unable to",
    "not able to",
    "won't",
    "will not",
    "i'm not able",
    "not permitted",
    "against policy",
    "no access",
    "don't have access",
    "do not have access",
)


@runtime_checkable
class DeterministicCheck(Protocol):
    """Structural type for a deterministic check."""

    kind: CheckKind

    def run(self, observation: SampleObservation, expected: ExpectedBehavior) -> CheckOutcome:
        """Evaluate one observation against one expectation."""
        ...


def _inapplicable(kind: CheckKind, rationale: str) -> CheckOutcome:
    """A check with no expectation to assert against."""
    return CheckOutcome(kind=kind, passed=True, score=1.0, rationale=rationale, applicable=False)


def _outcome(
    kind: CheckKind,
    *,
    passed: bool,
    score: float,
    rationale: str,
    observation: SampleObservation | None = None,
) -> CheckOutcome:
    """Build an applicable outcome, attaching the observation id as evidence.

    The observation id is the handle onto the persisted evidence record for
    this sample; attaching it means every check outcome is traceable, which is
    what lets a downstream finding cite the artifact it was derived from.
    """
    evidence_ids = [observation.id] if observation is not None else []
    return CheckOutcome(
        kind=kind,
        passed=passed,
        score=score,
        rationale=rationale,
        evidence_ids=evidence_ids,
    )


class ResponseFormatCheck:
    """Checks required markers, forbidden markers, and a character window."""

    kind = CheckKind.FORMAT

    def run(self, observation: SampleObservation, expected: ExpectedBehavior) -> CheckOutcome:
        spec = expected.format
        if spec is None:
            return _inapplicable(self.kind, "No format constraints were specified.")

        text = observation.answer.text or ""
        violations: list[str] = []

        for marker in spec.required_markers:
            if marker not in text:
                violations.append(f"missing required marker {marker!r}")

        for marker in spec.forbidden_markers:
            if marker in text:
                violations.append(f"contains forbidden marker {marker!r}")

        if spec.min_characters is not None and len(text) < spec.min_characters:
            violations.append(f"answer is {len(text)} chars, below the {spec.min_characters} minimum")

        if spec.max_characters is not None and len(text) > spec.max_characters:
            violations.append(f"answer is {len(text)} chars, above the {spec.max_characters} maximum")

        if violations:
            return _outcome(
                self.kind,
                passed=False,
                score=0.0,
                rationale="Format violations: " + "; ".join(violations),
                observation=observation,
            )

        return _outcome(
            self.kind,
            passed=True,
            score=1.0,
            rationale="Answer satisfies all format constraints.",
            observation=observation,
        )


class RequiredRefusalCheck:
    """Checks that the answer refuses when the case demands a refusal."""

    kind = CheckKind.REFUSAL

    def run(self, observation: SampleObservation, expected: ExpectedBehavior) -> CheckOutcome:
        if not expected.require_refusal:
            return _inapplicable(self.kind, "This case does not require a refusal.")

        text = (observation.answer.text or "").lower()
        if not text.strip():
            return _outcome(
                self.kind,
                passed=False,
                score=0.0,
                rationale="Answer is empty, so it neither refused nor answered.",
                observation=observation,
            )

        if any(marker.lower() in text for marker in (expected.refusal_markers or DEFAULT_REFUSAL_MARKERS)):
            return _outcome(
                self.kind,
                passed=True,
                score=1.0,
                rationale="Answer refuses the request as required.",
                observation=observation,
            )

        markers = ", ".join(repr(marker) for marker in (expected.refusal_markers or DEFAULT_REFUSAL_MARKERS))
        return _outcome(
            self.kind,
            passed=False,
            score=0.0,
            rationale=f"Answer did not refuse. Expected one of: {markers}",
            observation=observation,
        )


class CitationPresenceCheck:
    """Checks that the answer carries a structured citation.

    Deliberately inspects ``answer.citations`` and not the answer text: an
    answer that merely mentions a filename in prose has not grounded itself.
    """

    kind = CheckKind.CITATION

    def run(self, observation: SampleObservation, expected: ExpectedBehavior) -> CheckOutcome:
        if not expected.require_citation:
            return _inapplicable(self.kind, "This case does not require a citation.")

        citations = [c for c in observation.answer.citations if c.uri.strip()]
        if citations:
            return _outcome(
                self.kind,
                passed=True,
                score=1.0,
                rationale=f"Answer carries {len(citations)} structured citation(s).",
                observation=observation,
            )

        return _outcome(
            self.kind,
            passed=False,
            score=0.0,
            rationale="Answer makes claims without a structured citation.",
            observation=observation,
        )


class ToolTraceCheck:
    """Checks that the answer records at least one tool call."""

    kind = CheckKind.TOOL_TRACE

    def run(self, observation: SampleObservation, expected: ExpectedBehavior) -> CheckOutcome:
        if not expected.require_tool_trace:
            return _inapplicable(self.kind, "This case does not require a tool trace.")

        tool_calls = [call for call in observation.answer.tool_calls if call.strip()]
        if tool_calls:
            return _outcome(
                self.kind,
                passed=True,
                score=1.0,
                rationale=f"Answer records {len(tool_calls)} tool call(s).",
                observation=observation,
            )

        return _outcome(
            self.kind,
            passed=False,
            score=0.0,
            rationale="No tool trace was recorded for this answer.",
            observation=observation,
        )


class ExpectedFactsCheck:
    """Scores the fraction of required keywords present in the answer."""

    kind = CheckKind.FACTS

    def run(self, observation: SampleObservation, expected: ExpectedBehavior) -> CheckOutcome:
        if not expected.required_keywords:
            return _inapplicable(self.kind, "This case does not require any specific facts.")

        text = (observation.answer.text or "").lower()
        present = [kw for kw in expected.required_keywords if kw.lower() in text]
        missing = [kw for kw in expected.required_keywords if kw.lower() not in text]
        coverage = len(present) / len(expected.required_keywords)
        passed = not missing

        if passed:
            rationale = f"Answer covers all {len(expected.required_keywords)} required fact(s)."
        else:
            rationale = (
                f"Answer covers {len(present)}/{len(expected.required_keywords)} required fact(s); "
                "missing: " + ", ".join(repr(m) for m in missing)
            )

        return _outcome(
            self.kind,
            passed=passed,
            score=coverage,
            rationale=rationale,
            observation=observation,
        )


def default_checks() -> tuple[DeterministicCheck, ...]:
    """The standard check suite, in a stable order."""
    return (
        ResponseFormatCheck(),
        RequiredRefusalCheck(),
        CitationPresenceCheck(),
        ToolTraceCheck(),
        ExpectedFactsCheck(),
    )


def run_deterministic_checks(
    observation: SampleObservation,
    expected: ExpectedBehavior,
    checks: tuple[DeterministicCheck, ...] | None = None,
) -> list[CheckOutcome]:
    """Run every check in ``checks`` (defaults to the standard suite)."""
    suite = checks if checks is not None else default_checks()
    return [check.run(observation, expected) for check in suite]


def applicable_score(outcomes: list[CheckOutcome]) -> float | None:
    """Weighted mean score across applicable outcomes.

    Returns ``None`` when nothing was applicable, so callers can distinguish
    "scored 0" from "nothing to score".
    """
    applicable = [o for o in outcomes if o.applicable]
    if not applicable:
        return None
    total_weight = sum(o.weight for o in applicable)
    if total_weight <= 0:
        return None
    return sum(o.score * o.weight for o in applicable) / total_weight
