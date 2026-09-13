"""Integration tests for the runner -> engine evaluation boundary.

These exercise the seam rather than the engine (``test_evaluation.py`` already
covers the statistics). What matters here is that backend rows arrive at the
engine intact, that the numbers the report exposes are the engine's numbers, and
that the demo's conclusion is one its data can actually support.

The through-the-API tests drive the real runner over the deterministic demo, so
they are offline and reproducible like every other test in this suite.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from evalpilot import engine_mapping
from evalpilot.demo import (
    DEMO_BASELINE_VERSION,
    DEMO_CANDIDATE_VERSION,
    DEMO_CASE_COUNT,
    ensure_demo_project,
    scripted_regressions,
)
from evalpilot.evaluation import EvaluationService as EngineService
from evalpilot.fixtures import KNOWLEDGE_BASE, SUPPORT_SCENARIOS, scenario_by_id
from evalpilot.models import Evidence, Finding, Report, TestCase
from evalpilot.orchestration_eval.service import EvaluationService

from .conftest import start_and_wait

# Collected as a test class by pytest because of its name; it is a data model.
TestCase.__test__ = False


def _demo_report(client: TestClient) -> tuple[str, dict]:
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    start_and_wait(client, run.id)
    return run.id, client.get(f"/api/runs/{run.id}/report").json()


# --------------------------------------------------------------------------
# The mapping layer
# --------------------------------------------------------------------------


def test_scenario_id_is_the_matched_key_not_the_case_row_id() -> None:
    """The engine matches on scenario, because a row id is unique per version.

    Keying the engine on ``TestCase.id`` would produce two disjoint case sets
    and a silent "nothing to compare", so this is pinned directly.
    """
    cases = [
        TestCase(
            id=f"{version}-row",
            run_id="run",
            title=f"{scenario} [{version}]",
            category="normal",
            input={"scenario_id": scenario, "version": version},
            expected={},
            difficulty=0.2,
            status="passed",
            version=version,
        )
        for scenario in ("refund-window", "shipping-sla")
        for version in ("baseline", "candidate")
    ]

    keys = {engine_mapping.scenario_id(case) for case in cases}
    assert keys == {"refund-window", "shipping-sla"}
    assert len(keys) == 2, "the same scenario must not appear as two cases"


def test_expected_behavior_maps_facts_and_forbidden_content() -> None:
    expected = engine_mapping.to_expected_behavior(
        {
            "must_include": ["30 days"],
            "must_avoid": ["admin password"],
            "expects_refusal": False,
            "expected_doc_ids": ["kb-refund-policy"],
        }
    )

    assert expected.required_keywords == ["30 days"]
    assert expected.format is not None
    assert expected.format.forbidden_markers == ["admin password"]
    assert expected.require_refusal is False


def test_refusal_scenarios_are_not_held_to_the_answer_length_or_marker_rules() -> None:
    """A refusal is not supposed to mention what it refuses.

    ``out-of-scope-competitor`` forbids the word "competitor" and expects a
    refusal. Applying that ban to the refusal text would make the correct answer
    fail, so the format rule is dropped for refusal cases.
    """
    expected = engine_mapping.to_expected_behavior(
        {"must_avoid": ["competitor"], "expects_refusal": True, "expected_doc_ids": []}
    )

    assert expected.require_refusal is True
    assert expected.format is None


def test_observation_cites_the_persisted_evidence_id() -> None:
    """The engine derives finding evidence from the observation id.

    Backend findings must cite ids that exist in the run's evidence table, so
    the observation id has to be the persisted evidence id, not a fresh uuid.
    """
    case = TestCase(
        id="row-1",
        run_id="run",
        title="t",
        category="normal",
        input={"scenario_id": "s"},
        expected={},
        difficulty=0.2,
        status="passed",
        version="baseline",
        output={"answer": "a 30 days answer", "citations": ["kb://x"]},
    )
    evidence = [
        _evidence("ev-2", "row-1"),
        _evidence("ev-1", "row-1"),
        _evidence("ev-other", "row-other"),
    ]

    observation = engine_mapping.to_observation(case, evidence)

    assert observation.id == "ev-2", "first persisted evidence id for the case"
    assert observation.case_id == "s"
    assert observation.answer.citations[0].uri == "kb://x"
    assert observation.error is None


def test_observation_without_evidence_is_rejected() -> None:
    """A case with no evidence cannot produce a contract-valid finding."""
    case = TestCase(
        id="row-1",
        run_id="run",
        title="t",
        category="normal",
        input={"scenario_id": "s"},
        expected={},
        difficulty=0.2,
        status="error",
        version="baseline",
        output=None,
    )

    with pytest.raises(ValueError, match="no evidence rows"):
        engine_mapping.to_observation(case, [])


def _evidence(evidence_id: str, case_id: str) -> Evidence:
    return Evidence(
        id=evidence_id,
        run_id="run",
        test_case_id=case_id,
        kind="text",
        uri=None,
        payload={},
        created_at="2026-09-11T00:00:00Z",
    )


# --------------------------------------------------------------------------
# Fixture integrity
# --------------------------------------------------------------------------


def test_every_required_fact_is_producible_by_the_executor() -> None:
    """A ``must_include`` the fixture executor cannot emit is an unanswerable case.

    The mock assistant answers with a sentence copied verbatim from a retrieved
    document, so a required phrase that is not a substring of one of those
    sentences fails on the baseline through no fault of the candidate — and then
    reads as a defect in whichever version happens to be scored.
    """
    unanswerable: list[tuple[str, str]] = []
    for scenario in SUPPORT_SCENARIOS:
        candidates = " ".join(scenario.answer_candidates()).lower()
        for phrase in scenario.must_include:
            if phrase.lower() not in candidates:
                unanswerable.append((scenario.scenario_id, phrase))

    assert not unanswerable, f"fixtures ask for content the executor cannot emit: {unanswerable}"


def test_expected_documents_exist_in_the_knowledge_base() -> None:
    known = {doc.doc_id for doc in KNOWLEDGE_BASE}
    missing = [
        (scenario.scenario_id, doc_id)
        for scenario in SUPPORT_SCENARIOS
        for doc_id in scenario.expected_doc_ids
        if doc_id not in known
    ]
    assert not missing, f"scenarios cite documents that do not exist: {missing}"


def test_scripted_defects_are_declared_on_cases_that_can_express_them() -> None:
    """A scripted defect must be an edit the executor can actually apply.

    ``candidate_drops`` removes sentences from the baseline answer, so the
    phrase has to be in one of them. ``candidate_leaks`` is appended rather than
    dropped, and it models a defect that is *absent* from the baseline by
    construction — the baseline refuses and therefore never contains the leaked
    credential. So the two lists are checked against different things.
    """
    ungrounded_drops: list[tuple[str, str]] = []
    for scenario_id in scripted_regressions():
        scenario = scenario_by_id(scenario_id)
        baseline_answer = " ".join(scenario.answer_candidates()).lower()
        for phrase in scenario.candidate_drops:
            if phrase.lower() not in baseline_answer:
                ungrounded_drops.append((scenario_id, phrase))

    assert not ungrounded_drops, (
        f"candidate_drops phrases are not in the baseline answer, so dropping them "
        f"would be a no-op: {ungrounded_drops}"
    )

    # A leak on a scenario that expects an answer would be present on both
    # versions (the baseline is composed from the same document), which is not a
    # regression. Leaks only make sense on refusal scenarios.
    misplaced_leaks = [
        scenario.scenario_id
        for scenario_id in scripted_regressions()
        for scenario in [scenario_by_id(scenario_id)]
        if scenario.candidate_leaks and not scenario.expects_refusal
    ]
    assert not misplaced_leaks, (
        f"candidate_leaks on a non-refusal scenario is not a regression: {misplaced_leaks}"
    )


# --------------------------------------------------------------------------
# Metric exposure
# --------------------------------------------------------------------------


def test_report_exposes_the_paired_statistics(client: TestClient) -> None:
    _, report = _demo_report(client)
    metrics = report["metrics"]

    required = {
        "matched_scenarios",
        "baseline_mean",
        "candidate_mean",
        "mean_difference",
        "std_difference",
        "ci_lower",
        "ci_upper",
        "effect_size",
        "confidence",
        "direction",
        "is_significant",
        "regression_threshold",
        "trial_count",
        "regression_detected",
        "regression_confirmed",
        "regressed_scenarios",
        "control_scenarios",
        "minimum_detectable_effect",
        "required_matched_cases",
        "observed_power",
        "sample_size_adequate",
    }
    assert required <= set(metrics), f"missing metrics: {required - set(metrics)}"

    assert metrics["direction"] in {"improvement", "regression", "inconclusive"}
    assert 0.0 <= metrics["confidence"] <= 1.0
    assert metrics["ci_lower"] <= metrics["mean_difference"] <= metrics["ci_upper"]
    assert metrics["matched_scenarios"] == DEMO_CASE_COUNT
    assert metrics["baseline_mean"] == pytest.approx(1.0)
    assert metrics["candidate_mean"] < metrics["baseline_mean"]
    assert metrics["minimum_detectable_effect"] >= 0
    assert metrics["required_matched_cases"] >= 2
    assert 0.0 <= metrics["observed_power"] <= 1.0


def test_metric_values_are_the_engine_values_not_a_re_derivation(client: TestClient) -> None:
    """The report's numbers must come from the engine's comparison.

    Re-deriving the mean difference in the report layer is how a report ends up
    disagreeing with the verdict it is supposed to explain, so the report's
    aggregate fields are checked against the engine's own result for the same
    observations.
    """
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    start_and_wait(client, run.id)

    report = client.get(f"/api/runs/{run.id}/report").json()
    detail = client.get(f"/api/runs/{run.id}").json()

    cases = [TestCase.model_validate(item) for item in detail["test_cases"]]
    evidence_by_case: dict[str, list[Evidence]] = {}
    for item in detail["evidence"]:
        evidence_by_case.setdefault(item["test_case_id"], []).append(
            Evidence.model_validate(item)
        )

    outcome = asyncio.run(
        EvaluationService(seed=0, bootstrap_resamples=2000).evaluate_run_async(
            run_id=run.id, cases=cases, evidence_by_case=evidence_by_case
        )
    )

    for key in (
        "mean_difference",
        "ci_lower",
        "ci_upper",
        "effect_size",
        "confidence",
        "baseline_mean",
        "candidate_mean",
        "matched_scenarios",
    ):
        assert report["metrics"][key] == pytest.approx(outcome.metrics[key]), key
    assert report["metrics"]["direction"] == outcome.metrics["direction"]


# --------------------------------------------------------------------------
# Deliberate regressions, with evidence
# --------------------------------------------------------------------------


def test_deliberate_regressions_are_detected_per_case_with_evidence(
    client: TestClient,
) -> None:
    run_id, report = _demo_report(client)
    detail = client.get(f"/api/runs/{run_id}").json()

    expected = set(scripted_regressions())
    assert set(report["metrics"]["regressed_scenarios"]) == expected

    known_evidence = {item["id"] for item in detail["evidence"]}
    known_cases = {case["id"] for case in detail["test_cases"]}

    findings_by_scenario = {
        finding["title"]: finding for finding in report["findings"]
    }
    assert len(findings_by_scenario) == len(expected)

    for scenario_id in expected:
        title = f"场景“{scenario_id}”出现回归"
        assert title in findings_by_scenario, f"no finding for {scenario_id}"

        finding = Finding.model_validate(findings_by_scenario[title])
        assert finding.evidence_ids, "every finding must cite evidence"
        assert set(finding.evidence_ids) <= known_evidence
        assert finding.test_case_id in known_cases
        assert finding.severity in {"high", "critical"}
        assert finding.recommendation
        # The description names the scenario and the score it moved between.
        assert scenario_id in finding.description
        assert "差值" in finding.description


def test_findings_point_at_the_candidate_row(client: TestClient) -> None:
    """A finding cites the candidate's row, not whichever row came first.

    The run's version labels (``v1.0-baseline``) are free-form; the row literal
    is ``baseline | candidate``. Selecting the row by label silently picks the
    baseline row for every finding.
    """
    run_id, report = _demo_report(client)
    detail = client.get(f"/api/runs/{run_id}").json()

    candidate_rows = {
        case["id"]
        for case in detail["test_cases"]
        if case["version"] == "candidate"
    }
    regression_findings = [
        finding
        for finding in report["findings"]
        if "出现回归" in finding["title"]
    ]
    assert regression_findings
    for finding in regression_findings:
        assert finding["test_case_id"] in candidate_rows


def test_findings_report_the_failed_check_that_caused_the_regression(
    client: TestClient,
) -> None:
    _, report = _demo_report(client)

    by_scenario = {
        finding["title"]: Finding.model_validate(finding)
        for finding in report["findings"]
    }
    # The prompt-injection scenario discloses a forbidden credential, which the
    # format check catches; the other two drop a required fact.
    injection = by_scenario["场景“prompt-injection-password”出现回归"]
    assert injection.severity == "critical"
    assert "format" in injection.description

    escalation = by_scenario["场景“escalation-path”出现回归"]
    assert "facts" in escalation.description


# --------------------------------------------------------------------------
# False-regression resistance
# --------------------------------------------------------------------------


def test_control_scenarios_do_not_move(client: TestClient) -> None:
    """Identical answers must score identically, or the controls are not controls.

    A control that drifts makes every downstream number unattributable: the
    comparison would be measuring the fixture, not the version change.
    """
    run_id, report = _demo_report(client)
    detail = client.get(f"/api/runs/{run_id}").json()

    by_scenario: dict[str, dict[str, dict]] = {}
    for case in detail["test_cases"]:
        by_scenario.setdefault(case["input"]["scenario_id"], {})[case["version"]] = case

    moved = report["metrics"]["regressed_scenarios"]
    controls = report["metrics"]["control_scenarios"]

    assert len(controls) == DEMO_CASE_COUNT - len(moved)
    assert set(controls) | set(moved) == set(by_scenario)

    for scenario_id in controls:
        pair = by_scenario[scenario_id]
        assert pair["baseline"]["output"]["answer"] == pair["candidate"]["output"]["answer"], (
            f"control {scenario_id} produced different answers, so it is not a control"
        )
        assert pair["baseline"]["status"] == pair["candidate"]["status"] == "passed"


def test_controls_do_not_produce_findings(client: TestClient) -> None:
    _, report = _demo_report(client)
    regressed = set(report["metrics"]["regressed_scenarios"])

    for finding in report["findings"]:
        target = Finding.model_validate(finding).test_case_id
        assert target is not None
        # A finding is only ever raised for a scenario that moved.
        title = finding["title"]
        if "出现回归" in title:
            scenario = title.split("“", 1)[1].split("”", 1)[0]
            assert scenario in regressed


def test_a_harder_test_set_is_not_read_as_a_regression(client: TestClient) -> None:
    """The product claim, tested end to end.

    Each scenario is paired with a *different, harder* scenario's expectation
    than the answer it was actually produced for. Both arms are re-scored under
    that same harder yardstick, so the difficulty is no longer a property of one
    version: it cancels out of the difference, and a matched comparison reports
    no change at all.

    That cancellation is the whole design. An unpaired comparison of the two
    arms' means would be reading the same numbers with the pairing thrown away,
    and the drop it reports is test difficulty rather than a version change.
    """
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    start_and_wait(client, run.id)

    detail = client.get(f"/api/runs/{run.id}").json()
    cases = [TestCase.model_validate(item) for item in detail["test_cases"]]

    # Hand each scenario the expectation of a scenario several difficulty tiers
    # harder, wrapping around. The answers themselves are untouched.
    hardest_first = sorted(SUPPORT_SCENARIOS, key=lambda s: s.difficulty, reverse=True)
    order = [scenario.scenario_id for scenario in hardest_first]
    stride = max(1, len(order) // 3)
    harder_by_scenario = {
        scenario_id: order[(index + stride) % len(order)]
        for index, scenario_id in enumerate(order)
    }

    mismatched = [
        case.model_copy(
            update={
                "expected": next(
                    item.expected
                    for item in cases
                    if str(item.input["scenario_id"])
                    == harder_by_scenario[str(case.input["scenario_id"])]
                )
            }
        )
        for case in cases
    ]

    outcome = asyncio.run(
        EvaluationService(seed=0, bootstrap_resamples=2000).evaluate_run_async(
            run_id=run.id,
            cases=mismatched,
            evidence_by_case=_group_evidence(
                [
                    Evidence.model_validate(item)
                    for item in detail["evidence"]
                ]
            ),
            baseline_version=DEMO_BASELINE_VERSION,
            candidate_version=DEMO_CANDIDATE_VERSION,
        )
    )

    # The mismatched yardstick is genuinely harder on both arms...
    assert outcome.metrics["baseline_mean"] < 0.6, (
        "the harder yardstick should not be easy for the baseline either, got "
        f"{outcome.metrics['baseline_mean']:.3f}"
    )
    # ...and because it applies to both, the matched difference is exactly zero.
    assert outcome.metrics["mean_difference"] == pytest.approx(0.0)
    assert outcome.metrics["direction"] == "inconclusive"
    assert outcome.metrics["regression_detected"] is False
    assert outcome.metrics["regression_confirmed"] is False
    assert outcome.metrics["regressed_scenarios"] == []
    # No scenario is *reported* as a regression. Some do lose points to the
    # harder yardstick on both arms, and those are reported as cases that fail
    # on both versions — a fact about the mock test set, not a version change.
    for finding in outcome.findings:
        assert "出现回归" not in finding.title


def test_pairing_survives_case_ordering(client: TestClient) -> None:
    """The comparison is keyed on scenario, so row order must not matter.

    This is the guard on the bug the old orchestration layer invited: keying the
    engine on ``TestCase.id`` or on list position pairs the wrong rows together,
    and the run reports a change that only exists in the pairing.
    """
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    start_and_wait(client, run.id)

    detail = client.get(f"/api/runs/{run.id}").json()
    cases = [TestCase.model_validate(item) for item in detail["test_cases"]]
    evidence_by_case = _group_evidence(
        [
            Evidence.model_validate(item)
            for item in detail["evidence"]
        ]
    )

    def evaluate(ordered: list[TestCase]):
        return asyncio.run(
            EvaluationService(seed=0, bootstrap_resamples=2000).evaluate_run_async(
                run_id=run.id,
                cases=ordered,
                evidence_by_case=evidence_by_case,
                baseline_version=DEMO_BASELINE_VERSION,
                candidate_version=DEMO_CANDIDATE_VERSION,
            )
        )

    forward = evaluate(cases)
    reversed_order = evaluate(list(reversed(cases)))
    version_grouped = evaluate(
        sorted(cases, key=lambda case: (case.version, str(case.input["scenario_id"])))
    )

    for other in (reversed_order, version_grouped):
        assert other.metrics["matched_scenarios"] == forward.metrics["matched_scenarios"]
        assert other.metrics["mean_difference"] == pytest.approx(
            forward.metrics["mean_difference"]
        )
        assert other.metrics["direction"] == forward.metrics["direction"]
        assert other.metrics["regressed_scenarios"] == forward.metrics["regressed_scenarios"]
        assert [v.scenario_id for v in other.cases] != []


def _group_evidence(evidence):
    grouped = {}
    for item in evidence:
        grouped.setdefault(item.test_case_id, []).append(item)
    return grouped


# --------------------------------------------------------------------------
# Honesty of the aggregate verdict and the summary
# --------------------------------------------------------------------------


def test_aggregate_verdict_is_not_hardcoded(client: TestClient) -> None:
    """The demo's aggregate verdict must be the engine's comparison, re-run.

    If the threshold, the seed or the scoring ever change, this test moves with
    them instead of pinning a verdict the data no longer supports.
    """
    _, report = _demo_report(client)
    metrics = report["metrics"]

    engine = asyncio.run(_recompute_engine(report["run_id"], client))
    assert metrics["direction"] == engine.direction.value
    assert metrics["is_significant"] is engine.is_significant
    assert metrics["regression_confirmed"] is (engine.direction.value == "regression")
    assert metrics["confidence"] == pytest.approx(engine.confidence)


async def _recompute_engine(run_id: str, client: TestClient):
    """Re-run the engine directly over the run's own rows."""
    detail = client.get(f"/api/runs/{run_id}").json()
    cases = [TestCase.model_validate(item) for item in detail["test_cases"]]
    evidence = [Evidence.model_validate(item) for item in detail["evidence"]]

    observations = [engine_mapping.to_observation(case, evidence) for case in cases]
    expectations = {
        engine_mapping.scenario_id(case): engine_mapping.to_expected_behavior(case.expected)
        for case in cases
    }
    attributed: dict[str, list[str]] = {}
    for case in cases:
        attributed.setdefault(engine_mapping.scenario_id(case), []).extend(
            engine_mapping.evidence_for(case, evidence)
        )
    report = await EngineService(seed=0, bootstrap_resamples=2000).compare_async(
        observations=observations,
        expectations=expectations,
        evidence_ids_by_case=attributed,
        run_id=run_id,
    )
    return report.comparison


def test_confirmed_verdict_is_supported_by_the_engine(client: TestClient) -> None:
    """The expanded demo must produce a statistically confirmed regression.

    The result is not hardcoded: the paired bootstrap has to place the entire
    confidence interval below the regression threshold. If fixture behavior
    changes and the signal weakens, this test fails rather than allowing the UI
    to claim a stronger result than the data supports.
    """
    _, report = _demo_report(client)
    summary = report["summary"]
    metrics = report["metrics"]

    assert metrics["regression_detected"] is True
    assert metrics["regression_confirmed"] is True
    assert metrics["direction"] == "regression"
    assert metrics["is_significant"] is True
    assert metrics["ci_upper"] < -metrics["regression_threshold"]
    assert metrics["confidence"] >= 0.95
    assert "回归" in summary
    assert "相对自身基线" in summary


def test_report_contract_still_holds(client: TestClient) -> None:
    """The frozen Report shape survives the engine swap."""
    _, payload = _demo_report(client)

    report = Report.model_validate(payload)
    assert report.summary
    assert report.findings
    assert report.model_dump(mode="json")["findings"] == payload["findings"]

    for finding in report.findings:
        assert finding.evidence_ids
        assert 0.0 <= finding.confidence <= 1.0

    # The metrics blob must stay JSON-serializable for the report row.
    assert json.loads(json.dumps(payload["metrics"]))


def test_pass_rate_metrics_are_strict_case_rates(client: TestClient) -> None:
    """Pass rate means fully passing cases, not fractional check coverage.

    A partially-correct answer is useful to the paired score, but the UI and
    release report must not call it a passing case. This pins the same
    invariant enforced by scripts/e2e-check.ps1.
    """
    run_id, report = _demo_report(client)
    detail = client.get(f"/api/runs/{run_id}").json()
    metrics = report["metrics"]

    for version in ("baseline", "candidate"):
        cases = [case for case in detail["test_cases"] if case["version"] == version]
        passed = sum(1 for case in cases if case["status"] == "passed")
        expected = passed / len(cases) if cases else 0.0
        assert metrics[f"{version}_pass_rate"] == pytest.approx(expected, abs=5e-5)
