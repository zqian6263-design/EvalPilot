"""A browser counterfactual replay must be executed and measured.

The P3 acceptance record claimed three browser root causes "confirmed through
browser counterfactual replay", but the persisted run had no evidence row whose
request carried an intervention and the experiments' rationales read "is
predicted to restore ...". The replay never ran. Two defects caused that, and
neither is about the browser tool itself:

1. ``BrowserCaseExecutor.execute`` writes its screenshot through
   ``db.run_artifact_dir(run_id)``, and neither reading source implemented it, so
   the replay raised before the browser was ever launched; and
2. the replay engine's default registry has the browser tool disabled, so even
   with an artifact directory the ``browser_run`` invocation would be refused.

The provider catches every exception from the engine and falls back to the
deterministic predictor, which is why both defects were invisible in the API.

These tests drive the real path: a real Chromium page served over real HTTP, the
real composite executor, the real repository-backed reading source, and a real
tool registry. They fail if the replay falls back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from evalpilot.browser_tool import find_browser_executable
from evalpilot.config import Settings
from evalpilot.container import build_container
from evalpilot.counterfactual import CounterfactualEngine
from evalpilot.counterfactual.reading import InMemoryReadingSource
from evalpilot.db import Database
from evalpilot.executor import execute_case
from evalpilot.investigation.engine_provider import (
    EngineCounterfactualProvider,
    RepositoryReadingSource,
)
from evalpilot.investigation.providers import CounterfactualRequest
from evalpilot.models import TestCase
from evalpilot.repository import Repository
from evalpilot.sut.browser_executor import BrowserCaseExecutor, CompositeCaseExecutor
from evalpilot.tools import ToolPolicy, ToolRegistry

from .conftest import make_settings
from .uvicorn_server import serve_app

TestCase.__test__ = False

SCENARIO_ID = "tenant-metadata-overwrite"
INTERVENTION = "identity_metadata_stripped"
QUESTION = "Can metadata move this memory to another tenant?"
FIXED_MARKER = "foreign_visible=false"
BROKEN_MARKER = "foreign_visible=true"


def _page_app() -> FastAPI:
    """A page whose rendered answer depends on the intervention it is given."""

    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def page(request: Request) -> str:
        fixed = request.query_params.get("intervention") == INTERVENTION
        answer = (
            f"tenant=owner; owner_visible=true; {FIXED_MARKER}"
            if fixed
            else f"tenant=owner; owner_visible=true; {BROKEN_MARKER}"
        )
        return f"<html><body><div id='result'>{answer}</div></body></html>"

    return app


def _expected() -> dict:
    return {
        "expected_doc_ids": ["mem0-identity-scope"],
        "must_include": [FIXED_MARKER],
        "must_avoid": [BROKEN_MARKER],
        "expects_refusal": False,
    }


def _browser_actions() -> list[dict]:
    return [
        {"action": "wait_for_text", "text": "tenant=owner"},
        {"action": "extract_text", "selector": "#result", "name": "answer"},
    ]


def _write_workload(path: Path, base_url: str) -> Path:
    payload = {
        "workload_id": "browser-replay-unit",
        "baseline_version": "mem0ai-3.1.1",
        "candidate_version": "mem0ai-3.1.0",
        "scenarios": [
            {
                "scenario_id": SCENARIO_ID,
                "question": QUESTION,
                "category": "adversarial",
                "difficulty": 0.8,
                "expected_doc_ids": ["mem0-identity-scope"],
                "must_include": [FIXED_MARKER],
                "must_avoid": [BROKEN_MARKER],
                "suggested_intervention": INTERVENTION,
                "browser_url": f"{base_url}/?version={{{{version}}}}&intervention={{{{intervention}}}}",
                "browser_actions": _browser_actions(),
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _repository(tmp_path: Path) -> tuple[Repository, Database]:
    db = Database(tmp_path / "browser-replay.db", tmp_path / "artifacts")
    db.initialize()
    return Repository(db), db


def _policy(tmp_path: Path) -> ToolPolicy:
    return ToolPolicy(
        browser_enabled=True,
        browser_allowed_hosts=("127.0.0.1",),
        browser_screenshot_root=tmp_path / "artifacts",
        browser_executable_path=find_browser_executable(None),
        browser_headless=True,
    )


def _browser_provider(repo: Repository, tmp_path: Path) -> EngineCounterfactualProvider:
    """The production wiring, with the browser-enabled replay registry."""

    policy = _policy(tmp_path)
    registry = ToolRegistry(enable_python=False, policy=policy)
    executor = CompositeCaseExecutor(
        fallback=execute_case,
        browser=BrowserCaseExecutor(policy=policy, target_url=None),
    ).__call__
    engine = CounterfactualEngine(
        source=RepositoryReadingSource(repo),
        registry=registry,
        executor=executor,
    )
    return EngineCounterfactualProvider(repo=repo, engine=engine, executor=executor)


def _run_and_case(
    repo: Repository,
    *,
    base_url: str,
) -> tuple[str, TestCase]:
    project = repo.create_project("browser replay", "mem0-browser")
    run = repo.create_run(
        project_id=project.id,
        baseline_version="mem0ai-3.1.1",
        candidate_version="mem0ai-3.1.0",
        seed=20260919,
        case_count=1,
    )
    case = TestCase(
        id="case-browser-1",
        run_id=run.id,
        title=f"{SCENARIO_ID} [candidate]",
        category="adversarial",
        input={
            "scenario_id": SCENARIO_ID,
            "question": QUESTION,
            "version_label": "mem0ai-3.1.0",
            "browser_url": f"{base_url}/?version={{{{version}}}}&intervention={{{{intervention}}}}",
            "browser_actions": _browser_actions(),
        },
        expected=_expected(),
        difficulty=0.8,
        status="passed",
        version="candidate",
    )
    repo.add_test_case(case)
    return run.id, case


def test_repository_reading_source_exposes_the_run_artifact_directory(
    tmp_path: Path,
) -> None:
    repo, db = _repository(tmp_path)
    source = RepositoryReadingSource(repo)

    artifact_dir = source.run_artifact_dir("run-1")

    assert artifact_dir == db.run_artifact_dir("run-1")
    assert artifact_dir.is_dir()


def test_in_memory_reading_source_exposes_an_artifact_directory(tmp_path: Path) -> None:
    source = InMemoryReadingSource(artifact_root=tmp_path / "artifacts")

    artifact_dir = source.run_artifact_dir("run-1")

    assert artifact_dir == tmp_path / "artifacts" / "run-1"
    assert artifact_dir.is_dir()
    assert source.run_artifact_dir("run-1") == artifact_dir


def test_browser_replay_is_measured_not_predicted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serve_app(_page_app()) as base_url:
        workload = _write_workload(tmp_path / "workload.json", base_url)
        monkeypatch.setenv("EVALPILOT_WORKLOAD_FILE", str(workload))
        repo, db = _repository(tmp_path)
        run_id, case = _run_and_case(repo, base_url=base_url)
        provider = _browser_provider(repo, tmp_path)

        attempts = provider.attempt(
            CounterfactualRequest(
                scenario_id=SCENARIO_ID,
                category="adversarial",
                question=QUESTION,
                original_score=0.0,
                run_id=run_id,
                test_case_id=case.id,
                missing_facts=(FIXED_MARKER,),
                evidence_ids=(),
                failure_kind="missing_fact",
                suggested_intervention=INTERVENTION,
            )
        )

    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.verdict == "root_cause"
    assert attempt.intervention == INTERVENTION
    # The engine's wording, never the deterministic fallback's.
    assert attempt.rationale.startswith("Replayed "), attempt.rationale
    assert "predicted" not in attempt.rationale.lower(), attempt.rationale
    # Measured check-suite scores: the original arm fails both checks, the
    # replayed arm passes both. The fallback would have reported 0.0 to 0.9.
    assert attempt.original_score == 0.0
    assert attempt.counterfactual_score == 1.0

    evidence = repo.list_evidence(run_id)
    by_id = {item.id: item for item in evidence}
    screenshots = [item for item in evidence if item.kind == "screenshot"]
    traces = [item for item in evidence if item.kind == "trace"]
    assert len(screenshots) == 2, "both arms must persist a real browser screenshot"
    assert traces, "the replayed arm must persist its browser action trace"

    for item in screenshots:
        assert item.uri, item
        # Evidence stores a repository-relative URI; the bytes must be on disk.
        path = db.artifacts_dir / run_id / Path(item.uri).name
        assert path.is_file(), path
        assert path.stat().st_size > 100, path
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", path

    assert any(item.payload.get("actions") for item in traces), traces

    # The evidence itself must say which intervention produced it, otherwise a
    # browser replay is indistinguishable from an ordinary execution.
    replay_traces = [
        item
        for item in traces
        if (item.payload.get("request") or {}).get("intervention") == INTERVENTION
    ]
    assert len(replay_traces) == 1, [item.payload.get("request") for item in traces]

    # The experiment cites the replayed arm's own browser evidence, which is what
    # makes the score re-checkable rather than merely reported.
    cited = [by_id[evidence_id] for evidence_id in attempt.evidence_ids if evidence_id in by_id]
    assert cited, attempt.evidence_ids
    assert any(item.kind == "screenshot" for item in cited), [item.kind for item in cited]
    assert any(
        item.kind == "trace" and item.payload.get("actions") for item in cited
    ), [item.kind for item in cited]

    # The original arm's measured score is persisted next to its condition.
    original_rows = [
        item
        for item in evidence
        if isinstance(item.payload, dict) and item.payload.get("condition") == "original"
    ]
    assert original_rows, "the original arm must persist its own measured score"
    assert original_rows[0].payload["score"] == 0.0


def test_container_wires_a_browser_capable_replay_registry(tmp_path: Path) -> None:
    """The production wiring must let a browser replay invoke browser_run."""

    settings = make_settings(
        tmp_path,
        browser_enabled=True,
        browser_allowed_hosts=("127.0.0.1",),
        browser_screenshot_dir=tmp_path / "artifacts",
        browser_executable_path=find_browser_executable(None),
    )
    container = build_container(settings)

    provider = container.investigation_runner.provider
    available = provider.engine.registry.available()

    assert "browser_run" in available
    # The security property is unchanged: a replay still cannot run Python.
    assert "python_run" not in available


def test_container_leaves_the_replay_registry_without_browser_by_default(
    tmp_path: Path,
) -> None:
    settings: Settings = make_settings(tmp_path)
    container = build_container(settings)

    available = container.investigation_runner.provider.engine.registry.available()

    assert "browser_run" not in available
    assert "python_run" not in available
