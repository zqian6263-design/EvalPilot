"""The seeded demo: determinism, regression detection, evidence, and report."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from conftest import start_and_wait
from evalpilot.demo import (
    DEMO_BASELINE_VERSION,
    DEMO_CANDIDATE_VERSION,
    DEMO_CASE_COUNT,
    DEMO_PROJECT_NAME,
    DEMO_SCENARIO,
    DEMO_SEED,
    demo_metadata,
    ensure_demo_project,
    scripted_regressions,
)
from evalpilot.models import Report, RunDetail


def test_demo_seed_endpoint_is_side_effect_free(client: TestClient) -> None:
    before = client.get("/api/projects").json()
    response = client.get("/api/demo/seed")
    assert response.status_code == 200

    payload = response.json()
    assert payload["seed"] == DEMO_SEED
    assert payload["case_count"] == DEMO_CASE_COUNT
    assert payload["deterministic"] is True
    assert payload["external_services_required"] == []
    assert payload["baseline_version"] == DEMO_BASELINE_VERSION
    assert payload["candidate_version"] == DEMO_CANDIDATE_VERSION
    assert payload["project"]["name"] == DEMO_PROJECT_NAME
    assert payload["scenario"] == DEMO_SCENARIO
    assert len(payload["scenarios"]) == DEMO_CASE_COUNT
    assert set(payload["scripted_regressions"]) == set(scripted_regressions())

    # No side effects: the project list is untouched and no runs were created.
    assert client.get("/api/projects").json() == before
    assert client.get("/api/runs").json() == []


def test_demo_metadata_is_pure(container) -> None:
    """Calling the metadata builder never writes to the database."""
    assert container.repo.list_projects() == []
    assert container.repo.list_runs() == []
    demo_metadata()
    demo_metadata()
    assert container.repo.list_projects() == []
    assert container.repo.list_runs() == []


def test_demo_metadata_declares_defects_matching_scripted_regressions() -> None:
    metadata = demo_metadata()
    assert set(metadata["defects"]) == set(metadata["scripted_regressions"])
    for scenario_id, defect in metadata["defects"].items():
        assert defect["kind"] in {
            "dropped_required_content",
            "disclosed_forbidden_content",
        }
        assert defect["detail"], f"{scenario_id} defect has no detail"


def test_seeded_demo_run_detects_the_regression(client: TestClient) -> None:
    container = client.app.state.container
    project, run = ensure_demo_project(container.repo, container.settings)
    assert project.name == DEMO_PROJECT_NAME
    assert run is not None

    detail = start_and_wait(client, run.id)
    assert detail["run"]["status"] == "completed"

    report = client.get(f"/api/runs/{run.id}/report").json()
    assert report["metrics"]["regression_detected"] is True

    expected = set(scripted_regressions())
    detected = set(report["metrics"]["regressed_scenarios"])
    assert expected <= detected, f"undetected regressions: {expected - detected}"

    # The controls prove the drop is not just a harder test set.
    assert len(report["metrics"]["control_scenarios"]) >= 1
    assert report["metrics"]["baseline_pass_rate"] == 1.0
    assert report["metrics"]["candidate_pass_rate"] < 1.0


def test_report_summary_explains_the_regression(client: TestClient) -> None:
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    start_and_wait(client, run.id)

    report = client.get(f"/api/runs/{run.id}/report").json()
    summary = report["summary"]

    assert "regressed" in summary
    assert "control" in summary
    # Every regressed scenario is named so the reader does not need raw logs.
    for scenario_id in report["metrics"]["regressed_scenarios"]:
        assert scenario_id in summary


def test_report_matches_the_frozen_contract(client: TestClient) -> None:
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    start_and_wait(client, run.id)

    payload = client.get(f"/api/runs/{run.id}/report").json()
    report = Report.model_validate(payload)
    assert report.run_id == run.id
    assert report.summary
    assert report.findings

    # Round-trip through the frozen model, not just the JSON shape.
    assert report.model_dump(mode="json")["findings"] == payload["findings"]


def test_every_finding_links_to_evidence_created_during_the_run(
    client: TestClient,
) -> None:
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    detail = start_and_wait(client, run.id)

    report = client.get(f"/api/runs/{run.id}/report").json()
    known_evidence = {item["id"] for item in detail["evidence"]}
    known_cases = {case["id"] for case in detail["test_cases"]}

    assert report["findings"], "the seeded demo must produce findings"
    for finding in report["findings"]:
        assert finding["evidence_ids"], f"finding {finding['title']} links no evidence"
        assert set(finding["evidence_ids"]) <= known_evidence
        assert 0.0 <= finding["confidence"] <= 1.0
        assert finding["severity"] in {
            "info",
            "low",
            "medium",
            "high",
            "critical",
        }
        if finding["test_case_id"] is not None:
            assert finding["test_case_id"] in known_cases


def test_evidence_kinds_and_artifact_uris(client: TestClient) -> None:
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    detail = start_and_wait(client, run.id)

    kinds = {item["kind"] for item in detail["evidence"]}
    assert {"text", "citation", "trace", "metric"} <= kinds

    traces = [item for item in detail["evidence"] if item["kind"] == "trace"]
    assert traces
    for trace in traces:
        assert trace["uri"] and trace["uri"].startswith(f"data/artifacts/{run.id}/")
        # The artifact is really on disk, and it is real JSON.
        path = container.settings.artifacts_dir / run.id / trace["uri"].split("/")[-1]
        json.loads(path.read_text(encoding="utf-8"))

    # Evidence never stores credentials in a payload.
    serialized = json.dumps(detail["evidence"])
    assert "EVALPILOT_LLM_API_KEY" not in serialized


def test_evidence_rows_carry_the_frozen_fields(client: TestClient) -> None:
    container = client.app.state.container
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None
    detail = RunDetail.model_validate(start_and_wait(client, run.id))

    for item in detail.evidence:
        assert item.run_id == run.id
        assert item.test_case_id
        assert isinstance(item.payload, dict)
        assert item.created_at.tzinfo is not None


def test_demo_rerun_creates_a_new_run_and_is_reproducible(client: TestClient) -> None:
    """Letting the demo run again yields a new run with byte-identical results."""
    container = client.app.state.container

    def execute_once() -> tuple[str, tuple]:
        _, run = ensure_demo_project(container.repo, container.settings)
        assert run is not None
        # A completed demo run is not restarted in place.
        if run.status.value != "queued":
            run = container.repo.create_run(
                project_id=run.project_id,
                baseline_version=run.baseline_version,
                candidate_version=run.candidate_version,
                seed=DEMO_SEED,
                case_count=DEMO_CASE_COUNT,
            )
        start_and_wait(client, run.id)
        report = client.get(f"/api/runs/{run.id}/report").json()
        detail = client.get(f"/api/runs/{run.id}").json()
        return run.id, (
            report["metrics"]["candidate_score"],
            report["metrics"]["baseline_score"],
            report["metrics"]["regressed_scenarios"],
            [finding["title"] for finding in report["findings"]],
            [
                (case["title"], case["status"], case["difficulty"])
                for case in detail["test_cases"]
            ],
            report["summary"],
        )

    first_id, first = execute_once()
    second_id, second = execute_once()

    assert first_id != second_id, "each demo run must be its own run record"
    assert first == second


def test_ensure_demo_project_is_idempotent(client: TestClient) -> None:
    """Re-seeding reuses the project instead of duplicating it."""
    container = client.app.state.container
    project, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None

    again_project, again_run = ensure_demo_project(container.repo, container.settings)
    assert again_project.id == project.id
    assert again_run is not None and again_run.id == run.id

    projects = client.get("/api/projects").json()
    assert [item["id"] for item in projects] == [project.id]
    runs = client.get("/api/runs").json()
    assert len(runs) == 1
