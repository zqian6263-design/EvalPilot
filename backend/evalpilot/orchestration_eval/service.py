"""Evaluation service boundary.

The runner calls exactly one method on this service: :meth:`EvaluationService.evaluate_run`.
Everything the rest of the backend needs — case verdicts, findings, metrics, and
the report summary — comes back through :class:`EvaluationOutcome`.

Replace :meth:`EvaluationService.evaluate_run` with the causal-evaluation
pipeline (matched-case comparison, repeated sampling, rubric LLM judging) and no
other module needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evalpilot.orchestration_eval.checks import CaseEvaluation, evaluate_case
from evalpilot.orchestration_eval.compare import (
    RegressionComparison,
    compare_matched_cases,
    summarize_metrics,
)
from evalpilot.orchestration_eval.findings import build_findings
from evalpilot.models import Evidence, Finding, TestCase

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts


@dataclass
class EvaluationOutcome:
    cases: list[CaseEvaluation]
    comparisons: list[RegressionComparison]
    findings: list[Finding]
    metrics: dict[str, Any]
    summary: str


@dataclass
class JudgeHook:
    """Placeholder for the rubric LLM judge.

    ``docs/SPEC.md`` places LLM judging in the evaluation stage. The MVP keeps it
    unimplemented on purpose: the demo must run with no external API. When
    ``EVALPILOT_LLM_BASE_URL`` is configured, implement :meth:`score` here and
    call it from the service below.
    """

    base_url: str | None = None
    model: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)

    def score(self, case: TestCase, evidence: list[Evidence]) -> dict[str, Any] | None:
        return None


@dataclass
class EvaluationService:
    judge: JudgeHook = field(default_factory=JudgeHook)

    def evaluate_run(
        self,
        *,
        run_id: str,
        cases: list[TestCase],
        evidence_by_case: dict[str, list[Evidence]],
    ) -> EvaluationOutcome:
        evaluations: list[CaseEvaluation] = []

        for case in cases:
            case_evidence = evidence_by_case.get(case.id, [])
            evaluation = evaluate_case(
                test_case_id=case.id,
                scenario_id=str(case.input.get("scenario_id", "")),
                version=case.version,
                category=case.category,
                difficulty=case.difficulty,
                output=case.output or {},
                expected=case.expected,
                evidence_ids=[item.id for item in case_evidence],
            )
            evaluations.append(evaluation)

            if self.judge.enabled:
                # Reserved for the rubric judge; no-op in the deterministic MVP.
                self.judge.score(case, case_evidence)

        comparisons = compare_matched_cases(evaluations)
        metrics = summarize_metrics(comparisons, evaluations)
        findings = build_findings(
            run_id=run_id,
            comparisons=comparisons,
            evaluations=evaluations,
            evidence_by_case=evidence_by_case,
        )
        metrics["findings_by_severity"] = count_by_severity(findings)
        summary = summarize(run_id, comparisons, metrics, findings)

        return EvaluationOutcome(
            cases=evaluations,
            comparisons=comparisons,
            findings=findings,
            metrics=metrics,
            summary=summary,
        )


def summarize(
    run_id: str,
    comparisons: list[RegressionComparison],
    metrics: dict[str, Any],
    findings: list[Finding],
) -> str:
    """One-paragraph, human-readable report summary."""
    regressed = [c for c in comparisons if c.changed and not c.candidate_passed]
    controls = [c for c in comparisons if not c.changed]
    severity_counts = metrics.get("findings_by_severity", {})

    def sev_block() -> str:
        if not severity_counts:
            return ""
        ordered = sorted(
            severity_counts.items(), key=lambda item: SEVERITY_ORDER.get(item[0], 9)
        )
        return "Findings: " + ", ".join(f"{count} {sev}" for sev, count in ordered) + ". "

    if not comparisons:
        if findings:
            return (
                "No comparable matched scenarios were executed, so no regression verdict is "
                "available. " + sev_block()
            )
        return "No comparable cases were executed, so no regression verdict is available."

    if regressed:
        names = ", ".join(c.scenario_id for c in regressed)
        lead = (
            f"{len(regressed)} of {len(comparisons)} matched scenarios regressed on the "
            f"candidate version ({metrics['baseline_version']} -> {metrics['candidate_version']}): "
            f"{names}. "
        )
        rest = (
            f"{len(controls)} scenario(s) were unchanged and are treated as controls, so the "
            "drop is attributable to the version change rather than to test difficulty. "
        )
    else:
        lead = (
            f"No regression detected across {len(comparisons)} matched scenarios "
            f"({metrics['baseline_version']} -> {metrics['candidate_version']}). "
        )
        rest = f"{len(controls)} scenario(s) were unchanged and serve as controls. "

    rest += sev_block()
    rest += (
        f"Baseline pass rate {metrics['baseline_pass_rate']:.0%}, candidate pass rate "
        f"{metrics['candidate_pass_rate']:.0%}."
    )
    return lead + rest

