"""Contract tests for the HTTP surface defined in ``docs/INTERFACES.md``."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from .conftest import start_and_wait, wait_for_run


def test_health_returns_status_and_version(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_project_crud(client: TestClient) -> None:
    created = client.post(
        "/api/projects", json={"name": "KB QA", "scenario": "kb-qa"}
    )
    assert created.status_code == 201
    project = created.json()
    assert set(project) == {"id", "name", "scenario", "created_at"}

    fetched = client.get(f"/api/projects/{project['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == project

    listing = client.get("/api/projects").json()
    assert [item["id"] for item in listing] == [project["id"]]


def test_unknown_project_returns_404(client: TestClient) -> None:
    assert client.get("/api/projects/does-not-exist").status_code == 404


def test_run_creation_matches_contract_fields(
    client: TestClient, project: dict
) -> None:
    response = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "v1.0-baseline",
            "candidate_version": "v1.1-candidate",
            "case_count": 10,
            "seed": 20260919,
        },
    )
    assert response.status_code == 201
    run = response.json()
    assert set(run) == {
        "id",
        "project_id",
        "baseline_version",
        "candidate_version",
        "status",
        "case_count",
        "created_at",
        "completed_at",
    }
    assert run["status"] == "queued"
    assert run["completed_at"] is None


def test_run_creation_rejects_unknown_project(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={
            "project_id": "nope",
            "baseline_version": "a",
            "candidate_version": "b",
        },
    )
    assert response.status_code == 404


def test_run_creation_rejects_invalid_case_count(
    client: TestClient, project: dict
) -> None:
    response = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
            "case_count": 0,
        },
    )
    assert response.status_code == 422


def test_run_detail_exposes_cases_evidence_and_counts(
    client: TestClient, project: dict
) -> None:
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "v1.0-baseline",
            "candidate_version": "v1.1-candidate",
            "case_count": 10,
            "seed": 20260919,
        },
    ).json()

    detail = start_and_wait(client, run["id"])
    assert detail["run"]["status"] == "completed"
    assert detail["run"]["completed_at"] is not None

    # 10 scenarios, executed once per version.
    assert len(detail["test_cases"]) == 20
    assert detail["evidence_count"] == len(detail["evidence"])
    assert detail["evidence_count"] > 0
    assert detail["event_count"] > 0

    case_fields = {
        "id",
        "run_id",
        "title",
        "category",
        "input",
        "expected",
        "difficulty",
        "status",
        "version",
        "output",
    }
    assert all(set(case) == case_fields for case in detail["test_cases"])
    assert {case["version"] for case in detail["test_cases"]} == {
        "baseline",
        "candidate",
    }
    assert {case["status"] for case in detail["test_cases"]} <= {"passed", "failed"}


def test_report_unavailable_before_completion(client: TestClient, project: dict) -> None:
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
        },
    ).json()
    response = client.get(f"/api/runs/{run['id']}/report")
    assert response.status_code == 409


def test_release_gate_turns_a_confirmed_regression_into_a_block(
    client: TestClient, project: dict
) -> None:
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
    start_and_wait(client, run["id"])

    gate = client.get(f"/api/runs/{run['id']}/gate")
    assert gate.status_code == 200
    payload = gate.json()
    assert payload["decision"] == "block"
    assert payload["exit_code"] == 2
    assert payload["regression_confirmed"] is True
    assert payload["reasons"] == ["regression_confirmed"]
    assert payload["report_url"].endswith(f"/api/runs/{run['id']}/report")


def test_release_gate_is_unavailable_before_completion(
    client: TestClient, project: dict
) -> None:
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
        },
    ).json()
    assert client.get(f"/api/runs/{run['id']}/gate").status_code == 409


def test_release_gate_unknown_run_returns_404(client: TestClient) -> None:
    assert client.get("/api/runs/does-not-exist/gate").status_code == 404

def test_report_unknown_run_returns_404(client: TestClient) -> None:
    assert client.get("/api/runs/does-not-exist/report").status_code == 404


def test_start_requires_queued_status(client: TestClient, project: dict) -> None:
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
            "case_count": 4,
            "seed": 7,
        },
    ).json()

    assert client.post(f"/api/runs/{run['id']}/start").status_code == 202
    wait_for_run(client, run["id"])
    assert client.post(f"/api/runs/{run['id']}/start").status_code == 409


def test_start_unknown_run_returns_404(client: TestClient) -> None:
    assert client.post("/api/runs/does-not-exist/start").status_code == 404


def test_events_are_sequenced_and_typed(client: TestClient, project: dict) -> None:
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
            "case_count": 10,
            "seed": 20260919,
        },
    ).json()
    start_and_wait(client, run["id"])

    response = client.get(f"/api/runs/{run['id']}/events?fmt=ndjson&follow=false")
    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert lines

    events = [json.loads(line) for line in lines]
    assert [event["sequence"] for event in events] == list(
        range(1, len(events) + 1)
    )
    assert all(event["run_id"] == run["id"] for event in events)
    assert {event["type"] for event in events} <= {
        "run.started",
        "task.created",
        "task.started",
        "evidence.created",
        "task.completed",
        "finding.created",
        "run.completed",
        "run.failed",
    }
    assert events[0]["type"] == "run.started"
    assert events[-1]["type"] == "run.completed"


def test_events_alias_defaults_to_latest_run(client: TestClient, project: dict) -> None:
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
            "case_count": 4,
            "seed": 3,
        },
    ).json()
    start_and_wait(client, run["id"])

    response = client.get("/api/events?fmt=ndjson&follow=false")
    assert response.status_code == 200
    assert all(
        line.strip() for line in response.text.splitlines() if line.strip()
    )


def test_events_unknown_run_returns_404(client: TestClient) -> None:
    assert client.get("/api/runs/nope/events?fmt=ndjson").status_code == 404


def test_cancel_marks_run_cancelled(client: TestClient, project: dict) -> None:
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
            "case_count": 4,
            "seed": 11,
        },
    ).json()

    response = client.post(f"/api/runs/{run['id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # A cancelled run never starts.
    assert client.post(f"/api/runs/{run['id']}/start").status_code == 409


def test_cancel_completed_run_conflicts(client: TestClient, project: dict) -> None:
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
            "case_count": 4,
            "seed": 13,
        },
    ).json()
    start_and_wait(client, run["id"])
    assert client.post(f"/api/runs/{run['id']}/cancel").status_code == 409


def test_cancel_unknown_run_returns_404(client: TestClient) -> None:
    assert client.post("/api/runs/nope/cancel").status_code == 404


def test_openapi_schema_includes_all_contract_paths(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/health",
        "/api/projects",
        "/api/projects/{project_id}",
        "/api/runs",
        "/api/runs/{run_id}",
        "/api/runs/{run_id}/start",
        "/api/runs/{run_id}/cancel",
        "/api/runs/{run_id}/report",
        "/api/runs/{run_id}/gate",
        "/api/demo/seed",
    ):
        assert path in paths, f"{path} missing from OpenAPI schema"
    # The event stream is published on both the frozen path and the alias.
    assert "/api/runs/{run_id}/events" in paths
    assert "/api/events" in paths

