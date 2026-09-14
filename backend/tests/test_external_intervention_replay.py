"""Custom, externally declared interventions must be measured, not predicted.

The counterfactual engine originally understood only its own ``Intervention``
enum members: reading ``target.intervention.executor_value`` raised for any other
name, the provider swallowed the error and returned the deterministic fallback,
and the investigation then reported a *predicted* score next to measured ones
without saying which was which. A service that declared its own intervention name
in ``GET /capabilities`` was therefore never replayed at all.

These tests drive the whole path in-process against the real onboarding template
over real HTTP, and pin the two facts that separate a measurement from a
prediction:

1. the service received a request carrying the custom intervention name, and
2. the reported score is the one that answer actually earned.

The built-in ``Intervention`` behaviour is pinned alongside it, so widening the
seam cannot quietly change the fixtures it was written for.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from evalpilot.app import create_app
from evalpilot.counterfactual import CounterfactualTarget, Intervention

from .conftest import make_settings, start_and_wait
from .uvicorn_server import serve_app

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_APP_PATH = ROOT / "integrations" / "sut_template" / "app.py"
TEMPLATE_WORKLOAD_PATH = ROOT / "integrations" / "sut_template" / "workload.json"

#: The template's own intervention name. It is deliberately absent from the
#: ``Intervention`` enum: an external SUT publishes its own vocabulary.
CUSTOM_INTERVENTION = "full_context_restored"

REGRESSED_SCENARIOS = (
    "credential-handling-policy",
    "escalation-deadline",
    "escalation-human-handoff",
    "refund-processing-time",
    "shipping-express-cutoff",
)

INVESTIGATION_TIMEOUT_SECONDS = 60.0


def _load_template():
    spec = importlib.util.spec_from_file_location("p5_template_for_replay", TEMPLATE_APP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def template():
    return _load_template()


def _trace_requests(detail: dict) -> list[dict]:
    return [
        item["payload"]["request"]
        for item in detail["evidence"]
        if item["kind"] == "trace" and (item.get("payload") or {}).get("request")
    ]


def _wait_for_investigation(client: TestClient, investigation_id: str) -> dict:
    import time

    deadline = time.time() + INVESTIGATION_TIMEOUT_SECONDS
    detail: dict = {}
    while time.time() < deadline:
        detail = client.get(f"/api/investigations/{investigation_id}").json()
        if detail["investigation"]["status"] in {"completed", "failed"}:
            return detail
        time.sleep(0.05)
    raise AssertionError(
        f"investigation {investigation_id} did not finish: {detail.get('investigation')}"
    )


def test_custom_intervention_is_replayed_against_the_service_and_measured(
    template, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serve_app(template.app) as base_url:
        monkeypatch.setenv("EVALPILOT_WORKLOAD_FILE", str(TEMPLATE_WORKLOAD_PATH))
        settings = make_settings(
            tmp_path,
            sut_url=base_url,
            sut_discover_capabilities=True,
            sut_cache_dir=tmp_path / "cache",
        )
        with TestClient(create_app(settings)) as client:
            project = client.post(
                "/api/projects", json={"name": "custom intervention", "scenario": "kb-qa"}
            ).json()
            run = client.post(
                "/api/runs",
                json={
                    "project_id": project["id"],
                    "baseline_version": "v1.0-baseline",
                    "candidate_version": "v1.1-candidate",
                    "seed": 20260919,
                    "case_count": 8,
                },
            ).json()
            start_and_wait(client, run["id"])

            report = client.get(f"/api/runs/{run['id']}/report").json()
            assert report["metrics"]["regression_confirmed"] is True

            investigation = client.post(
                "/api/investigations",
                json={
                    "run_id": run["id"],
                    "objective": "Confirm the root cause of every regressed scenario.",
                },
            ).json()
            client.post(f"/api/investigations/{investigation['id']}/start")
            detail = _wait_for_investigation(client, investigation["id"])

            assert detail["investigation"]["status"] == "completed"
            counterfactuals = detail["counterfactuals"]
            assert len(counterfactuals) == len(REGRESSED_SCENARIOS)
            assert {item["intervention"] for item in counterfactuals} == {CUSTOM_INTERVENTION}
            assert {item["verdict"] for item in counterfactuals} == {"root_cause"}

            # Measurement, not prediction: the service was actually called with
            # the custom intervention, once per replayed scenario.
            run_detail = client.get(f"/api/runs/{run['id']}").json()
            replay_requests = [
                request
                for request in _trace_requests(run_detail)
                if request["intervention"] == CUSTOM_INTERVENTION
            ]
            assert len(replay_requests) == len(REGRESSED_SCENARIOS)
            assert {request["scenario_id"] for request in replay_requests} == set(
                REGRESSED_SCENARIOS
            )

            # ... and the score is the one the measured answer earned. The
            # deterministic fallback reports 0.95 here; the replayed answer is a
            # full pass.
            assert {item["counterfactual_score"] for item in counterfactuals} == {1.0}


def test_builtin_intervention_names_still_resolve_to_enum_members() -> None:
    from evalpilot.counterfactual import coerce_intervention

    assert coerce_intervention("compression_disabled") is Intervention.COMPRESSION_DISABLED
    assert coerce_intervention("none") is Intervention.NONE
    assert coerce_intervention(Intervention.SECURITY_GUARD_ENABLED) is (
        Intervention.SECURITY_GUARD_ENABLED
    )


def test_target_keeps_an_external_intervention_name() -> None:
    target = CounterfactualTarget(
        scenario_id="s",
        run_id="r",
        test_case_id="c",
        intervention=CUSTOM_INTERVENTION,
    )
    assert target.intervention == CUSTOM_INTERVENTION
    assert not isinstance(target.intervention, Intervention)


def test_blank_intervention_is_still_rejected() -> None:
    """A blank name must fail: silently replaying without an intervention would
    report ``no_effect`` for a hypothesis that was never tested."""

    with pytest.raises(ValidationError):
        CounterfactualTarget(
            scenario_id="s",
            run_id="r",
            test_case_id="c",
            intervention="   ",
        )


def test_intervention_parse_still_rejects_names_outside_the_allowlist() -> None:
    """The executable allowlist that gates model-proposed interventions is
    unchanged: widening the replay seam must not widen that gate."""

    with pytest.raises(ValueError, match="Unknown intervention"):
        Intervention.parse(CUSTOM_INTERVENTION)


def test_template_declares_the_custom_intervention_in_capabilities(template) -> None:
    capabilities = template.capabilities()
    assert CUSTOM_INTERVENTION in capabilities["interventions"]
    assert CUSTOM_INTERVENTION not in {member.value for member in Intervention}


def test_template_workload_uses_the_custom_intervention() -> None:
    workload = json.loads(TEMPLATE_WORKLOAD_PATH.read_text(encoding="utf-8"))
    regressed = [
        scenario
        for scenario in workload["scenarios"]
        if scenario.get("suggested_intervention")
    ]
    assert {scenario["suggested_intervention"] for scenario in regressed} == {
        CUSTOM_INTERVENTION
    }
    assert {scenario["scenario_id"] for scenario in regressed} == set(REGRESSED_SCENARIOS)
