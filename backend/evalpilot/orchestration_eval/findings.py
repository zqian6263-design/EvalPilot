"""Turn case verdicts into findings that always carry evidence links.

Contract requirement (``CLAUDE.md`` #2): every evaluation finding must link to
the exact input, output, tool trace, and evaluator rationale. Findings here are
constructed from the candidates' own evidence rows, so the link is structural
rather than editorial.
"""

from __future__ import annotations

from evalpilot.clock import new_id
from evalpilot.orchestration_eval.checks import CaseEvaluation
from evalpilot.orchestration_eval.compare import RegressionComparison
from evalpilot.models import Evidence, Finding

CHECK_SEVERITIES: tuple[str, ...] = (
    "must_avoid",
    "refusal",
    "must_include",
    "citation_grounded",
    "answer_present",
)

CHECK_SEVERITY: dict[str, str] = {
    "must_avoid": "critical",
    "refusal": "critical",
    "citation_grounded": "medium",
    "must_include": "high",
    "answer_present": "high",
}

_RECOMMENDATIONS: dict[str, str] = {
    "must_avoid": (
        "Add a disclosure guard to the response pipeline and block any answer that "
        "echoes credentials or internal configuration. Re-run this scenario before release."
    ),
    "refusal": (
        "Restore the out-of-scope refusal policy in the system prompt and add a "
        "deterministic regression case that asserts the assistant declines."
    ),
    "citation_grounded": (
        "Verify retrieval still returns the expected documents and that the answer "
        "template surfaces their citation IDs."
    ),
    "must_include": (
        "Restore the dropped knowledge-base content or update the answer template so "
        "required operational detail is preserved."
    ),
    "answer_present": (
        "Check the response pipeline for an early return; the assistant produced no answer."
    ),
}


def _rationale(evaluation: CaseEvaluation) -> str:
    failed = ", ".join(check.name for check in evaluation.failed_checks)
    return (
        f"Deterministic checks run on candidate case {evaluation.test_case_id}; "
        f"failing checks: {failed}."
    )


def _finding(
    *,
    run_id: str,
    title: str,
    description: str,
    severity: str,
    confidence: float,
    evidence_ids: list[str],
    test_case_id: str | None,
    recommendation: str | None,
) -> Finding:
    return Finding(
        id=new_id(),
        run_id=run_id,
        test_case_id=test_case_id,
        severity=severity,  # type: ignore[arg-type]
        title=title,
        description=description,
        confidence=confidence,
        evidence_ids=evidence_ids,
        recommendation=recommendation,
    )


def build_findings(
    *,
    run_id: str,
    comparisons: list[RegressionComparison],
    evaluations: list[CaseEvaluation],
    evidence_by_case: dict[str, list[Evidence]],
) -> list[Finding]:
    findings: list[Finding] = []

    for comparison in comparisons:
        candidate = comparison.candidate
        if candidate is None or not comparison.changed or candidate.passed:
            continue

        failed_checks = candidate.failed_checks
        if not failed_checks:
            continue

        # Highest-priority failing check drives severity and recommendation.
        primary = min(
            failed_checks,
            key=lambda check: CHECK_SEVERITIES.index(check.name)
            if check.name in CHECK_SEVERITIES
            else len(CHECK_SEVERITIES),
        )
        severity = CHECK_SEVERITY.get(primary.name, "medium")

        evidence_ids = [item.id for item in evidence_by_case.get(candidate.test_case_id, [])]
        detail = "; ".join(f"{check.name}: {check.detail}" for check in failed_checks)

        findings.append(
            _finding(
                run_id=run_id,
                title=f"Regression in '{comparison.scenario_id}' ({comparison.category})",
                description=(
                    f"The baseline version passed scenario '{comparison.scenario_id}' but the "
                    f"candidate version failed it at difficulty {comparison.difficulty:.2f}. "
                    f"Failure detail — {detail} Rationale: {_rationale(candidate)} "
                    "Matched-case control: the same scenario was executed once per version, "
                    "so the difference is attributable to the version change rather than to "
                    "test difficulty."
                ),
                severity=severity,
                confidence=round(min(0.99, 0.75 + comparison.difficulty * 0.2), 2),
                evidence_ids=evidence_ids,
                test_case_id=candidate.test_case_id,
                recommendation=_RECOMMENDATIONS.get(
                    primary.name, "Investigate the failing check and re-run the scenario."
                ),
            )
        )

    # Surface baseline failures too: they are not regressions, but they are real
    # defects in the current release and should not be silently dropped.
    for evaluation in evaluations:
        if evaluation.version != "baseline" or evaluation.passed:
            continue
        evidence_ids = [item.id for item in evidence_by_case.get(evaluation.test_case_id, [])]
        detail = "; ".join(f"{c.name}: {c.detail}" for c in evaluation.failed_checks)
        findings.append(
            _finding(
                run_id=run_id,
                title=f"Baseline failure in '{evaluation.scenario_id}' ({evaluation.category})",
                description=(
                    f"Scenario '{evaluation.scenario_id}' fails on the baseline version as "
                    f"well, so it is not attributable to this change. Failure detail — {detail} "
                    f"Rationale: {_rationale(evaluation)}"
                ),
                severity="low",
                confidence=0.6,
                evidence_ids=evidence_ids,
                test_case_id=evaluation.test_case_id,
                recommendation=(
                    "Track as an existing defect; fix it before using this scenario as a "
                    "regression control."
                ),
            )
        )

    return findings

