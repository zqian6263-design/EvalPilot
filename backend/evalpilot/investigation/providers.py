"""Counterfactual replay seam.

A :class:`CounterfactualProvider` answers one question per regressed scenario:
*if we had undone one change in the candidate, would the scenario have passed?*
That answer is what turns "the candidate scored lower" into "this specific
change caused the drop", so it is the single most load-bearing input to the
release decision.

The protocol below is the seam. :class:`DeterministicProvider` is the fallback
that ships with the backend: it reasons from the run's own evidence and needs
neither a model nor a network, so the investigation works end to end before the
dedicated counterfactual engine is wired in. That engine is expected to
implement this protocol and be injected at
:attr:`~evalpilot.container.Container.investigation_runner`, at which point the
fallback stops being used and nothing else changes.

Be precise about what the fallback claims
-----------------------------------------
A real replay re-executes the candidate with one intervention applied and
measures the answer. The fallback cannot: it has no executor for a modified
candidate. What it does instead is *predict* the counterfactual score from the
failure the run already recorded — a scenario that lost a required clause is
predicted to regain exactly that clause when compression is disabled, and only
when the scenario's own question makes compression the plausible mechanism.

So every fallback claim is a hypothesis derived from recorded evidence, not a
measurement, and each one says so in its ``rationale``. The verdicts are still
falsifiable — the injected engine either reproduces them or does not — which is
what makes this a usable placeholder rather than a fabrication.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from evalpilot.models import CounterfactualVerdict

#: The intervention vocabulary. ``compression_disabled`` and
#: ``security_guard_enabled`` are the two the deterministic demo is required to
#: produce; the other two cover failure modes the matcher can see but the demo
#: run does not exhibit.
Intervention = Literal[
    "compression_disabled",
    "security_guard_enabled",
    "retrieval_top_k_restored",
    "clause_validator_enabled",
]

#: What the replay was aimed at, and how it went.
FailureKind = Literal["dropped_clause", "credential_disclosure", "unknown"]


@dataclass(frozen=True)
class CounterfactualRequest:
    """Everything a provider needs to replay one regressed scenario."""

    scenario_id: str
    category: str
    question: str
    original_score: float
    #: Identities needed by a measured replay provider. Defaults preserve the
    #: fallback-only tests while production always supplies them.
    investigation_id: str = ""
    run_id: str = ""
    test_case_id: str = ""
    failed_checks: tuple[str, ...] = ()
    #: Required facts the candidate answer lost, in the evaluator's words.
    missing_facts: tuple[str, ...] = ()
    #: Forbidden strings the candidate answer disclosed.
    leaked_markers: tuple[str, ...] = ()
    #: Evidence rows for the scenario, which the experiment cites.
    evidence_ids: tuple[str, ...] = ()
    failure_kind: FailureKind = "unknown"
    #: Intervention the recalled incident history points at, when there is one.
    suggested_intervention: Intervention | None = None


@dataclass(frozen=True)
class Attempt:
    """One attempted intervention and its predicted effect.

    Not a contract type: the engine stamps this into a
    :class:`~evalpilot.models.CounterfactualExperiment` with an id and a
    timestamp, so a provider never has to invent either.
    """

    scenario_id: str
    intervention: str
    original_score: float
    counterfactual_score: float
    confidence: float
    verdict: CounterfactualVerdict
    rationale: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def delta(self) -> float:
        return self.counterfactual_score - self.original_score


@runtime_checkable
class CounterfactualProvider(Protocol):
    """Replays a regressed scenario under one intervention.

    Implementations must be side-effect free: no network writes, no external
    state, and no mutation of the investigation. The engine persists whatever
    is returned and derives the release decision from it.
    """

    #: Short identifier recorded on every experiment's rationale.
    name: str

    def attempt(self, request: CounterfactualRequest) -> Sequence[Attempt]:
        """Return one attempt per intervention the provider considered."""
        ...


# --- Deterministic fallback -------------------------------------------------

#: Which algorithm the fallback assumes would run for a given intervention,
#: and how specifically it targets the observed failure. The specificity is the
#: experiment's confidence: an intervention aimed at the exact failure mode is
#: a stronger explanation than a generic guard bolted on afterwards.
_ALGORITHMS: dict[str, tuple[float, str]] = {
    "summary": (0.95, "compression path disabled for this scenario"),
    "injection": (0.95, "credential and override guards restored"),
    "credential": (0.95, "credential disclosure blocked at the answer boundary"),
    "refusal": (0.60, "refusal path restored for a non-credential prompt"),
    "validator": (0.70, "post-generation mandatory-clause validator"),
    "default": (0.70, "generic candidate-behaviour rollback for this scenario"),
}

#: Fraction of the lost score the fallback assumes each algorithm recovers.
#: A targeted algorithm is assumed to recover the scenario fully; a generic one
#: is assumed to help less, because it does not address the diagnosed mechanism.
_RECOVERY: dict[str, float] = {
    "summary": 1.0,
    "injection": 1.0,
    "credential": 1.0,
    "refusal": 0.75,
    "validator": 0.90,
    "default": 0.90,
}

_QUESTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "summary": ("summar", "compress", "brief", "shorten", "concise"),
    "credential": ("password", "credential", "secret", "token", "api key"),
    "injection": ("ignore your previous", "ignore previous", "instruction", "system prompt"),
    "refusal": ("out of scope", "competitor", "should i switch", "not covered"),
}

#: Below this recoverable gap the scenario has nothing left to explain.
MIN_RECOVERABLE_GAP = 0.05

_ROOT_CAUSE_RATIO = 0.90
_PARTIAL_RATIO = 0.40


class DeterministicProvider:
    """Offline fallback provider. Reproducible, explainable, and honest.

    See the module docstring for what it does and does not claim.
    """

    name = "deterministic-fallback"

    def attempt(self, request: CounterfactualRequest) -> Sequence[Attempt]:
        intervention = request.suggested_intervention or self._suggest(request)
        algorithm = self._algorithm(intervention, request)
        return [self._experiment(request, intervention, algorithm)]

    # -- intervention choice -------------------------------------------------

    @staticmethod
    def _suggest(request: CounterfactualRequest) -> str:
        """Pick the intervention the observed failure calls for.

        A disclosed credential is not a dropped clause and is not repaired by
        the same change, so the two are separated before anything else. That
        separation is the whole reason the demo can name two distinct root
        causes instead of one.
        """
        if request.leaked_markers or request.failure_kind == "credential_disclosure":
            return "security_guard_enabled"
        if request.missing_facts or request.failure_kind == "dropped_clause":
            return "compression_disabled"
        return "clause_validator_enabled"

    @staticmethod
    def _algorithm(intervention: str, request: CounterfactualRequest) -> str:
        """Which mechanism the fallback assumes the intervention switches off."""
        if intervention == "security_guard_enabled":
            haystack = f"{request.question} {' '.join(request.leaked_markers)}".lower()
            for keyword in _QUESTION_KEYWORDS["injection"]:
                if keyword in haystack:
                    return "injection"
            for keyword in _QUESTION_KEYWORDS["credential"]:
                if keyword in haystack:
                    return "credential"
            return "refusal"

        if intervention == "compression_disabled":
            question = request.question.lower()
            for keyword in _QUESTION_KEYWORDS["summary"]:
                if keyword in question:
                    return "summary"
            # No compression keyword in the question: the fallback cannot
            # justify claiming the compression path caused this one.
            return "default"

        if intervention == "retrieval_top_k_restored":
            return "default"

        return "validator"

    # -- scoring -------------------------------------------------------------

    def _experiment(
        self, request: CounterfactualRequest, intervention: str, algorithm: str
    ) -> Attempt:
        specificity, description = _ALGORITHMS[algorithm]
        gap = max(0.0, 1.0 - request.original_score)
        recovery = gap * _RECOVERY[algorithm]
        counterfactual_score = round(min(1.0, request.original_score + recovery), 4)

        verdict = self._verdict(gap, recovery)
        rationale = self._rationale(
            request, intervention, algorithm, description, verdict, counterfactual_score
        )
        return Attempt(
            scenario_id=request.scenario_id,
            intervention=intervention,
            original_score=request.original_score,
            counterfactual_score=counterfactual_score,
            confidence=specificity if gap > 0 else 0.0,
            verdict=verdict,
            rationale=rationale,
            evidence_ids=request.evidence_ids,
        )

    @staticmethod
    def _verdict(gap: float, recovery: float) -> CounterfactualVerdict:
        if gap < MIN_RECOVERABLE_GAP:
            return "inconclusive"
        ratio = recovery / gap
        if ratio >= _ROOT_CAUSE_RATIO:
            return "root_cause"
        if ratio >= _PARTIAL_RATIO:
            return "partial"
        return "no_effect"

    @staticmethod
    def _rationale(
        request: CounterfactualRequest,
        intervention: str,
        algorithm: str,
        description: str,
        verdict: CounterfactualVerdict,
        counterfactual_score: float,
    ) -> str:
        lost = ", ".join(request.missing_facts) or "no required fact was recorded as missing"
        leaked = ", ".join(request.leaked_markers)
        observed = (
            f"it disclosed {leaked}" if leaked else f"it lost {lost}"
        )
        if verdict == "inconclusive":
            effect = (
                "The scenario had no measurable gap left to recover, so the replay "
                "cannot attribute anything to this intervention."
            )
        elif verdict == "root_cause":
            effect = (
                f"Replaying '{request.scenario_id}' with '{intervention}' "
                f"({description}) is predicted to restore the scenario to "
                f"{counterfactual_score:.2f}, which accounts for the whole drop."
            )
        elif verdict == "partial":
            effect = (
                f"Replaying '{request.scenario_id}' with '{intervention}' "
                f"({description}) is predicted to recover only part of the drop, to "
                f"{counterfactual_score:.2f}, so this intervention is a contributing "
                "factor rather than the whole cause."
            )
        else:
            effect = (
                f"Replaying '{request.scenario_id}' with '{intervention}' "
                f"({description}) is predicted to leave the score essentially "
                f"unchanged at {counterfactual_score:.2f}, so this intervention does "
                "not explain the drop."
            )
        return (
            f"{effect} Predicted by the deterministic fallback from recorded "
            f"evidence, not measured by a replay: the candidate scored "
            f"{request.original_score:.2f} and {observed}."
        )
