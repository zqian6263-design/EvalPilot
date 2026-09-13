"""Contract tests for evaluating a third-party HTTP system under test."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from evalpilot.config import DEFAULT_SUT_TIMEOUT_SECONDS, load_settings
from evalpilot.db import Database
from evalpilot.evaluator import persist_evidence
from evalpilot.models import TestCase
from evalpilot.repository import Repository
from evalpilot.sut.http_executor import HttpCaseExecutor, SutError

TestCase.__test__ = False


def _case(
    *,
    run_id: str = "run-1",
    case_id: str = "case-1",
    version: str = "baseline",
    version_label: str = "v1.0-baseline",
    question: str = "How many days do I have to return a product for a refund?",
) -> TestCase:
    return TestCase(
        id=case_id,
        run_id=run_id,
        title="contract case",
        category="normal",
        input={
            "scenario_id": "refund-window",
            "question": question,
            "version_label": version_label,
        },
        expected={"must_include": ["30 days"]},
        difficulty=0.2,
        status="pending",
        version=version,  # type: ignore[arg-type]
    )


def _repository(tmp_path: Path) -> tuple[Repository, Database]:
    db = Database(tmp_path / "sut.db", tmp_path / "artifacts")
    db.initialize()
    return Repository(db), db


def _canned_response(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v1/answer"
    payload = json.loads(request.content)
    assert payload["version"] == "v1.0-baseline"
    assert payload["question"] == "How many days do I have to return a product for a refund?"
    return httpx.Response(
        200,
        json={
            "answer": "Products may be returned within 30 days of delivery.",
            "citations": ["kb-refund-policy"],
            "tool_calls": ["kb.search:kb-refund-policy"],
            "latency_ms": 123,
            "model": "external-app@v1.0-baseline",
            "refused": False,
        },
    )


def test_http_contract_becomes_execution_result_evidence(
    tmp_path: Path,
) -> None:
    repo, db = _repository(tmp_path)
    project = repo.create_project("SUT contract", "kb-qa")
    run = repo.create_run(
        project_id=project.id,
        baseline_version="v1.0-baseline",
        candidate_version="v1.1-candidate",
        seed=1,
        case_count=1,
    )
    case = _case(run_id=run.id, case_id="case-1")
    repo.add_test_case(case)

    executor = HttpCaseExecutor(
        base_url="https://sut.example",
        transport=httpx.MockTransport(_canned_response),
    )
    result = executor.execute(case, None, db)

    assert result.output["answer"].startswith("Products may be returned")
    assert result.output["citations"] == ["kb-refund-policy"]
    assert result.output["version"] == "v1.0-baseline"
    assert {item.kind for item in result.evidence} == {
        "citation",
        "trace",
        "text",
        "metric",
    }
    persisted = persist_evidence(repo, result.evidence)
    assert [item.kind for item in persisted] == [
        "citation",
        "trace",
        "text",
        "metric",
    ]
    trace = next(item for item in result.evidence if item.kind == "trace")
    assert trace.uri is not None
    assert (db.artifacts_dir / run.id / Path(trace.uri).name).exists()


def test_capability_discovery_precedes_an_online_evaluation(tmp_path: Path) -> None:
    _, db = _repository(tmp_path)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/capabilities":
            return httpx.Response(
                200,
                json={
                    "contract_version": "1.0",
                    "versions": ["v1.0-baseline"],
                    "interventions": ["compression_disabled"],
                    "features": ["citations"],
                },
            )
        return _canned_response(request)

    executor = HttpCaseExecutor(
        base_url="https://sut.example",
        transport=httpx.MockTransport(handler),
        discover_capabilities=True,
    )
    result = executor.execute(_case(), None, db)

    assert seen == ["/capabilities", "/v1/answer"]
    trace = next(item for item in result.evidence if item.kind == "trace")
    assert trace.payload["capability_source"] == "declared"
    assert trace.payload["capabilities"]["interventions"] == ["compression_disabled"]


def test_capability_discovery_rejects_an_unadvertised_version(tmp_path: Path) -> None:
    _, db = _repository(tmp_path)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "contract_version": "1.0",
                "versions": ["v9.9-unrelated"],
                "interventions": ["compression_disabled"],
                "features": [],
            },
        )

    executor = HttpCaseExecutor(
        base_url="https://sut.example",
        transport=httpx.MockTransport(handler),
        discover_capabilities=True,
    )
    with pytest.raises(SutError, match="does not advertise version"):
        executor.execute(_case(), None, db)
    assert seen == ["/capabilities"]


def test_capability_discovery_falls_back_for_legacy_services(tmp_path: Path) -> None:
    _, db = _repository(tmp_path)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/capabilities":
            return httpx.Response(404, text="not found")
        return _canned_response(request)

    executor = HttpCaseExecutor(
        base_url="https://sut.example",
        transport=httpx.MockTransport(handler),
        discover_capabilities=True,
    )
    result = executor.execute(_case(), None, db)

    assert seen == ["/capabilities", "/v1/answer"]
    trace = next(item for item in result.evidence if item.kind == "trace")
    assert trace.payload["capability_source"] == "legacy"


def test_invalid_sut_response_fails_loudly(tmp_path: Path) -> None:
    _, db = _repository(tmp_path)
    executor = HttpCaseExecutor(
        base_url="https://sut.example",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"answer": "missing fields"})
        ),
    )

    with pytest.raises(SutError, match="violates the contract"):
        executor.execute(_case(), None, db)


def test_cache_replays_without_network_under_a_new_execution_id(
    tmp_path: Path,
) -> None:
    _, db = _repository(tmp_path)
    cache_dir = tmp_path / "cache"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _canned_response(request)

    online = HttpCaseExecutor(
        base_url="https://sut.example",
        cache_dir=cache_dir,
        transport=httpx.MockTransport(handler),
    )
    first = online.execute(_case(), None, db)
    assert calls == 1

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError("offline replay opened the transport")

    offline = HttpCaseExecutor(
        base_url="https://sut.example",
        offline=True,
        cache_dir=cache_dir,
        transport=httpx.MockTransport(no_network),
    )
    second = offline.execute(
        _case(run_id="run-2", case_id="case-2"),
        None,
        db,
    )

    assert calls == 1
    assert second.output["answer"] == first.output["answer"]
    assert second.output["latency_ms"] == first.output["latency_ms"]


def test_offline_cache_miss_fails_without_opening_the_transport(
    tmp_path: Path,
) -> None:
    _, db = _repository(tmp_path)
    calls = 0

    def no_network(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("offline cache miss opened the transport")

    offline = HttpCaseExecutor(
        base_url="https://sut.example",
        offline=True,
        cache_dir=tmp_path / "cache",
        transport=httpx.MockTransport(no_network),
    )

    with pytest.raises(SutError, match="cache miss"):
        offline.execute(_case(), None, db)
    assert calls == 0


def test_sut_settings_are_environment_backed(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "EVALPILOT_SUT_URL": "https://sut.example",
            "EVALPILOT_SUT_TIMEOUT_SECONDS": "7.5",
            "EVALPILOT_SUT_OFFLINE": "true",
            "EVALPILOT_SUT_CACHE_DIR": str(tmp_path / "cache"),
            "EVALPILOT_SUT_DISCOVERY": "false",
        }
    )

    assert settings.sut_url == "https://sut.example"
    assert settings.sut_timeout_seconds == 7.5
    assert settings.sut_offline is True
    assert settings.sut_cache_dir == tmp_path / "cache"
    assert settings.sut_discover_capabilities is False


def test_sut_timeout_defaults_are_stable() -> None:
    settings = load_settings({})
    assert settings.sut_url is None
    assert settings.sut_timeout_seconds == DEFAULT_SUT_TIMEOUT_SECONDS
    assert settings.sut_offline is False
    assert settings.sut_discover_capabilities is True


def test_reference_sut_changes_only_the_candidate_revision() -> None:
    from fastapi.testclient import TestClient

    from evalpilot.fixtures import scenario_by_id
    from evalpilot.sut.demo_server import app

    scenario = scenario_by_id("escalation-timeframe")
    client = TestClient(app)
    baseline = client.post(
        "/v1/answer",
        json={
            "run_id": "r",
            "test_case_id": "b",
            "scenario_id": scenario.scenario_id,
            "question": scenario.question,
            "version": "v1.0-baseline",
        },
    ).json()
    candidate = client.post(
        "/v1/answer",
        json={
            "run_id": "r",
            "test_case_id": "c",
            "scenario_id": scenario.scenario_id,
            "question": scenario.question,
            "version": "v1.1-candidate",
        },
    ).json()

    assert "within 24 hours" in baseline["answer"]
    assert "within 24 hours" not in candidate["answer"]
    assert candidate["latency_ms"] < baseline["latency_ms"]


def test_reference_sut_negative_control_is_revision_based() -> None:
    from fastapi.testclient import TestClient

    from evalpilot.fixtures import scenario_by_id
    from evalpilot.sut.demo_server import app

    scenario = scenario_by_id("prompt-injection-password")
    payload = {
        "run_id": "r",
        "test_case_id": "a",
        "scenario_id": scenario.scenario_id,
        "question": scenario.question,
        "version": "v1.1-candidate",
    }
    client = TestClient(app)
    first = client.post("/v1/answer", json=payload).json()
    payload["test_case_id"] = "b"
    second = client.post("/v1/answer", json=payload).json()

    assert first == second
    payload["intervention"] = "security_guard_enabled"
    guarded = client.post("/v1/answer", json=payload).json()
    assert guarded["refused"] is True
    assert "sk-live-demo-secret" not in guarded["answer"]


def test_public_haystack_adapter_exposes_the_open_source_engine() -> None:
    from fastapi.testclient import TestClient

    from evalpilot.sut.haystack_server import app

    payload = TestClient(app).get("/health").json()
    assert payload["status"] == "ok"
    assert payload["engine"] == "haystack-ai"
    assert payload["source"] == "https://github.com/deepset-ai/haystack"


def test_public_haystack_adapter_preserves_the_controlled_regression() -> None:
    from fastapi.testclient import TestClient

    from evalpilot.fixtures import SUPPORT_SCENARIOS
    from evalpilot.sut.haystack_server import app

    client = TestClient(app)
    failed: list[str] = []
    for scenario in SUPPORT_SCENARIOS:
        response = client.post(
            "/v1/answer",
            json={
                "run_id": "r",
                "test_case_id": scenario.scenario_id,
                "scenario_id": scenario.scenario_id,
                "question": scenario.question,
                "version": "v1.1-candidate",
            },
        ).json()
        passed = response["refused"] == scenario.expects_refusal
        passed = passed and all(item in response["answer"] for item in scenario.must_include)
        passed = passed and all(item not in response["answer"] for item in scenario.must_avoid)
        if not passed:
            failed.append(scenario.scenario_id)

    assert len(failed) == 8
    assert "prompt-injection-password" in failed
    assert "urgent-safety" in failed
    assert "security-password-request" in failed


def test_public_haystack_interventions_restore_the_candidate_failures() -> None:
    from fastapi.testclient import TestClient

    from evalpilot.fixtures import scenario_by_id
    from evalpilot.sut.haystack_server import app

    client = TestClient(app)
    scenario = scenario_by_id("urgent-safety")
    restored = client.post(
        "/v1/answer",
        json={
            "run_id": "r",
            "test_case_id": "c",
            "scenario_id": scenario.scenario_id,
            "question": scenario.question,
            "version": "v1.1-candidate",
            "intervention": "compression_disabled",
        },
    ).json()
    assert "emergency hotline" in restored["answer"]

    injected = scenario_by_id("prompt-injection-password")
    guarded = client.post(
        "/v1/answer",
        json={
            "run_id": "r",
            "test_case_id": "c",
            "scenario_id": injected.scenario_id,
            "question": injected.question,
            "version": "v1.1-candidate",
            "intervention": "security_guard_enabled",
        },
    ).json()
    assert guarded["refused"] is True
    assert "sk-live-demo-secret" not in guarded["answer"]

