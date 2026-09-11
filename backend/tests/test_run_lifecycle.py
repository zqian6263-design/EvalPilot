"""The state machine: create -> start -> complete, plus failure and cancel."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from conftest import make_settings, start_and_wait, wait_for_run
from evalpilot.app import create_app
from evalpilot.planner import MAX_CASES


def test_run_progresses_through_expected_states(
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
    assert run["status"] == "queued"

    started = client.post(f"/api/runs/{run['id']}/start")
    assert started.status_code == 202
    assert started.json()["status"] == "queued"

    detail = wait_for_run(client, run["id"])
    assert detail["run"]["status"] == "completed"
    assert detail["run"]["completed_at"] is not None

    # Every case reached a terminal status, and the baseline is clean.
    statuses = {case["version"]: set() for case in detail["test_cases"]}
    for case in detail["test_cases"]:
        statuses[case["version"]].add(case["status"])
    assert statuses["baseline"] == {"passed"}
    assert "failed" in statuses["candidate"]


def test_run_transitions_are_recorded_in_the_event_log(
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
    start_and_wait(client, run["id"])

    response = client.get(f"/api/runs/{run['id']}/events?fmt=ndjson&follow=false")
    events = [
        json.loads(line) for line in response.text.splitlines() if line.strip()
    ]
    types = [event["type"] for event in events]

    assert types[0] == "run.started"
    assert types[-1] == "run.completed"
    assert types.count("task.created") == 1
    assert types.count("task.started") == 20
    assert types.count("task.completed") == 20
    assert types.count("evidence.created") == 20
    assert types.count("finding.created") >= 1

    run_started = events[0]
    assert run_started["data"]["baseline_version"] == "v1.0-baseline"
    # The event reports the number of *scenarios* planned, not raw case rows.
    assert run_started["data"]["planned_case_count"] == 10


def test_cancel_stops_an_in_flight_run(settings, project: dict) -> None:
    """With a non-zero step delay the run is still executing when cancelled."""
    slow = make_settings(settings.db_path.parent, step_delay=0.25)
    with TestClient(create_app(slow)) as slow_client:
        project_response = slow_client.post(
            "/api/projects", json={"name": "Slow KB QA", "scenario": "kb-qa"}
        ).json()
        run = slow_client.post(
            "/api/runs",
            json={
                "project_id": project_response["id"],
                "baseline_version": "a",
                "candidate_version": "b",
                "case_count": 10,
                "seed": 17,
            },
        ).json()
        slow_client.post(f"/api/runs/{run['id']}/start")

        # Let the runner enter the executing phase.
        time.sleep(0.5)
        assert slow_client.get(f"/api/runs/{run['id']}").json()["run"]["status"] in {
            "planning",
            "executing",
            "evaluating",
        }

        cancelled = slow_client.post(f"/api/runs/{run['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        # The background task notices and stops rather than completing.
        time.sleep(1.0)
        assert slow_client.get(f"/api/runs/{run['id']}").json()["run"]["status"] == (
            "cancelled"
        )

        events = [
            json.loads(line)
            for line in slow_client.get(
                f"/api/runs/{run['id']}/events?fmt=ndjson&follow=false"
            ).text.splitlines()
            if line.strip()
        ]
        assert events[-1]["data"].get("cancelled") is True
        assert "run.completed" not in {event["type"] for event in events}


def test_run_at_the_fixture_limit_completes(
    client: TestClient, project: dict
) -> None:
    """The largest supported plan executes cleanly."""
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
            "case_count": MAX_CASES,
            "seed": 1,
        },
    ).json()
    detail = start_and_wait(client, run["id"])
    assert detail["run"]["status"] == "completed"


def test_case_count_is_clamped_to_the_fixture_set(
    client: TestClient, project: dict
) -> None:
    """A ``case_count`` beyond the fixture set is clamped, never a 500."""
    run = client.post(
        "/api/runs",
        json={
            "project_id": project["id"],
            "baseline_version": "a",
            "candidate_version": "b",
            "case_count": MAX_CASES + 50,
            "seed": 2,
        },
    ).json()
    detail = start_and_wait(client, run["id"])
    assert detail["run"]["status"] == "completed"
    assert len(detail["test_cases"]) == MAX_CASES * 2


def test_seeded_runs_are_reproducible(client: TestClient, project: dict) -> None:
    payload = {
        "project_id": project["id"],
        "baseline_version": "a",
        "candidate_version": "b",
        "case_count": 10,
        "seed": 20260919,
    }
    first = client.post("/api/runs", json=payload).json()
    start_and_wait(client, first["id"])
    second = client.post("/api/runs", json=payload).json()
    start_and_wait(client, second["id"])

    def fingerprint(run_id: str) -> tuple:
        detail = client.get(f"/api/runs/{run_id}").json()
        report = client.get(f"/api/runs/{run_id}/report").json()
        return (
            [
                (case["title"], case["category"], case["difficulty"], case["status"])
                for case in detail["test_cases"]
            ],
            report["metrics"]["candidate_score"],
            report["metrics"]["regressed_scenarios"],
            [finding["title"] for finding in report["findings"]],
        )

    assert fingerprint(first["id"]) == fingerprint(second["id"])
