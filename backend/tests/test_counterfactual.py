"""Tests for the counterfactual replay engine.

Two things are being pinned here, and they are different claims:

1. **The engine's contract** — verdicts follow from measured scores, evidence
   ids are real, controls are no-ops, and two identical replays agree.
2. **The fixture's causal story** — disabling compression restores the dropped
   clauses, enabling the security guard restores the credential refusal, and
   nothing else moves.

The second is asserted against a real demo run rather than against the
fixture module's own declarations, because the whole point of the engine is to
re-derive that story from executed output. A test that read
``scenario.candidate_drops`` and asserted the replay matched it would pass even
if the engine ignored the replay entirely.

Every test here is offline: the fixture executor is deterministic and the
reading source is in-memory.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from evalpilot.counterfactual import (
    CounterfactualEngine,
    CounterfactualTarget,
    ExperimentVerdict,
    InMemoryReadingSource,
    Intervention,
)
from evalpilot.demo import ensure_demo_project
from evalpilot.executor import COMPRESSION_DISABLED, SECURITY_GUARD_ENABLED
from evalpilot.models import Evidence, TestCase

from .conftest import start_and_wait

# Collected as a test class by pytest because of its name; it is a data model.
TestCase.__test__ = False

#: The scenarios the candidate is built to fail, and the intervention that
#: explains each. This is the fixture's declared causal story, restated here as
#: the *expected result* of a replay — never as its input.
COMPRESSION_REGRESSIONS = (
    "escalation-path",
    "escalation-timeframe",
    "escalation-channel",
    "urgent-safety",
    "battery-handling",
    "safety-reporting",
    "security-password-request",
)
SECURITY_REGRESSION = "prompt-injection-password"

#: Scenarios that behave identically in both versions.
CONTROLS = ("refund-window", "shipping-sla", "warranty-term", "privacy-retention")


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _run_completed_demo(client: TestClient) -> tuple[str, dict]:
    """Execute the deterministic demo once and return ``(run_id, detail)``."""
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    start_and_wait(client, run.id)
    return run.id, client.get(f"/api/runs/{run.id}").json()


def _candidate_row(detail: dict, scenario_id: str) -> dict:
    for case in detail["test_cases"]:
        if (
            case["version"] == "candidate"
            and case["input"]["scenario_id"] == scenario_id
        ):
            return case
    raise AssertionError(f"no candidate row for scenario {scenario_id!r}")


def _reading_source(detail: dict) -> InMemoryReadingSource:
    return InMemoryReadingSource(
        Evidence.model_validate(item) for item in detail["evidence"]
    )


def _target(detail: dict, scenario_id: str, intervention: Intervention) -> CounterfactualTarget:
    row = _candidate_row(detail, scenario_id)
    evidence_ids = [
        item["id"] for item in detail["evidence"] if item["test_case_id"] == row["id"]
    ]
    return CounterfactualTarget(
        scenario_id=scenario_id,
        run_id=detail["run"]["id"],
        test_case_id=row["id"],
        intervention=intervention,
        expected=row["expected"],
        original_evidence_ids=evidence_ids,
    )


@pytest.fixture
def demo_run(client: TestClient) -> dict:
    """The executed demo run, with its rows and evidence — the replay subject.

    Session-wide in behaviour but function-scoped in declaration because each
    test gets its own temporary database; the demo run itself is deterministic,
    so every test replays the same thing.
    """
    _, detail = _run_completed_demo(client)
    return detail


@pytest.fixture
def engine(demo_run: dict) -> CounterfactualEngine:
    return CounterfactualEngine(source=_reading_source(demo_run))


def _answer_text(source: InMemoryReadingSource, evidence_ids: list[str]) -> str | None:
    """The answer recorded by the first evidence row that carries one.

    The replayed arm's own evidence rows come first in the list, followed by
    the original arm's; the first row with an ``answer`` payload is therefore
    the arm's answer record, independent of how many retrieval citations the
    executor happened to attach ahead of it.
    """
    for evidence_id in evidence_ids:
        row = source.get_evidence(evidence_id)
        if row is not None and "answer" in row.payload:
            return str(row.payload["answer"])
    return None


def _prose(rationale: str) -> str:
    """The rationale's words, without the evidence citations it ends with."""
    marker = "Evidence: "
    return rationale.split(marker)[0] if marker in rationale else rationale


# --------------------------------------------------------------------------
# Grounding: the replay must come from persisted evidence
# --------------------------------------------------------------------------


def test_replayed_evidence_ids_are_persisted_rows(demo_run: dict) -> None:
    """Every evidence id an experiment reports must resolve to a real row.

    A claim that cites an id nobody can look up is not evidence-backed, so this
    checks the ids the engine *returned* against the store rather than trusting
    that it wrote them.
    """
    source = _reading_source(demo_run)
    engine = CounterfactualEngine(source=source)
    before = {item.id for item in source.all_evidence()}

    result = engine.replay(
        _target(demo_run, "urgent-safety", Intervention.COMPRESSION_DISABLED),
        investigation_id="inv-grounding",
    )

    assert result.evidence_ids, "an experiment must cite evidence"
    for evidence_id in result.evidence_ids:
        assert source.get_evidence(evidence_id) is not None, evidence_id

    # The claim cites both arms: the run's own rows, and the two observations
    # this replay produced.
    written = {item.id for item in source.added}
    assert written, "the two arms of the experiment must have been persisted"
    assert result.original.original_evidence_id in before
    assert set(result.replayed.evidence_ids) <= written

    # The replayed arm carries the restored answer, so the claim is checkable
    # against the text that was actually produced.
    replayed_answer = _answer_text(source, result.replayed.evidence_ids)
    assert replayed_answer is not None
    assert "emergency hotline" in replayed_answer
    assert "emergency hotline" not in _answer_text(source, result.original.evidence_ids)


def test_replay_reports_the_same_candidate_answer_the_run_produced(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    """The original arm must reproduce the executed run, not a fresh answer.

    If the replay's original arm diverged from what the run stored, the delta
    would measure the replay harness rather than the intervention.
    """
    row = _candidate_row(demo_run, "urgent-safety")

    result = engine.replay(
        _target(demo_run, "urgent-safety", Intervention.COMPRESSION_DISABLED)
    )

    assert result.metrics["original_answer"] == row["output"]["answer"]


def test_missing_evidence_makes_the_experiment_inconclusive(demo_run: dict) -> None:
    """An ungrounded citation is reported, not silently replayed.

    The engine must not fall back to re-running the case and calling the result
    an explanation: the caller cited something that does not exist, and the
    honest answer is that nothing was established.
    """
    engine = CounterfactualEngine(source=_reading_source(demo_run))
    row = _candidate_row(demo_run, "urgent-safety")

    result = engine.replay(
        CounterfactualTarget(
            scenario_id="urgent-safety",
            run_id=demo_run["run"]["id"],
            test_case_id=row["id"],
            intervention=Intervention.COMPRESSION_DISABLED,
            expected=row["expected"],
            original_evidence_ids=["00000000-0000-0000-0000-000000000000"],
        ),
        investigation_id="inv-missing",
    )

    assert result.verdict is ExperimentVerdict.INCONCLUSIVE
    assert result.confidence == 0.0
    assert result.counterfactual_score is None
    assert result.delta is None
    assert "00000000-0000-0000-0000-000000000000" in result.rationale
    assert "No replay was performed" in result.rationale


def test_missing_expectation_makes_the_experiment_inconclusive(demo_run: dict) -> None:
    """Without an expectation there is nothing to score a replayed answer against.

    The alternative — inventing a score — would produce a delta that no check
    ever computed.
    """
    engine = CounterfactualEngine(source=_reading_source(demo_run))
    row = _candidate_row(demo_run, "urgent-safety")
    evidence_ids = [
        item["id"]
        for item in demo_run["evidence"]
        if item["test_case_id"] == row["id"]
    ]

    result = engine.replay(
        CounterfactualTarget(
            scenario_id="urgent-safety",
            run_id=demo_run["run"]["id"],
            test_case_id=row["id"],
            intervention=Intervention.COMPRESSION_DISABLED,
            expected={},
            original_evidence_ids=evidence_ids,
        )
    )

    assert result.verdict is ExperimentVerdict.INCONCLUSIVE
    assert result.counterfactual_score is None
    assert "could not be scored" in result.rationale


def test_unknown_scenario_makes_the_experiment_inconclusive(demo_run: dict, engine) -> None:
    result = engine.replay(
        CounterfactualTarget(
            scenario_id="no-such-scenario",
            run_id=demo_run["run"]["id"],
            test_case_id="row",
            intervention=Intervention.COMPRESSION_DISABLED,
            expected={"must_include": ["x"]},
        )
    )

    assert result.verdict is ExperimentVerdict.INCONCLUSIVE
    assert "not in the fixture set" in result.rationale


def test_question_that_does_not_match_the_fixture_is_rejected(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    """A replay must not run under a prompt the run never used."""
    row = _candidate_row(demo_run, "urgent-safety")

    result = engine.replay(
        CounterfactualTarget(
            scenario_id="urgent-safety",
            run_id=demo_run["run"]["id"],
            test_case_id=row["id"],
            intervention=Intervention.COMPRESSION_DISABLED,
            expected=row["expected"],
            question="Some other question entirely?",
        )
    )

    assert result.verdict is ExperimentVerdict.INCONCLUSIVE
    assert "does not match the fixture" in result.rationale


def test_unknown_intervention_is_rejected_rather_than_defaulted() -> None:
    """An unsupported intervention must raise, not silently become a no-op.

    A replay that fell through to "run the candidate unchanged" would report
    ``no_effect`` for every hypothesis — which reads as a clean bill of health
    for a defect that was never actually tested.
    """
    with pytest.raises(ValueError, match="Unknown intervention"):
        Intervention.parse("disable_everything")

    with pytest.raises(ValueError):
        Intervention.parse("")


# --------------------------------------------------------------------------
# Root cause: compression disabled restores the dropped clauses
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", COMPRESSION_REGRESSIONS)
def test_compression_disabled_is_the_root_cause_of_the_dropped_clauses(
    demo_run: dict, engine: CounterfactualEngine, scenario_id: str
) -> None:
    """The headline claim: one compression step explains all seven failures.

    Restoring it lifts each case to a clean pass, so the behaviour is
    implicated in the whole failure and not merely correlated with it.
    """
    result = engine.replay(_target(demo_run, scenario_id, Intervention.COMPRESSION_DISABLED))

    assert result.verdict is ExperimentVerdict.ROOT_CAUSE, result.rationale
    assert result.original_score is not None and result.original_score < 1.0
    assert result.counterfactual_score == pytest.approx(1.0)
    assert result.delta is not None and result.delta > 0
    assert result.confidence == pytest.approx(1.0)
    assert result.replayed.failing_checks == []
    assert result.is_positive
    # The rationale is rendered from the measurement, so the numbers are in it.
    assert scenario_id in result.rationale
    assert "compression_disabled" in result.rationale


def test_the_restored_text_is_the_clause_that_was_dropped(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    """The delta is backed by the text that came back, not just by a number."""
    result = engine.replay(
        _target(demo_run, "urgent-safety", Intervention.COMPRESSION_DISABLED)
    )

    restored = result.metrics["restored_text"]
    assert restored, "the intervention restored text, so it must be reported"
    assert "emergency hotline" in restored
    assert "emergency hotline" not in result.metrics["original_answer"]


def test_compression_is_not_the_cause_of_the_credential_disclosure(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    """The wrong hypothesis must be reported as wrong, not left unstated.

    This is the discriminating test for the whole engine: two interventions,
    two different failures, and each one must come out the right way round.
    """
    result = engine.replay(
        _target(demo_run, SECURITY_REGRESSION, Intervention.COMPRESSION_DISABLED)
    )

    assert result.verdict is ExperimentVerdict.NO_EFFECT, result.rationale
    assert result.delta == pytest.approx(0.0)
    assert result.metrics["restored_text"] is None
    assert not result.is_positive


# --------------------------------------------------------------------------
# Security intervention restores the credential refusal
# --------------------------------------------------------------------------


def test_security_guard_is_the_root_cause_of_the_credential_disclosure(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    result = engine.replay(
        _target(demo_run, SECURITY_REGRESSION, Intervention.SECURITY_GUARD_ENABLED)
    )

    assert result.verdict is ExperimentVerdict.ROOT_CAUSE, result.rationale
    assert result.original_score == pytest.approx(0.0)
    assert result.counterfactual_score == pytest.approx(1.0)
    assert result.delta == pytest.approx(1.0)

    # The leak is gone and the refusal is back — the behaviour was restored,
    # not merely re-scored.
    assert "sk-live-demo-secret" not in result.replayed.answer
    assert result.replayed.refused is True
    assert result.replayed.answer.startswith("I can only answer questions")


@pytest.mark.parametrize(
    "scenario_id",
    ["escalation-path", "urgent-safety", "security-password-request"],
)
def test_enabling_the_security_guard_does_not_explain_the_dropped_clauses(
    demo_run: dict, engine: CounterfactualEngine, scenario_id: str
) -> None:
    """The mirror of the previous test: a control intervention on a real defect.

    Enabling the guard leaves the dropped-clause failures untouched, which is
    what makes ``compression_disabled`` the discriminating explanation rather
    than one of two interventions that both "fix" everything.
    """
    result = engine.replay(_target(demo_run, scenario_id, Intervention.SECURITY_GUARD_ENABLED))

    assert result.verdict is ExperimentVerdict.NO_EFFECT, result.rationale
    assert result.delta == pytest.approx(0.0)
    assert result.original_score == result.counterfactual_score


def test_the_two_interventions_partition_the_fixture_failures(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    """Every candidate failure has exactly one explaining intervention.

    This is the property the investigation layer's root-cause claim rests on.
    Each intervened cell may move at most one case in the matrix of (scenario,
    intervention); no row may be explained by both behaviours.
    """
    explained: dict[str, str] = {}
    for scenario_id in COMPRESSION_REGRESSIONS + (SECURITY_REGRESSION,):
        for intervention in (
            Intervention.COMPRESSION_DISABLED,
            Intervention.SECURITY_GUARD_ENABLED,
        ):
            result = engine.replay(_target(demo_run, scenario_id, intervention))
            if result.verdict is ExperimentVerdict.ROOT_CAUSE:
                assert scenario_id not in explained, (
                    f"{scenario_id} is explained by both "
                    f"{explained[scenario_id]} and {intervention.value}"
                )
                explained[scenario_id] = intervention.value

    assert explained == {
        **{scenario_id: COMPRESSION_DISABLED for scenario_id in COMPRESSION_REGRESSIONS},
        SECURITY_REGRESSION: SECURITY_GUARD_ENABLED,
    }


# --------------------------------------------------------------------------
# Controls and no-effect
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", CONTROLS)
def test_controls_show_no_effect(
    demo_run: dict, engine: CounterfactualEngine, scenario_id: str
) -> None:
    """A scenario that never regressed has nothing for an intervention to fix."""
    for intervention in (
        Intervention.COMPRESSION_DISABLED,
        Intervention.SECURITY_GUARD_ENABLED,
    ):
        result = engine.replay(_target(demo_run, scenario_id, intervention))

        assert result.verdict is ExperimentVerdict.NO_EFFECT, result.rationale
        assert result.original_score == pytest.approx(1.0)
        assert result.counterfactual_score == pytest.approx(1.0)
        assert result.delta == pytest.approx(0.0)
        assert result.metrics["restored_text"] is None
        assert "did not regress" in result.rationale


def test_the_none_intervention_changes_nothing_at_all(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    """The control intervention is the replay path's own fidelity check.

    It re-runs the case unmodified on both arms and must produce byte-identical
    answers. A difference here would mean the replay harness leaked state
    between arms, which would invalidate every other experiment.
    """
    for scenario_id in ("urgent-safety", SECURITY_REGRESSION, "refund-window"):
        result = engine.replay(_target(demo_run, scenario_id, Intervention.NONE))

        assert result.verdict is ExperimentVerdict.NO_EFFECT
        assert result.delta == pytest.approx(0.0)
        assert result.original.answer == result.replayed.answer
        assert result.original.evidence_ids != result.replayed.evidence_ids, (
            "each arm is a separate observation and must carry its own evidence"
        )


def test_a_control_intervention_reproduces_the_executed_answer(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    """A control replay must land on the answer the run actually stored."""
    row = _candidate_row(demo_run, "refund-window")

    result = engine.replay(_target(demo_run, "refund-window", Intervention.NONE))

    assert result.original.answer == row["output"]["answer"]
    assert result.replayed.answer == row["output"]["answer"]


# --------------------------------------------------------------------------
# Partial
# --------------------------------------------------------------------------


def test_a_partial_recovery_is_reported_as_partial(demo_run: dict) -> None:
    """A replay that recovers score while a failing check remains is ``partial``.

    ``escalation-timeframe`` requires "within 24 hours", which the candidate's
    compression step drops. The expectation here additionally asserts a fact the
    source document does not contain, modelling a case whose failure has more
    than one cause: the intervention restores what it can and the case still
    fails, so the behaviour is implicated but is not the whole story.

    The extra phrase is deliberately absent from ``kb-escalation`` — this is a
    synthetic second cause, not a claim about the fixture.
    """
    row = _candidate_row(demo_run, "escalation-timeframe")
    evidence_ids = [
        item["id"] for item in demo_run["evidence"] if item["test_case_id"] == row["id"]
    ]
    engine = CounterfactualEngine(source=_reading_source(demo_run))

    def replay(must_include: list[str]):
        return engine.replay(
            CounterfactualTarget(
                scenario_id="escalation-timeframe",
                run_id=demo_run["run"]["id"],
                test_case_id=row["id"],
                intervention=Intervention.COMPRESSION_DISABLED,
                expected={
                    "must_include": must_include,
                    "must_avoid": [],
                    "expects_refusal": False,
                    "expected_doc_ids": ["kb-escalation"],
                },
                original_evidence_ids=evidence_ids,
            )
        )

    # The scenario's own expectation: restoring the clause clears the failure,
    # so the same intervention is a clean root cause.
    restored = replay(["within 24 hours"])
    assert restored.verdict is ExperimentVerdict.ROOT_CAUSE, restored.rationale
    assert restored.original_score == pytest.approx(0.5)
    assert restored.counterfactual_score == pytest.approx(1.0)

    # A second, unsatisfiable cause keeps a failing check in the replayed arm.
    partial = replay(["within 24 hours", "refund"])
    assert partial.verdict is ExperimentVerdict.PARTIAL, partial.rationale
    assert partial.original_score == pytest.approx(0.5)
    assert partial.counterfactual_score == pytest.approx(0.75)
    assert partial.delta == pytest.approx(0.25)
    assert partial.replayed.failing_checks == ["facts"]
    assert partial.confidence == pytest.approx(0.25)
    assert partial.is_positive
    assert "recovered 0.25" in partial.rationale


def test_root_cause_does_not_require_the_original_to_have_scored_zero(
    demo_run: dict, engine: CounterfactualEngine
) -> None:
    """``root_cause`` keys on cleared failing checks, not on the score reaching 1.0.

    ``escalation-path`` asserts two facts and the candidate drops the sentence
    that carries both, so the original scores 0.5 — the format check and the
    facts check each weigh equally in the mean, and only one of them fails.
    Restoring the clause clears the only failing check, which is what makes the
    behaviour the cause of the failure; a rule written on "the score went to 1.0
    from a complete failure" would call this partial and under-report it.
    """
    result = engine.replay(
        _target(demo_run, "escalation-path", Intervention.COMPRESSION_DISABLED)
    )

    assert result.verdict is ExperimentVerdict.ROOT_CAUSE, result.rationale
    assert result.original_score == pytest.approx(0.5)
    assert result.counterfactual_score == pytest.approx(1.0)
    assert result.original.failing_checks == ["facts"]
    assert result.replayed.failing_checks == []
    assert result.metrics["original_failed_completely"] is False
    assert "accounts for the failure" in result.rationale


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_the_same_replay_twice_gives_the_same_answer(demo_run: dict) -> None:
    """Reproducibility is the product claim; a replay must not drift.

    The measurement is what has to be stable. Each replay writes its own
    evidence rows, so the *ids* the rationale cites are necessarily new — the
    rationale's prose up to that citation list is compared, and a separate test
    covers the id ordering.
    """
    engine = CounterfactualEngine(source=_reading_source(demo_run))
    target = _target(demo_run, "urgent-safety", Intervention.COMPRESSION_DISABLED)

    first = engine.replay(target, investigation_id="inv-repro")
    second = engine.replay(target, investigation_id="inv-repro")

    assert first.verdict is second.verdict
    assert first.original_score == second.original_score
    assert first.counterfactual_score == second.counterfactual_score
    assert first.delta == second.delta
    assert first.confidence == second.confidence
    assert first.replayed.answer == second.replayed.answer
    assert first.metrics["restored_text"] == second.metrics["restored_text"]
    assert _prose(first.rationale) == _prose(second.rationale)


def test_a_fresh_engine_over_a_fresh_source_agrees(demo_run: dict) -> None:
    """The result must depend on the run, not on engine instance state."""
    target = _target(demo_run, SECURITY_REGRESSION, Intervention.SECURITY_GUARD_ENABLED)

    first = CounterfactualEngine(source=_reading_source(demo_run)).replay(target)
    second = CounterfactualEngine(source=_reading_source(demo_run)).replay(target)

    assert first.verdict is second.verdict
    assert first.delta == second.delta
    assert first.counterfactual_score == second.counterfactual_score


def test_evidence_ids_are_ordered_original_arm_first(demo_run: dict) -> None:
    """Ordering is stable so two identical experiments are comparable.

    An intervention that changed nothing produces identical *scores*; the ids
    still have to come back in a deterministic order or the persisted artifacts
    of two identical investigations look different.
    """
    engine = CounterfactualEngine(source=_reading_source(demo_run))
    result = engine.replay(
        _target(demo_run, "urgent-safety", Intervention.COMPRESSION_DISABLED)
    )

    assert result.evidence_ids[0] == result.original.original_evidence_id
    assert len(result.evidence_ids) == len(set(result.evidence_ids))


# --------------------------------------------------------------------------
# The batch protocol and the executor seam
# --------------------------------------------------------------------------


def test_replay_batch_returns_one_experiment_per_target(demo_run: dict) -> None:
    engine = CounterfactualEngine(source=_reading_source(demo_run))
    targets = [
        _target(demo_run, "urgent-safety", Intervention.COMPRESSION_DISABLED),
        _target(demo_run, SECURITY_REGRESSION, Intervention.SECURITY_GUARD_ENABLED),
        _target(demo_run, SECURITY_REGRESSION, Intervention.COMPRESSION_DISABLED),
        _target(demo_run, "refund-window", Intervention.NONE),
    ]

    summary = engine.replay_batch(targets, investigation_id="inv-batch")

    assert len(summary.experiments) == len(targets)
    assert summary.investigation_id == "inv-batch"
    assert summary.run_id == demo_run["run"]["id"]
    assert all(e.investigation_id == "inv-batch" for e in summary.experiments)
    assert summary.counts_by_verdict == {"root_cause": 2, "no_effect": 2}
    assert [e.scenario_id for e in summary.experiments] == [
        t.scenario_id for t in targets
    ]


def test_executor_interventions_are_named_by_this_package() -> None:
    """The engine's vocabulary and the executor's seam must not drift apart."""
    assert Intervention.COMPRESSION_DISABLED.value == COMPRESSION_DISABLED
    assert Intervention.SECURITY_GUARD_ENABLED.value == SECURITY_GUARD_ENABLED
    assert Intervention.NONE.executor_value is None
    assert Intervention.parse(COMPRESSION_DISABLED) is Intervention.COMPRESSION_DISABLED


def test_replaying_does_not_touch_the_database(client: TestClient, demo_run: dict) -> None:
    """The engine persists nothing of its own.

    Everything it writes goes through the injected reading source, so the
    repository the run lives in is untouched — which is what makes a replay
    safe to run against a finished, audited run.
    """
    container = client.app.state.container
    run_id = demo_run["run"]["id"]
    before = (
        container.repo.count_evidence(run_id),
        container.repo.count_findings(run_id),
        container.repo.count_events(run_id),
    )

    engine = CounterfactualEngine(source=_reading_source(demo_run))
    engine.replay(_target(demo_run, "urgent-safety", Intervention.COMPRESSION_DISABLED))
    engine.replay(_target(demo_run, SECURITY_REGRESSION, Intervention.SECURITY_GUARD_ENABLED))

    after = (
        container.repo.count_evidence(run_id),
        container.repo.count_findings(run_id),
        container.repo.count_events(run_id),
    )
    assert after == before


def test_the_engine_imports_no_repository_or_routes(client: TestClient) -> None:
    """A structural guarantee, checked mechanically.

    The investigation backend has to be able to call this package without
    pulling in the repository or the HTTP layer. Checking ``sys.modules``
    directly would prove nothing, because the FastAPI test client that other
    tests in this file share has already imported all of them; so this asserts
    the *source* of the package's own modules instead.
    """
    import ast
    import pathlib

    package = pathlib.Path(__file__).resolve().parents[1] / "evalpilot" / "counterfactual"
    forbidden = ("evalpilot.repository", "evalpilot.routes", "evalpilot.app", "evalpilot.container")

    offenders: list[str] = []
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                targets = [node.module]
            elif isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            else:
                continue
            offenders.extend(
                f"{path.name}: {target}"
                for target in targets
                if target in forbidden
            )

    assert not offenders, f"counterfactual must not import repository/routes/app: {offenders}"
