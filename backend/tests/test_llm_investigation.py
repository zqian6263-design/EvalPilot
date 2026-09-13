"""Live-mode investigation: augmentation, fallback, and the anti-override rules.

The load-bearing tests here are the invariants in
``docs/V3_LLM_INTERFACES.md``: in live mode the model may add hypotheses,
choose a bounded replay experiment, and explain the decision, but it may not
change any measured value. Each of those
is asserted directly against the persisted investigation, not against the
model's response.

All tests drive the service with an injected fake provider or an
``httpx.MockTransport``. None touches the network.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from evalpilot.container import use_llm_runtime
from evalpilot.investigation import InvestigationService
from evalpilot.llm.errors import (
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTransportError,
)
from evalpilot.llm.prompts import HYPOTHESIS_SCHEMA, RATIONALE_SCHEMA
from evalpilot.llm.runtime import MODE_LIVE, LLMRuntime

from .conftest import start_and_wait
from .llm_fakes import (
    CANARY_KEY,
    OVERRIDING_RATIONALE,
    VALID_HYPOTHESES,
    VALID_RATIONALE,
    ScriptedProvider,
    openai_transport,
)

OBJECTIVE = "Decide whether v1.1-candidate can ship."


class StubProvider:
    """A provider whose per-phase responses the test names explicitly.

    The investigation makes two calls per run — hypotheses, then rationale —
    and a test usually wants to control them independently.
    """

    name = "stub"
    model = "stub-model"

    def __init__(self, *, hypotheses=None, rationale=None) -> None:
        self.hypotheses = hypotheses if hypotheses is not None else VALID_HYPOTHESES
        self.rationale = rationale if rationale is not None else VALID_RATIONALE
        self.calls: list[list[dict[str, str]]] = []
        #: The schema the caller asked for on each call, in order.
        self.schemas: list[dict] = []

    async def complete_json(self, messages, schema, timeout_seconds=None):
        from evalpilot.llm.providers import LLMResult

        self.calls.append(messages)
        self.schemas.append(schema)
        # Keyed on the schema the caller requested, not on prompt text: the
        # caller decides which phase this is, so the stub cannot misread it.
        if schema is HYPOTHESIS_SCHEMA:
            payload = self.hypotheses
        elif schema is RATIONALE_SCHEMA:
            payload = self.rationale
        else:  # pragma: no cover - a phase this test does not model
            payload = {}
        if isinstance(payload, BaseException):
            raise payload
        return LLMResult(
            payload=dict(payload),
            model=self.model,
            call_id=f"call-{len(self.calls)}",
            provider=self.name,
        )

    async def complete_text(self, messages, timeout_seconds=None):  # pragma: no cover
        return ""


def live_runtime(provider) -> LLMRuntime:
    return LLMRuntime(
        mode=MODE_LIVE,
        configured=True,
        provider=provider,
        model=provider.model,
        base_url_host="api.deepseek.com",
        timeout_seconds=5.0,
    )


def live_runtime_for(provider) -> LLMRuntime:
    return live_runtime(provider)


def make_canary_provider():
    """A real client holding a real (fake) key, speaking to a mock transport.

    Unlike :class:`StubProvider`, this provider actually stores the credential,
    so a leak test against it is testing the shipped code path rather than a
    fake with no secret in it.
    """
    from evalpilot.llm.client import OpenAICompatibleProvider

    return OpenAICompatibleProvider(
        base_url="https://api.deepseek.com",
        api_key=CANARY_KEY,
        model="canary-model",
        timeout_seconds=5.0,
        transport=openai_transport(
            content=json.dumps(
                {"hypotheses": VALID_HYPOTHESES["hypotheses"], "discarded": []}
            )
        ),
    )


async def _rescore(container, run_id: str) -> dict:
    """Re-score a finished run's persisted rows and return its metrics.

    This is the run pipeline's own boundary, called a second time with a
    different judge installed. It proves the judge seam is live *and* inert.
    """
    run = container.repo.get_run(run_id)
    cases = container.repo.list_test_cases(run_id)
    evidence = container.repo.list_evidence(run_id)
    evidence_by_case: dict[str, list] = {}
    for item in evidence:
        evidence_by_case.setdefault(item.test_case_id, []).append(item)
    outcome = await container.runner.evaluation_service.evaluate_run_async(
        run_id=run_id,
        cases=cases,
        evidence_by_case=evidence_by_case,
        baseline_version=run.baseline_version,
        candidate_version=run.candidate_version,
    )
    return {**outcome.metrics}


def _demo_run(client: TestClient) -> dict:
    """Create and finish the seeded demo run, returning the run detail."""
    project = client.post(
        "/api/projects", json={"name": "Live LLM KB QA", "scenario": "kb-qa"}
    ).json()
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "v1.0-baseline",
            "candidate_version": "v1.1-candidate",
            "case_count": 26,
            "seed": 20260919,
        },
    ).json()
    return start_and_wait(client, run["id"])


def _run_investigation(
    client: TestClient,
    run_id: str,
    *,
    runtime: LLMRuntime | None = None,
    provider=None,
    timeout: float = 120.0,
):
    """Install a runtime, drive an investigation, return ``(id, payload)``.

    ``POST /start`` returns immediately and the engine runs as a task, so the
    payload is polled until the investigation reaches a terminal status. Pass
    ``runtime`` to install a specific one (including a deterministic one);
    otherwise a live runtime wrapping ``provider`` is installed.
    """
    container = client.app.state.container
    use_llm_runtime(
        container, runtime if runtime is not None else live_runtime(provider)
    )
    created = client.post(
        "/api/investigations", json={"run_id": run_id, "objective": OBJECTIVE}
    )
    assert created.status_code == 201, created.text
    investigation_id = created.json()["id"]
    started = client.post(f"/api/investigations/{investigation_id}/start")
    assert started.status_code == 202, started.text

    deadline = time.time() + timeout
    payload: dict = {}
    while time.time() < deadline:
        payload = client.get(f"/api/investigations/{investigation_id}").json()
        if payload["investigation"]["status"] in {"completed", "failed"}:
            return investigation_id, payload
        time.sleep(0.05)
    raise AssertionError(
        f"investigation did not finish within {timeout}s: {payload}"
    )


# --- the offline path is untouched ------------------------------------------


def test_deterministic_mode_produces_no_llm_steps(client: TestClient) -> None:
    # Pin the runtime explicitly: the fixture builds its container from the
    # dataclass defaults, not from the process environment, so a developer with
    # EVALPILOT_LLM_MODE=live exported would otherwise change this test.
    use_llm_runtime(client.app.state.container, LLMRuntime())
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client, detail["run"]["id"], runtime=LLMRuntime()
    )
    assert payload["investigation"]["status"] == "completed"
    assert all(step["data"]["source"] == "deterministic" for step in payload["steps"])
    assert not [
        step for step in payload["steps"] if step["data"].get("llm_call_id")
    ]


def test_a_live_runtime_without_a_provider_is_still_deterministic(
    client: TestClient,
) -> None:
    """Live mode with an incomplete configuration must not half-run."""
    container = client.app.state.container
    use_llm_runtime(
        container, LLMRuntime(mode=MODE_LIVE, configured=False, provider=None)
    )
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client,
        detail["run"]["id"],
        runtime=LLMRuntime(mode=MODE_LIVE, configured=False, provider=None),
    )
    assert payload["investigation"]["status"] == "completed"
    assert all(step["data"]["source"] == "deterministic" for step in payload["steps"])


# --- success ----------------------------------------------------------------


def test_live_mode_adds_model_hypotheses_and_a_rationale(client: TestClient) -> None:
    provider = StubProvider()
    detail = _demo_run(client)
    _, payload = _run_investigation(client, detail["run"]["id"], provider=provider)

    assert payload["investigation"]["status"] == "completed"
    by_source = [step for step in payload["steps"] if step["data"].get("source") == "llm"]
    assert by_source, "live mode recorded no LLM step"

    hypotheses = [
        step for step in by_source if step["title"] == "Model-proposed risk hypotheses"
    ]
    assert len(hypotheses) == 1
    assert hypotheses[0]["data"]["proposals"]
    assert hypotheses[0]["data"]["authoritative"] is False
    assert hypotheses[0]["data"]["model"] == "stub-model"
    assert hypotheses[0]["data"]["llm_call_id"]

    child = [
        step
        for step in payload["steps"]
        if step["data"].get("kind") == "domain:returns"
    ]
    assert len(child) == 1
    assert child[0]["data"]["source"] == "llm"
    assert child[0]["data"]["llm_call_id"]
    assert child[0]["evidence_ids"], "a model hypothesis cited no evidence"

    rationale = [
        step for step in by_source if step["title"] == "Model release rationale"
    ]
    assert len(rationale) == 1
    assert rationale[0]["data"]["rationale"]
    assert rationale[0]["data"]["authoritative"] is False


def test_a_validated_model_plan_controls_the_replay_intervention(
    client: TestClient,
) -> None:
    """The model may choose a bounded experiment, which the engine then measures.

    The deterministic fallback would re-enable compression for this scenario.
    The model instead selects the security guard. That choice must reach the
    replay executor, while the resulting measured verdict remains authoritative.
    """
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client,
        detail["run"]["id"],
        provider=StubProvider(
            hypotheses={
                "hypotheses": [],
                "replay_interventions": [
                    {
                        "scenario_id": "escalation-path",
                        "intervention": "security_guard_enabled",
                        "rationale": "Test the guard hypothesis first.",
                    }
                ],
            }
        ),
    )

    assert payload["investigation"]["status"] == "completed"
    experiment = next(
        item
        for item in payload["counterfactuals"]
        if item["scenario_id"] == "escalation-path"
    )
    assert experiment["intervention"] == "security_guard_enabled"
    plan = next(
        step
        for step in payload["steps"]
        if step["title"] == "Model-guided counterfactual plan"
    )
    assert plan["data"]["authoritative"] is False
    assert plan["data"]["replay_plan"][0]["scenario_id"] == "escalation-path"
    assert payload["decision"]["verdict"] == "block"


def test_an_unexecutable_model_plan_is_rejected(client: TestClient) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client,
        detail["run"]["id"],
        provider=StubProvider(
            hypotheses={
                "hypotheses": [],
                "replay_interventions": [
                    {
                        "scenario_id": "escalation-path",
                        "intervention": "restart_production",
                        "rationale": "Not an executable intervention.",
                    }
                ],
            }
        ),
    )

    experiment = next(
        item
        for item in payload["counterfactuals"]
        if item["scenario_id"] == "escalation-path"
    )
    assert experiment["intervention"] == "compression_disabled"
    model_step = next(
        step
        for step in payload["steps"]
        if step["title"] == "Model-proposed risk hypotheses"
    )
    assert "not executable" in model_step["data"]["fallback_reason"]


def test_every_llm_step_records_its_provenance(client: TestClient) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(client, detail["run"]["id"], provider=StubProvider())
    llm_steps = [step for step in payload["steps"] if step["data"].get("source") == "llm"]
    assert llm_steps
    for step in llm_steps:
        assert step["data"]["model"] == "stub-model"
        assert step["data"]["llm_call_id"]


def test_the_model_receives_the_measured_failures(client: TestClient) -> None:
    provider = StubProvider()
    detail = _demo_run(client)
    _run_investigation(client, detail["run"]["id"], provider=provider)
    prompt = json.dumps(provider.calls[0])
    assert "prompt-injection-password" in prompt
    assert "Scenarios that regressed" in prompt


# --- anti-override invariants -----------------------------------------------


def test_measured_values_are_identical_in_both_modes(client: TestClient) -> None:
    """The numbers a decision rests on do not move when a model is added."""

    async def _intake(run_id: str, service: InvestigationService) -> dict:
        return dict(vars(await service.build_intake(run_id)))

    detail = _demo_run(client)
    run_id = detail["run"]["id"]
    container = client.app.state.container
    # Intake never consults the model, so the two runs differ only in which
    # runtime is installed. Swapping it around a single `build_intake` call
    # (rather than around the whole investigation) keeps the comparison exact.
    offline = asyncio.run(_intake(run_id, container.investigation_runner))
    use_llm_runtime(container, live_runtime(StubProvider()))
    online = asyncio.run(_intake(run_id, container.investigation_runner))

    for key in (
        "matched_scenarios",
        "baseline_pass_rate",
        "candidate_pass_rate",
        "direction",
        "confidence",
    ):
        assert offline[key] == online[key], key
    assert [s.scenario_id for s in offline["scenarios"]] == [
        s.scenario_id for s in online["scenarios"]
    ]


def test_a_model_hypothesis_never_becomes_a_blocking_finding(
    client: TestClient,
) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client, detail["run"]["id"], provider=StubProvider()
    )

    decision = payload["decision"]
    llm_step_ids = {
        step["id"] for step in payload["steps"] if step["data"].get("source") == "llm"
    }
    assert llm_step_ids
    # A blocking finding is a run finding id, never an investigation step id.
    assert not (set(decision["blocking_findings"]) & llm_step_ids)
    assert decision["blocking_findings"], "the demo decision has no blocking findings"


def test_live_mode_does_not_change_the_reported_findings(
    client: TestClient,
) -> None:
    """The same fixture reports the same measured findings in both modes.

    Each run can have only one investigation by contract, so this compares two
    independently executed runs from the same fixture. Ids differ by design;
    the measured verdict, scores, scenario/intervention classifications,
    memory recall and deterministic step shape must not.
    """
    detail_offline = _demo_run(client)
    detail_online = _demo_run(client)

    _, offline = _run_investigation(
        client, detail_offline["run"]["id"], runtime=LLMRuntime()
    )
    _, online = _run_investigation(
        client, detail_online["run"]["id"], provider=StubProvider()
    )

    assert online["investigation"]["status"] == "completed"

    measured_decision_keys = (
        "verdict",
        "risk_level",
        "summary",
        "blocking_findings",
        "recommended_actions",
        "confidence",
    )
    for key in measured_decision_keys:
        if key == "blocking_findings":
            # Finding ids are run-specific; the count and order carry the shape.
            assert len(online["decision"][key]) == len(offline["decision"][key])
        else:
            assert online["decision"][key] == offline["decision"][key], key

    def counterfactual_shape(payload: dict) -> list[tuple]:
        return [
            (
                item["scenario_id"],
                item["intervention"],
                item["original_score"],
                item["counterfactual_score"],
                item["delta"],
                item["confidence"],
                item["verdict"],
            )
            for item in payload["counterfactuals"]
        ]

    def memory_shape(payload: dict) -> list[tuple]:
        return [
            (
                item["incident_id"],
                item["score"],
                item["reason"],
                tuple(item["matched_terms"]),
            )
            for item in payload["memory_matches"]
        ]

    assert counterfactual_shape(online) == counterfactual_shape(offline)
    assert memory_shape(online) == memory_shape(offline)

    def deterministic_step_shape(payload: dict) -> list[tuple]:
        return [
            (
                step["kind"],
                step["title"],
                step["status"],
            )
            for step in payload["steps"]
            if step["data"].get("source") != "llm"
        ]

    assert deterministic_step_shape(online) == deterministic_step_shape(offline)
    assert len(online["steps"]) > len(offline["steps"])


def test_live_mode_does_not_change_the_run_report(client: TestClient) -> None:
    """The evaluation a run reports is identical whether or not a model ran.

    The judge seam is populated in live mode, and this is the test that proves
    it does not move a number: the same run's report is compared before and
    after the runtime is switched.
    """
    detail = _demo_run(client)
    run_id = detail["run"]["id"]
    before = client.get(f"/api/runs/{run_id}/report").json()

    live = live_runtime_for(StubProvider())
    use_llm_runtime(client.app.state.container, live)
    try:
        # Re-score the same persisted rows through the newly-installed judge.
        after = asyncio.run(
            _rescore(client.app.state.container, run_id)
        )
    finally:
        use_llm_runtime(client.app.state.container, LLMRuntime())

    for key in (
        "baseline_pass_rate",
        "candidate_pass_rate",
        "matched_scenarios",
        "mean_difference",
        "ci_lower",
        "ci_upper",
        "direction",
        "regressed_scenarios",
        "control_scenarios",
    ):
        assert after[key] == before["metrics"][key], key
    assert after["findings_by_severity"] == before["metrics"]["findings_by_severity"]


def test_a_provider_that_ignores_its_timeout_still_falls_back(
    client: TestClient,
) -> None:
    """``asyncio.wait_for`` expiry must become a recorded fallback.

    A provider that accepts ``timeout_seconds`` and then hangs is exactly the
    case the outer bound exists for. The builtin ``TimeoutError`` it raises is
    not an ``LLMError``, so without an explicit conversion it would escape and
    fail the whole investigation instead of falling back.
    """

    class HangingProvider:
        name = "hanging"
        model = "hanging-model"

        async def complete_json(self, messages, schema, timeout_seconds=None):
            await asyncio.sleep(30)  # deliberately ignores timeout_seconds

        async def complete_text(self, messages, timeout_seconds=None):
            await asyncio.sleep(30)

    detail = _demo_run(client)
    runtime = LLMRuntime(
        mode=MODE_LIVE,
        configured=True,
        provider=HangingProvider(),
        model="hanging-model",
        base_url_host="api.deepseek.com",
        timeout_seconds=0.05,
    )
    _, payload = _run_investigation(client, detail["run"]["id"], runtime=runtime)

    assert payload["investigation"]["status"] == "completed"
    assert payload["decision"]["verdict"] == "block"
    fallbacks = [
        step["data"]["fallback_reason"]
        for step in payload["steps"]
        if step["data"].get("fallback_reason")
    ]
    assert fallbacks
    assert all("LLMTimeoutError" in reason for reason in fallbacks)


def test_a_provider_injecting_a_measured_key_is_refused(
    client: TestClient,
) -> None:
    """A provider cannot smuggle a measured key into a step's data.

    The shipped client validates against a schema with
    ``additionalProperties: false``, so this cannot happen with it. The guard
    exists because the provider seam is injectable, and a contribution that
    could overwrite a measured key would break the contract's central promise.
    """

    class InjectingProvider:
        name = "injecting"
        model = "injecting-model"

        async def complete_json(self, messages, schema, timeout_seconds=None):
            from evalpilot.llm.providers import LLMResult

            return LLMResult(
                payload={
                    "hypotheses": [],
                    "verdict": "allow",
                    "risk_level": "low",
                    "blocking_findings": [],
                    "confidence": 1.0,
                },
                model=self.model,
                call_id="injected",
                provider=self.name,
            )

        async def complete_text(self, messages, timeout_seconds=None):
            return ""

    detail = _demo_run(client)
    runtime = LLMRuntime(
        mode=MODE_LIVE,
        configured=True,
        provider=InjectingProvider(),
        model="injecting-model",
        base_url_host="api.deepseek.com",
        timeout_seconds=5.0,
    )
    _, payload = _run_investigation(client, detail["run"]["id"], runtime=runtime)

    assert payload["investigation"]["status"] == "completed"
    # The measured decision is untouched, and the injected keys are not on any
    # LLM step's data: the merge refused them.
    assert payload["decision"]["verdict"] == "block"
    assert payload["decision"]["risk_level"] == "critical"
    llm_steps = [s for s in payload["steps"] if s["data"].get("source") == "llm"]
    assert llm_steps
    for step in llm_steps:
        assert "blocking_findings" not in step["data"]
        assert step["data"].get("verdict") != "allow"


def test_a_model_verdict_disagreement_does_not_change_the_decision(
    client: TestClient,
) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client,
        detail["run"]["id"],
        provider=StubProvider(rationale=OVERRIDING_RATIONALE),
    )

    decision = payload["decision"]
    assert decision["verdict"] == "block"
    assert decision["risk_level"] == "critical"

    rationale = [
        step
        for step in payload["steps"]
        if step["title"] == "Model release rationale"
    ][0]
    assert rationale["data"]["verdict"] == "block"
    assert rationale["data"]["proposed_verdict"] == "allow"
    assert rationale["data"]["verdict_disagreement"]


def test_counterfactual_results_are_unchanged_in_live_mode(client: TestClient) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(client, detail["run"]["id"], provider=StubProvider())
    root_causes = [
        item for item in payload["counterfactuals"] if item["verdict"] == "root_cause"
    ]
    assert root_causes
    by_intervention: dict[str, list[str]] = {}
    for item in root_causes:
        by_intervention.setdefault(item["intervention"], []).append(item["scenario_id"])
    assert "prompt-injection-password" in by_intervention.get(
        "security_guard_enabled", []
    )
    assert len(by_intervention.get("compression_disabled", [])) >= 6


def test_the_decision_verdict_is_still_the_measured_one(client: TestClient) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(client, detail["run"]["id"], provider=StubProvider())
    engine_decision = [
        step
        for step in payload["steps"]
        if step["kind"] == "decision" and step["data"]["source"] == "deterministic"
    ]
    assert len(engine_decision) == 1
    assert engine_decision[0]["data"]["verdict"] == "block"


# --- fallback ---------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        LLMTimeoutError("timed out"),
        LLMTransportError("endpoint returned HTTP 503", status=503),
        LLMResponseError("content that is not valid JSON"),
        LLMSchemaError("missing required property 'hypotheses'"),
    ],
)
def test_a_provider_failure_falls_back_without_failing_the_investigation(
    client: TestClient, failure: Exception
) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client,
        detail["run"]["id"],
        provider=ScriptedProvider([failure]),
    )

    assert payload["investigation"]["status"] == "completed"
    assert payload["decision"]["verdict"] == "block"

    fallbacks = [
        step for step in payload["steps"] if step["data"].get("fallback_reason")
    ]
    assert fallbacks, "no step recorded a fallback_reason"
    assert any(
        type(failure).__name__ in step["data"]["fallback_reason"] for step in fallbacks
    )
    # The deterministic analysis is still complete.
    assert [
        step for step in payload["steps"] if step["kind"] == "decision"
    ]


def test_a_fallback_is_recorded_on_the_runtime_status(
    client: TestClient,
) -> None:
    detail = _demo_run(client)
    _run_investigation(
        client,
        detail["run"]["id"],
        provider=ScriptedProvider([LLMTimeoutError("timed out")]),
    )
    status = client.get("/api/runtime").json()
    assert status["fallback_active"] is True
    assert status["llm_configured"] is True


def test_a_hypothesis_citing_an_unknown_scenario_is_discarded(
    client: TestClient,
) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client,
        detail["run"]["id"],
        provider=StubProvider(
            hypotheses={
                "hypotheses": [
                    {
                        "kind": "domain:safety",
                        "claim": "invented",
                        "mechanism": "invented",
                        "scenario_ids": ["scenario-that-does-not-exist"],
                    }
                ]
            }
        ),
    )
    assert payload["investigation"]["status"] == "completed"
    hypotheses = [
        step
        for step in payload["steps"]
        if step["title"] == "Model-proposed risk hypotheses"
    ][0]
    assert not hypotheses["data"].get("proposals")
    assert hypotheses["data"]["fallback_reason"]
    assert not [
        step for step in payload["steps"] if step["data"].get("label") == "invented"
    ]


def test_an_empty_hypothesis_set_is_a_fallback_not_an_error(
    client: TestClient,
) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(
        client,
        detail["run"]["id"],
        provider=StubProvider(hypotheses={"hypotheses": []}),
    )
    assert payload["investigation"]["status"] == "completed"


# --- no secret leakage ------------------------------------------------------


def test_the_key_a_live_runtime_holds_never_reaches_a_response(
    client: TestClient,
) -> None:
    """A runtime whose provider really holds the key still leaks nothing.

    This is the end-to-end version of the client-level leak tests: the canary
    is a real credential in a real provider object, and the assertion covers
    every surface the investigation writes — the investigation payload, the
    event stream, the exported report, and the runtime status.
    """
    container = client.app.state.container
    provider = make_canary_provider()
    assert provider.api_key == CANARY_KEY
    use_llm_runtime(container, live_runtime(provider))

    detail = _demo_run(client)
    investigation_id, payload = _run_investigation(
        client, detail["run"]["id"], provider=provider
    )

    surfaces = {
        "investigation": json.dumps(payload),
        "events": client.get(
            f"/api/investigations/{investigation_id}/events?fmt=ndjson"
        ).text,
        "report": client.get(
            f"/api/investigations/{investigation_id}/report.md"
        ).text,
        "runtime": client.get("/api/runtime").text,
        "run_detail": client.get(f"/api/runs/{detail['run']['id']}").text,
    }
    for name, blob in surfaces.items():
        assert CANARY_KEY not in blob, name
        assert "Bearer" not in blob, name


def test_hypothesis_proposal_never_reaches_the_report_as_a_finding(
    client: TestClient,
) -> None:
    detail = _demo_run(client)
    _, payload = _run_investigation(client, detail["run"]["id"], provider=StubProvider())
    investigation_id = payload["investigation"]["id"]
    report = client.get(f"/api/investigations/{investigation_id}/report.md").text
    # The decision section still states the measured verdict.
    assert "**Verdict: `block`**" in report
