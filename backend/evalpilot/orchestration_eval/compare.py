"""Matched-case comparison across the baseline and candidate versions.

Every scenario is executed once per version, so the two versions face an
identical test set. A difference between the two runs of the same scenario is
therefore attributable to the version change rather than to test difficulty —
the causal claim the product is built around.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evalpilot.orchestration_eval.checks import CaseEvaluation
from evalpilot.models import CaseVersion

BASELINE_VERSION: CaseVersion = "baseline"
CANDIDATE_VERSION: CaseVersion = "candidate"


@dataclass
class RegressionComparison:
    scenario_id: str
    category: str
    difficulty: float
    baseline: CaseEvaluation | None
    candidate: CaseEvaluation | None

    @property
    def changed(self) -> bool:
        """True when the two versions scored differently on this scenario."""
        if self.baseline is None or self.candidate is None:
            return False
        return self.baseline.passed != self.candidate.passed

    @property
    def candidate_passed(self) -> bool:
        return bool(self.candidate and self.candidate.passed)

    def failed_checks(self) -> list:
        if self.candidate is None:
            return []
        return self.candidate.failed_checks


def _index(
    evaluations: list[CaseEvaluation], version: str
) -> dict[str, CaseEvaluation]:
    return {
        evaluation.scenario_id: evaluation
        for evaluation in evaluations
        if evaluation.version == version
    }


def compare_matched_cases(
    evaluations: list[CaseEvaluation],
) -> list[RegressionComparison]:
    baseline = _index(evaluations, BASELINE_VERSION)
    candidate = _index(evaluations, CANDIDATE_VERSION)

    comparisons: list[RegressionComparison] = []
    for scenario_id in sorted(set(baseline) | set(candidate)):
        left = baseline.get(scenario_id)
        right = candidate.get(scenario_id)
        reference = left or right
        assert reference is not None
        comparisons.append(
            RegressionComparison(
                scenario_id=scenario_id,
                category=reference.category,
                difficulty=reference.difficulty,
                baseline=left,
                candidate=right,
            )
        )
    return comparisons


def _pass_rate(evaluations: list[CaseEvaluation]) -> float:
    if not evaluations:
        return 0.0
    return sum(1 for evaluation in evaluations if evaluation.passed) / len(evaluations)


def _weighted_pass_rate(evaluations: list[CaseEvaluation]) -> float:
    """Difficulty-weighted pass rate in ``[0, 1]``.

    Harder cases carry more weight, so a version that only handles easy
    questions cannot look strong. This is the summary score shown in the UI.
    """
    if not evaluations:
        return 0.0
    total_weight = sum(evaluation.difficulty for evaluation in evaluations)
    if total_weight <= 0:
        return _pass_rate(evaluations)
    passed_weight = sum(
        evaluation.difficulty for evaluation in evaluations if evaluation.passed
    )
    return passed_weight / total_weight


def summarize_metrics(
    comparisons: list[RegressionComparison],
    evaluations: list[CaseEvaluation],
    baseline_version: str = BASELINE_VERSION,
    candidate_version: str = CANDIDATE_VERSION,
) -> dict[str, Any]:
    baseline = [e for e in evaluations if e.version == baseline_version]
    candidate = [e for e in evaluations if e.version == candidate_version]

    regressed = [c for c in comparisons if c.changed and not c.candidate_passed]
    fixed = [c for c in comparisons if c.changed and c.candidate_passed]
    stable = [c for c in comparisons if not c.changed]

    by_category: dict[str, dict[str, int]] = {}
    for comparison in comparisons:
        bucket = by_category.setdefault(
            comparison.category, {"total": 0, "regressed": 0}
        )
        bucket["total"] += 1
        if comparison in regressed:
            bucket["regressed"] += 1

    return {
        "baseline_version": baseline_version,
        "candidate_version": candidate_version,
        "matched_scenarios": len(comparisons),
        "baseline_cases": len(baseline),
        "candidate_cases": len(candidate),
        "baseline_pass_rate": round(_pass_rate(baseline), 4),
        "candidate_pass_rate": round(_pass_rate(candidate), 4),
        "baseline_score": round(_weighted_pass_rate(baseline), 4),
        "candidate_score": round(_weighted_pass_rate(candidate), 4),
        "regressed_scenarios": [c.scenario_id for c in regressed],
        "fixed_scenarios": [c.scenario_id for c in fixed],
        "control_scenarios": [c.scenario_id for c in stable],
        "regression_detected": bool(regressed),
        "by_category": by_category,
    }

