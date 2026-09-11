"""Evaluation boundary between the runner and the evaluation engine.

The runner calls exactly one method, :meth:`EvaluationService.evaluate_run_async`,
and persists whatever :class:`EvaluationOutcome` it returns. All statistics,
severities, confidence intervals and evidence links come from
:mod:`evalpilot.evaluation` — this module maps rows in, maps verdicts out, and
computes no statistics of its own.

Case verdicts come back as :class:`CaseVerdict`, which is the comparison's own
view of the run reported in the shape the runner persists, so the runner does
not have to re-derive pass/fail from raw output.

How a scenario is scored
------------------------
Every matched scenario is scored by the engine's deterministic checks
(:mod:`evalpilot.evaluation.checks`) against the expectation mapped in
:mod:`evalpilot.engine_mapping`. A scenario's score is the fraction of the
checks it satisfies, and the comparison is the paired mean of the per-scenario
differences.

Two properties of that number decide what this run can conclude:

- It is *coverage*, not pass/fail: a scenario that loses one of two required
  facts scores 0.5 rather than 1.0.
- There is no judge in the offline demo, so this is the whole score. The engine
  would blend a judge in at equal weight, halving the deterministic signal, and
  the fixture executor does not record the question text a judge needs — so the
  demo runs judge-free on purpose and reports a configured judge as a warning
  instead of quietly blending in a non-deterministic number.

The comparison is deliberately not forced to a verdict. With 26 matched cases
this bootstrap resolves a mean drop of about 0.23 and nothing smaller, so three
localized regressions of the size the demo ships land in ``inconclusive``
instead of ``regression``. That is the honest reading of this much data, and
:func:`summarize` says so in words rather than dressing it up. The per-scenario
facts — which case failed which check, with the evidence — are reported either
way.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from evalpilot import engine_mapping
from evalpilot.clock import new_id
from evalpilot.evaluation import (
    DEFAULT_REGRESSION_THRESHOLD,
    ComparisonDirection,
    EvaluationService as EngineService,
    RubricJudge,
    Severity,
)
from evalpilot.evaluation.service import CaseEvaluation, ComparisonReport
from evalpilot.models import Evidence, Finding, TestCase

CaseVerdictStatus = Literal["pending", "running", "passed", "failed", "error"]

#: Severity of a localized drop, banded on how much of the answer was lost.
_DROP_SEVERITY_BANDS: tuple[tuple[float, Severity], ...] = (
    (0.50, Severity.CRITICAL),
    (0.20, Severity.HIGH),
)
_MOVED_SEVERITY = Severity.MEDIUM

_RECOMMENDATIONS: dict[str, str] = {
    "format": (
        "The candidate answer violates a constraint this scenario asserts — it either "
        "dropped a required fact or disclosed something it must not. Diff the retrieval "
        "and answer-template changes between the two versions for this scenario's "
        "source documents."
    ),
    "facts": (
        "Restore the dropped knowledge-base content, or update the answer template so "
        "the required operational detail survives the change."
    ),
    "refusal": (
        "Restore the out-of-scope refusal policy in the system prompt and re-run this "
        "scenario before release."
    ),
}

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    """Finding counts keyed by severity."""
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


@dataclass(frozen=True)
class CaseVerdict:
    """One scenario's verdict, as the matched comparison saw it.

    Status is per version, not per scenario: the contract stores one status on
    each ``TestCase`` row and there is a row per version. Applying a single
    scenario-level status to both rows marks the baseline row ``failed`` for
    every scenario the candidate regressed on, which makes the run look like it
    regressed against itself.
    """

    scenario_id: str
    baseline_status: CaseVerdictStatus
    candidate_status: CaseVerdictStatus
    baseline_score: float | None
    candidate_score: float | None
    delta: float | None
    failed_checks: tuple[str, ...]
    rationale: str

    def status_for(self, version: str) -> CaseVerdictStatus:
        """The status to persist on the row for a ``TestCase.version`` literal.

        Keyed on the contract's ``baseline | candidate`` literal, not on the
        run's version *labels* (``v1.0-baseline`` and friends): those are
        free-form display strings, and matching a case row against them silently
        fails for every run that names its versions anything else.
        """
        return self.baseline_status if version == "baseline" else self.candidate_status


@dataclass
class EvaluationOutcome:
    cases: list[CaseVerdict]
    findings: list[Finding]
    metrics: dict[str, Any]
    summary: str


@dataclass
class EvaluationService:
    """Runs the engine over a finished run's cases and evidence.

    Args:
        seed: Bootstrap seed, so a run's verdict is reproducible.
        threshold: Regression threshold forwarded to the comparison.
        bootstrap_resamples: Bootstrap resamples forwarded to the comparison.
        judge: Optional rubric judge. ``None`` keeps the run offline.
    """

    seed: int = 0
    threshold: float = DEFAULT_REGRESSION_THRESHOLD
    bootstrap_resamples: int = 2000
    judge: RubricJudge | None = None

    async def evaluate_run_async(
        self,
        *,
        run_id: str,
        cases: list[TestCase],
        evidence_by_case: dict[str, list[Evidence]],
        baseline_version: str = "baseline",
        candidate_version: str = "candidate",
    ) -> EvaluationOutcome:
        """Score and compare every matched scenario in a finished run.

        ``evidence_by_case`` is keyed by case id exactly as the runner collects
        it; the flat evidence list is rebuilt from it so both keyings agree.
        """
        engine = EngineService(
            judge=self.judge,
            threshold=self.threshold,
            bootstrap_resamples=self.bootstrap_resamples,
            seed=self.seed,
        )

        evidence = [item for items in evidence_by_case.values() for item in items]
        observations = [
            engine_mapping.to_observation(case, evidence) for case in cases
        ]

        expectations: dict[str, Any] = {}
        attributed: dict[str, list[str]] = {}
        case_rows: dict[str, str] = {}
        for case in cases:
            scenario = engine_mapping.scenario_id(case)
            expectations.setdefault(
                scenario, engine_mapping.to_expected_behavior(case.expected)
            )
            attributed.setdefault(scenario, []).extend(
                engine_mapping.evidence_for(case, evidence)
            )
            # Findings cite a specific case row. Prefer the candidate's, since
            # that is the row whose output the finding is about. Keyed on the
            # ``TestCase.version`` literal, not the run's version label.
            if scenario not in case_rows or case.version == "candidate":
                case_rows[scenario] = case.id

        report = await engine.compare_async(
            observations=observations,
            expectations=expectations,
            evidence_ids_by_case=attributed,
            run_id=run_id,
        )

        warnings = list(report.warnings)
        if self.judge is not None:
            warnings.append(
                "An LLM judge is configured, but the offline fixture executor does not "
                "record the question text a judge needs, so only deterministic checks "
                "were scored and no judge contributes to these numbers."
            )

        verdicts = _case_verdicts(cases, report)
        findings = _findings(run_id, report, attributed, case_rows)
        metrics = _metrics(
            report,
            verdicts,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
        )
        metrics["findings_by_severity"] = count_by_severity(findings)
        if warnings:
            metrics["evaluation_warnings"] = list(warnings)

        return EvaluationOutcome(
            cases=verdicts,
            findings=findings,
            metrics=metrics,
            summary=summarize(
                report,
                verdicts,
                findings,
                metrics,
                baseline_version=baseline_version,
                candidate_version=candidate_version,
            ),
        )

    def evaluate_run(
        self,
        *,
        run_id: str,
        cases: list[TestCase],
        evidence_by_case: dict[str, list[Evidence]],
        baseline_version: str = "baseline",
        candidate_version: str = "candidate",
    ) -> EvaluationOutcome:
        """Synchronous wrapper for callers with no event loop (CLI, tests)."""
        return asyncio.run(
            self.evaluate_run_async(
                run_id=run_id,
                cases=cases,
                evidence_by_case=evidence_by_case,
                baseline_version=baseline_version,
                candidate_version=candidate_version,
            )
        )


# --------------------------------------------------------------------------
# Row-shape adapters
# --------------------------------------------------------------------------


def _case_verdicts(cases: list[TestCase], report: ComparisonReport) -> list[CaseVerdict]:
    """One verdict per scenario, in the order the planner produced them."""
    by_case = {item.case_id: item for item in report.case_evaluations}
    verdicts: list[CaseVerdict] = []
    seen: set[str] = set()

    for case in cases:
        scenario = engine_mapping.scenario_id(case)
        if scenario in seen:
            continue
        seen.add(scenario)

        evaluation = by_case.get(scenario)
        if evaluation is None:
            continue

        baseline = evaluation.deterministic_scores_by_version.get("baseline")
        candidate = evaluation.deterministic_scores_by_version.get("candidate")
        delta = (
            candidate - baseline
            if baseline is not None and candidate is not None
            else None
        )
        failed = _failed_check_labels(evaluation)

        verdicts.append(
            CaseVerdict(
                scenario_id=scenario,
                baseline_status=_status(baseline),
                candidate_status=_status(candidate),
                baseline_score=baseline,
                candidate_score=candidate,
                delta=delta,
                failed_checks=failed,
                rationale=_scenario_rationale(evaluation, baseline, candidate, delta),
            )
        )
    return verdicts


def _status(score: float | None) -> CaseVerdictStatus:
    """A scenario that did not score at all is an error, not a failure."""
    if score is None:
        return "error"
    return "passed" if score >= 1.0 else "failed"


def _scenario_rationale(
    evaluation: CaseEvaluation,
    baseline: float | None,
    candidate: float | None,
    delta: float | None,
) -> str:
    if baseline is None or candidate is None:
        return "Scenario was not scored on both versions, so no comparison is available."
    if delta is None or delta == 0:
        return (
            f"Baseline {baseline:.2f} and candidate {candidate:.2f} score identically: "
            "this scenario is a control and did not move."
        )
    return f"Candidate scored {candidate:.2f} against a baseline of {baseline:.2f}."


def _failed_check_labels(evaluation: CaseEvaluation) -> tuple[str, ...]:
    """Names of the checks that failed on either version, in suite order."""
    return tuple(kind.value for kind in evaluation.failing_checks)


def _failure_detail(evaluation: CaseEvaluation) -> str:
    """The evaluator's own words for why the scenario lost points."""
    return " ".join(gap.rationale for gap in evaluation.missing_evidence)


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


def _drop_severity(delta: float) -> Severity:
    for band, severity in _DROP_SEVERITY_BANDS:
        if abs(delta) >= band:
            return severity
    return _MOVED_SEVERITY


def _findings(
    run_id: str,
    report: ComparisonReport,
    attributed: dict[str, list[str]],
    case_rows: dict[str, str],
) -> list[Finding]:
    """Evidence-linked findings for regressed and persistently failing scenarios.

    Controls — scenarios that scored the same on both versions — produce
    nothing. A scenario the candidate fell back on produces a regression
    finding. A scenario that still fails on the candidate but did not move (or
    moved up) is reported too, at ``low``: it is not this change's fault, but it
    is a real defect and the reason the case cannot discriminate between
    versions. A scenario with no matched score, or no evidence to cite, is
    skipped: a finding that cannot link evidence is not a finding.
    """
    findings: list[Finding] = []

    for evaluation in report.case_evaluations:
        baseline = evaluation.deterministic_scores_by_version.get("baseline")
        candidate = evaluation.deterministic_scores_by_version.get("candidate")
        evidence_ids = attributed.get(evaluation.case_id, [])

        if baseline is None or candidate is None or not evidence_ids:
            continue

        delta = candidate - baseline
        if delta >= 0 and candidate >= 1.0:
            continue

        failed = _failed_check_labels(evaluation)

        if delta < 0:
            severity = _drop_severity(delta)
            title = f"Regression in '{evaluation.case_id}'"
            detail = _failure_detail(evaluation)
            description = (
                f"The candidate scored {candidate:.2f} on '{evaluation.case_id}' "
                f"where the baseline scored {baseline:.2f} (delta {delta:+.2f}). "
                f"Failing check(s): {', '.join(failed) if failed else 'none recorded'}. "
                f"{detail} "
                f"{_scenario_rationale(evaluation, baseline, candidate, delta)}"
            ).strip()
            # A deterministic check failure is reproducible, so confidence is
            # certainty about the fact. It is lower when the baseline was not
            # clean, because then the case was not a clean control.
            confidence = 1.0 if baseline >= 1.0 else 0.8
        else:
            severity = Severity.LOW
            title = f"Scenario '{evaluation.case_id}' fails on both versions"
            description = (
                f"'{evaluation.case_id}' scores {candidate:.2f} on the candidate and "
                f"{baseline:.2f} on the baseline, so the failure is not attributable to "
                "this change. It still cannot discriminate between versions until it "
                "passes somewhere. "
                f"Failing check(s): {', '.join(failed) if failed else 'none recorded'}."
            )
            confidence = 1.0

        findings.append(
            Finding(
                id=new_id(),
                run_id=run_id,
                test_case_id=case_rows.get(evaluation.case_id),
                severity=severity.value,
                title=title,
                description=description,
                confidence=confidence,
                evidence_ids=list(evidence_ids),
                recommendation=_recommendation(delta, failed),
            )
        )

    return findings


def _recommendation(delta: float, failed: tuple[str, ...]) -> str:
    if delta >= 0:
        return (
            "Fix the underlying defect on both versions before using this scenario as a "
            "regression control; until it passes somewhere it contributes no signal."
        )
    return _RECOMMENDATIONS.get(
        failed[0] if failed else "facts", _RECOMMENDATIONS["facts"]
    )


# --------------------------------------------------------------------------
# Metrics and summary
# --------------------------------------------------------------------------


def _metrics(
    report: ComparisonReport,
    verdicts: list[CaseVerdict],
    *,
    baseline_version: str,
    candidate_version: str,
) -> dict[str, Any]:
    """Report metrics: the keys the orchestration layer already exposed, plus
    the paired statistics the engine computes.

    The first block keeps its names and meaning so the CLI, the event stream and
    anything else reading ``regression_detected`` or ``regressed_scenarios``
    keeps working. ``baseline_pass_rate``/``candidate_pass_rate`` are strict
    case pass rates: the fraction of matched scenarios for which every check
    passed. ``baseline_score``/``candidate_score`` retain the mean check
    coverage, which is the continuous quantity behind the paired comparison.
    Keeping those concepts separate prevents the UI from claiming that a
    partially-correct answer was a fully passing test case.
    """
    comparison = report.comparison
    baseline_scores = [
        v.baseline_score for v in verdicts if v.baseline_score is not None
    ]
    candidate_scores = [
        v.candidate_score for v in verdicts if v.candidate_score is not None
    ]
    baseline_pass_rate = (
        sum(1 for score in baseline_scores if score >= 1.0) / len(baseline_scores)
        if baseline_scores
        else 0.0
    )
    candidate_pass_rate = (
        sum(1 for score in candidate_scores if score >= 1.0) / len(candidate_scores)
        if candidate_scores
        else 0.0
    )

    moved = [v for v in verdicts if v.delta is not None and v.delta < 0]
    failing = [v for v in verdicts if v.candidate_score is not None and v.candidate_score < 1.0]

    return {
        "baseline_version": baseline_version,
        "candidate_version": candidate_version,
        "matched_scenarios": comparison.sample_size,
        "scenario_count": len(verdicts),
        "baseline_cases": len(baseline_scores),
        "candidate_cases": len(candidate_scores),
        "baseline_pass_rate": round(baseline_pass_rate, 4),
        "candidate_pass_rate": round(candidate_pass_rate, 4),
        "baseline_score": round(_mean(baseline_scores), 4),
        "candidate_score": round(_mean(candidate_scores), 4),
        # Both scenario-level keys keep the meaning they had before this
        # integration: the scenarios the candidate scored below the baseline.
        # They are the per-case facts, and they are reported whatever the
        # aggregate verdict says. ``regression_confirmed`` below is the separate
        # question of whether the mean difference cleared the threshold.
        #
        # Sorted, not in row order: the report is persisted and compared between
        # runs, and a list whose order tracks how the cases happened to be
        # listed makes two identical runs look different.
        "regressed_scenarios": sorted(v.scenario_id for v in moved),
        "regression_detected": bool(moved),
        "failing_scenarios": sorted(v.scenario_id for v in failing),
        "control_scenarios": sorted(
            v.scenario_id for v in verdicts if v.delta == 0 and v.candidate_score == 1.0
        ),
        "fixed_scenarios": sorted(
            v.scenario_id for v in verdicts if v.delta is not None and v.delta > 0
        ),
        "baseline_mean": comparison.baseline_mean,
        "candidate_mean": comparison.candidate_mean,
        "mean_difference": comparison.mean_difference,
        "std_difference": comparison.std_difference,
        "ci_lower": comparison.ci_lower,
        "ci_upper": comparison.ci_upper,
        "effect_size": comparison.effect_size,
        "confidence": comparison.confidence,
        "direction": comparison.direction.value,
        "is_significant": comparison.is_significant,
        "regression_threshold": comparison.threshold,
        "trial_count": comparison.trial_count,
        "regression_confirmed": comparison.direction is ComparisonDirection.REGRESSION,
    }


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def summarize(
    report: ComparisonReport,
    verdicts: list[CaseVerdict],
    findings: list[Finding],
    metrics: dict[str, Any],
    *,
    baseline_version: str = "baseline",
    candidate_version: str = "candidate",
) -> str:
    """A report summary built only from numbers the run actually produced.

    Every clause is conditional on a metric that moved. Prose that asserts a
    conclusion the statistics do not support is worse than no prose, because the
    summary is the part a reader trusts without re-deriving the numbers behind
    it.
    """
    comparison = report.comparison
    direction = comparison.direction
    matched = comparison.sample_size

    if matched == 0:
        return (
            "No scenarios were matched across both versions, so no regression "
            "verdict is available."
        )

    moved = [v for v in verdicts if v.delta is not None and v.delta < 0]
    controls = [v for v in verdicts if v.delta == 0 and v.candidate_score == 1.0]
    failed_both = [
        v
        for v in verdicts
        if v.delta is not None
        and v.delta >= 0
        and v.candidate_score is not None
        and v.candidate_score < 1.0
    ]

    parts = [
        f"Compared {matched} matched scenario(s) between {baseline_version} and "
        f"{candidate_version}. "
    ]

    if direction is ComparisonDirection.REGRESSION:
        parts.append(
            f"The candidate regressed: the mean score fell "
            f"{abs(comparison.mean_difference):.3f} (95% CI {comparison.ci_lower:.3f} "
            f"to {comparison.ci_upper:.3f}), entirely below the "
            f"-{comparison.threshold:.3f} threshold. "
        )
    elif direction is ComparisonDirection.IMPROVEMENT:
        parts.append(
            f"The candidate improved: the mean score rose "
            f"{comparison.mean_difference:.3f} (95% CI {comparison.ci_lower:.3f} to "
            f"{comparison.ci_upper:.3f}), entirely above the "
            f"+{comparison.threshold:.3f} threshold. "
        )
    else:
        parts.append(
            f"The aggregate comparison is inconclusive: the mean score changed by "
            f"{comparison.mean_difference:+.3f} (95% CI {comparison.ci_lower:.3f} to "
            f"{comparison.ci_upper:.3f}), which does not clear the "
            f"±{comparison.threshold:.3f} threshold at {comparison.confidence:.0%} "
            "confidence. "
        )

    if moved:
        named = ", ".join(
            f"{v.scenario_id} ({v.baseline_score:.2f}->{v.candidate_score:.2f})"
            for v in moved
        )
        parts.append(
            f"{len(moved)} scenario(s) regressed against their own baseline: {named}. "
        )

    if controls:
        parts.append(
            f"{len(controls)} control scenario(s) scored identically on both versions, "
            "which is what makes any difference attributable to the version change "
            "rather than to a harder test set. "
        )

    if direction is ComparisonDirection.INCONCLUSIVE and moved:
        parts.append(
            "Treat those as localized failures with evidence, not as a resolved "
            "regression: a change this size across this many matched cases is too "
            "small for the interval to separate from noise. "
        )

    if failed_both:
        parts.append(
            f"{len(failed_both)} scenario(s) fail on both versions and cannot "
            "discriminate between them. "
        )

    severity_counts = metrics.get("findings_by_severity", {})
    if severity_counts:
        ordered = sorted(
            severity_counts.items(), key=lambda item: _SEVERITY_ORDER.get(item[0], 9)
        )
        parts.append(
            "Findings: "
            + ", ".join(f"{count} {severity}" for severity, count in ordered)
            + ". "
        )

    return "".join(parts)
