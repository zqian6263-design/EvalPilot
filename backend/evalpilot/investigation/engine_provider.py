"""Measured counterfactual provider for the investigation service.

The investigation layer talks to :class:`~evalpilot.investigation.providers.CounterfactualProvider`.
This adapter connects that seam to the real replay engine: it reads the
candidate case from the repository, replays it under the suggested intervention,
and maps the measured result back to the provider's ``Attempt`` shape.

The deterministic fallback remains available and is used only when the real
engine cannot replay the request (for example, malformed identity or a missing
case). That keeps the API robust without silently turning a failed replay into a
fabricated root-cause claim.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from evalpilot.counterfactual import (
    CounterfactualEngine,
    CounterfactualTarget,
    Intervention,
)
from evalpilot.executor import ExecutionResult
from evalpilot.models import Evidence
from evalpilot.repository import Repository

from .providers import Attempt, CounterfactualRequest, DeterministicProvider


@dataclass(frozen=True)
class RepositoryReadingSource:
    """Thin adapter from ``Repository`` to the replay engine's read/write seam."""

    repo: Repository

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        return self.repo.get_evidence(evidence_id)

    def add_evidence(self, evidence: Evidence) -> Evidence:
        return self.repo.add_evidence(evidence)

    def write_artifact(self, run_id: str, filename: str, content: str) -> str:
        return self.repo.db.write_artifact(run_id, filename, content)


class EngineCounterfactualProvider:
    """Provider backed by measured counterfactual replay."""

    name = "counterfactual-engine"

    def __init__(
        self,
        *,
        repo: Repository,
        engine: CounterfactualEngine | None = None,
        fallback: DeterministicProvider | None = None,
        executor: Callable[..., ExecutionResult] | None = None,
    ) -> None:
        self.repo = repo
        self.engine = engine or CounterfactualEngine(
            source=RepositoryReadingSource(repo),
            executor=executor,
        )
        self.fallback = fallback or DeterministicProvider()

    def attempt(self, request: CounterfactualRequest):
        if not request.run_id or not request.test_case_id:
            return self.fallback.attempt(request)

        try:
            case = self.repo.get_test_case(request.test_case_id)
            run = self.repo.get_run(request.run_id)
        except Exception:
            return self.fallback.attempt(request)

        intervention = request.suggested_intervention or (
            Intervention.SECURITY_GUARD_ENABLED
            if request.failure_kind == "credential_disclosure"
            else Intervention.COMPRESSION_DISABLED
        )

        try:
            result = self.engine.replay(
                CounterfactualTarget(
                    scenario_id=request.scenario_id,
                    run_id=request.run_id,
                    test_case_id=request.test_case_id,
                    intervention=intervention,
                    expected=case.expected,
                    question=request.question,
                    version_label=run.candidate_version,
                    original_evidence_ids=list(request.evidence_ids),
                    original_score=request.original_score,
                    failing_checks=list(request.failed_checks),
                ),
                investigation_id=request.investigation_id or None,
            )
        except Exception:
            return self.fallback.attempt(request)

        original = result.original_score if result.original_score is not None else request.original_score
        counterfactual = (
            result.counterfactual_score
            if result.counterfactual_score is not None
            else original
        )
        return (
            Attempt(
                scenario_id=request.scenario_id,
                intervention=result.intervention,
                original_score=original,
                counterfactual_score=counterfactual,
                confidence=result.confidence,
                verdict=result.verdict.value,
                rationale=result.rationale,
                evidence_ids=tuple(result.evidence_ids),
            ),
        )


__all__ = ["EngineCounterfactualProvider", "RepositoryReadingSource"]
