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
        "候选答案违反该场景声明的约束：要么丢失了必答事实，要么披露了禁止输出的内容。"
        "请对比两个版本在该场景来源文档上的检索与答案模板变更。"
    ),
    "facts": (
        "恢复被删除的知识库内容，或调整答案模板，确保变更后仍保留关键业务信息。"
    ),
    "refusal": (
        "在系统提示词中恢复越界拒答策略，并在发布前重新运行该场景。"
    ),
}

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_SEVERITY_LABELS = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "low": "低",
    "info": "提示",
}


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
        return "该场景未在两个版本上同时评分，无法比较。"
    if delta is None or delta == 0:
        return (
            f"基线与候选版本得分均为 {baseline:.2f}/{candidate:.2f}："
            "该场景是对照组，没有发生移动。"
        )
    return f"候选版本得分 {candidate:.2f}，基线得分 {baseline:.2f}。"


def _failed_check_labels(evaluation: CaseEvaluation) -> tuple[str, ...]:
    """Names of the checks that failed on either version, in suite order."""
    return tuple(kind.value for kind in evaluation.failing_checks)


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
            title = f"场景“{evaluation.case_id}”出现回归"
            description = (
                f"候选版本在“{evaluation.case_id}”上得分 {candidate:.2f}，"
                f"基线得分 {baseline:.2f}（差值 {delta:+.2f}）。"
                f"未通过的检查：{', '.join(failed) if failed else '未记录'}。"
                f"{_scenario_rationale(evaluation, baseline, candidate, delta)}"
            ).strip()
            # A deterministic check failure is reproducible, so confidence is
            # certainty about the fact. It is lower when the baseline was not
            # clean, because then the case was not a clean control.
            confidence = 1.0 if baseline >= 1.0 else 0.8
        else:
            severity = Severity.LOW
            title = f"场景“{evaluation.case_id}”在两个版本上均未通过"
            description = (
                f"“{evaluation.case_id}”在候选版本得分 {candidate:.2f}，"
                f"基线得分 {baseline:.2f}，因此该失败不能归因于本次变更。"
                "在任一版本通过前，它都无法区分版本差异。"
                f"未通过的检查：{', '.join(failed) if failed else '未记录'}。"
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
        return "先修复两个版本共同存在的缺陷，再将该场景用作回归对照；在任一版本通过前，它不提供回归信号。"
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
        return "两个版本之间没有匹配到任何场景，因此无法给出回归结论。"

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
        f"已在 {baseline_version} 与 {candidate_version} 之间比较 {matched} 个匹配场景。"
    ]

    if direction is ComparisonDirection.REGRESSION:
        parts.append(
            f"候选版本出现回归：平均分下降 {abs(comparison.mean_difference):.3f}"
            f"（95% 置信区间 {comparison.ci_lower:.3f} 至 {comparison.ci_upper:.3f}），"
            f"整个区间均低于 -{comparison.threshold:.3f} 的回归阈值。"
        )
    elif direction is ComparisonDirection.IMPROVEMENT:
        parts.append(
            f"候选版本有所改进：平均分上升 {comparison.mean_difference:.3f}"
            f"（95% 置信区间 {comparison.ci_lower:.3f} 至 {comparison.ci_upper:.3f}），"
            f"整个区间均高于 +{comparison.threshold:.3f} 的改进阈值。"
        )
    else:
        parts.append(
            f"总体比较尚不确定：平均分变化 {comparison.mean_difference:+.3f}"
            f"（95% 置信区间 {comparison.ci_lower:.3f} 至 {comparison.ci_upper:.3f}），"
            f"在 {comparison.confidence:.0%} 置信度下未跨越 ±{comparison.threshold:.3f} 阈值。"
        )

    if moved:
        named = ", ".join(
            f"{v.scenario_id} ({v.baseline_score:.2f}->{v.candidate_score:.2f})"
            for v in moved
        )
        parts.append(
            f"{len(moved)} 个场景相对自身基线发生回归：{named}。"
        )

    if controls:
        parts.append(
            f"{len(controls)} 个对照场景在两个版本上得分完全一致，"
            "因此任何差异都可归因于版本变更，而不是更换了更难的测试集。"
        )

    if direction is ComparisonDirection.INCONCLUSIVE and moved:
        parts.append(
            "应将这些场景视为有证据支持的局部故障，而不是已经确认的总体回归："
            "在当前离线样本量下，这一变化幅度仍不足以与噪声区分。"
        )

    if failed_both:
        parts.append(
            f"{len(failed_both)} 个场景在两个版本上均未通过，无法用于区分版本差异。"
        )

    severity_counts = metrics.get("findings_by_severity", {})
    if severity_counts:
        ordered = sorted(
            severity_counts.items(), key=lambda item: _SEVERITY_ORDER.get(item[0], 9)
        )
        parts.append(
            "发现："
            + "、".join(
                f"{_SEVERITY_LABELS.get(severity, severity)} {count}"
                for severity, count in ordered
            )
            + "。"
        )

    return "".join(parts)
