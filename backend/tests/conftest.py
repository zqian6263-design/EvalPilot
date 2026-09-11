"""Shared pytest fixtures.

Tests run against a temporary SQLite file so they never touch the developer's
``backend/data`` directory, and with ``step_delay=0`` so runs finish promptly.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evalpilot.app import create_app
from evalpilot.config import Settings
from evalpilot.container import Container, build_container


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "db_path": tmp_path / "evalpilot.db",
        "artifacts_dir": tmp_path / "artifacts",
        "llm_base_url": None,
        "llm_api_key": None,
        "llm_model": None,
        "enable_python_tool": False,
        "demo_mode": True,
        "step_delay": 0.0,
        "version": "0.1.0",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def container(settings: Settings) -> Container:
    return build_container(settings)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def project(client: TestClient) -> dict:
    response = client.post(
        "/api/projects",
        json={"name": "Fixture KB QA", "scenario": "kb-qa"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_run(client: TestClient, run_id: str, timeout: float = 60.0) -> dict:
    """Poll ``GET /runs/{id}`` until the run leaves the non-terminal states."""
    deadline = time.time() + timeout
    detail: dict = {}
    while time.time() < deadline:
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["run"]["status"] in {"completed", "failed", "cancelled"}:
            return detail
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout}s: {detail}")


def start_and_wait(client: TestClient, run_id: str, timeout: float = 60.0) -> dict:
    response = client.post(f"/api/runs/{run_id}/start")
    assert response.status_code == 202, response.text
    return wait_for_run(client, run_id, timeout)
