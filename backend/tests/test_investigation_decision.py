"""Representation and cap tests for the release decision."""

from __future__ import annotations

from evalpilot.investigation.service import (
    MAX_BLOCKING_FINDINGS,
    ScenarioFinding,
    _blocking_findings,
)
from evalpilot.models import Finding


class _Intake:
    """The slice of RunIntake ``_blocking_findings`` reads."""

    def __init__(self, findings, scenarios) -> None:
        self.run_findings = findings
        self.scenarios = scenarios


def _scenario(scenario_id: str, baseline: str, candidate: str) -> ScenarioFinding:
    return ScenarioFinding(
        scenario_id=scenario_id,
        category="boundary",
        question="q",
        baseline_score=1.0,
        candidate_score=0.0,
        delta=-1.0,
        failed_checks=("facts",),
        missing_facts=("x",),
        leaked_markers=(),
        refusal_required=False,
        baseline_case_id=baseline,
        candidate_case_id=candidate,
        baseline_evidence=("b1",),
        candidate_evidence=("c1",),
    )


def _finding(finding_id: str, case_id: str, severity: str = "critical") -> Finding:
    return Finding(
        id=finding_id,
        run_id="run",
        test_case_id=case_id,
        severity=severity,
        title=f"Regression in '{case_id}'",
        description="d",
        confidence=1.0,
        evidence_ids=[f"ev-{finding_id}"],
        recommendation=None,
    )


def test_blocking_findings_are_the_runs_own_finding_ids() -> None:
    intake = _Intake(
        findings=[_finding("f1", "case-b"), _finding("f2", "case-a")],
        scenarios=[_scenario("s1", "case-a", "case-b")],
    )
    assert _blocking_findings(intake, disclosures=[], hard_failures=intake.scenarios) == [
        "f1",
        "f2",
    ]


def test_blocking_findings_ignore_findings_from_other_scenarios() -> None:
    intake = _Intake(
        findings=[_finding("f1", "unrelated-case"), _finding("f2", "case-b")],
        scenarios=[_scenario("s1", "case-a", "case-b")],
    )
    assert _blocking_findings(intake, disclosures=[], hard_failures=intake.scenarios) == [
        "f2"
    ]


def test_blocking_findings_ignore_advisory_severities() -> None:
    """A `low` finding cannot block a release."""
    intake = _Intake(
        findings=[_finding("f1", "case-b", severity="low")],
        scenarios=[_scenario("s1", "case-a", "case-b")],
    )
    assert _blocking_findings(intake, disclosures=[], hard_failures=intake.scenarios) == []


def test_blocking_findings_are_capped() -> None:
    scenarios = [
        _scenario(f"s{index}", f"a{index}", f"b{index}")
        for index in range(MAX_BLOCKING_FINDINGS + 3)
    ]
    findings = [_finding(f"f{index}", f"b{index}") for index in range(len(scenarios))]
    intake = _Intake(findings=findings, scenarios=scenarios)

    blocking = _blocking_findings(intake, disclosures=[], hard_failures=scenarios)
    assert len(blocking) == MAX_BLOCKING_FINDINGS
    # The cap keeps the earliest findings rather than an arbitrary subset.
    assert blocking == [f"f{index}" for index in range(MAX_BLOCKING_FINDINGS)]
