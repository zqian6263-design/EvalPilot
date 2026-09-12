"""Autonomous release investigation.

Public surface:

- :class:`~evalpilot.investigation.service.InvestigationService` — drives a
  completed run through hypotheses, incident recall, probes, counterfactual
  replay, a release decision, and an exportable evidence report.
- :class:`~evalpilot.investigation.providers.CounterfactualProvider` — the seam
  the dedicated counterfactual engine implements, with
  :class:`~evalpilot.investigation.providers.DeterministicProvider` as the
  offline fallback the backend ships with.
- :func:`recommend_actions` — the release-gate recommendation for a decision.
"""

from __future__ import annotations

from evalpilot.investigation.engine_provider import EngineCounterfactualProvider
from evalpilot.investigation.live import LiveLLMAugmenter
from evalpilot.investigation.providers import (
    CounterfactualProvider,
    CounterfactualRequest,
    DeterministicProvider,
)
from evalpilot.investigation.service import (
    InvestigationError,
    InvestigationOutcome,
    InvestigationService,
    RunIntake,
    ScenarioFinding,
    render_markdown,
)

__all__ = [
    "CounterfactualProvider",
    "CounterfactualRequest",
    "DeterministicProvider",
    "EngineCounterfactualProvider",
    "InvestigationError",
    "InvestigationOutcome",
    "InvestigationService",
    "LiveLLMAugmenter",
    "RunIntake",
    "ScenarioFinding",
    "recommend_actions",
    "render_markdown",
]


def recommend_actions(verdict: str) -> list[str]:
    """The recommended-action set for a decision verdict.

    Kept next to the service so a caller reading a stored decision can recover
    the recommendation without re-running the analysis that produced it.
    """
    from evalpilot.investigation.service import (
        ALLOW_RECOMMENDATION,
        DISCLOSURE_RECOMMENDATION,
        REGRESSION_RECOMMENDATION,
    )

    if verdict == "block":
        return [REGRESSION_RECOMMENDATION, DISCLOSURE_RECOMMENDATION]
    if verdict == "review":
        return [REGRESSION_RECOMMENDATION]
    return [ALLOW_RECOMMENDATION]
