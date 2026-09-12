"""``GET /api/runtime``: the mode, the model, the tools — and never the key.

This is the endpoint an operator checks after setting ``EVALPILOT_LLM_MODE``,
so it has to be accurate in both directions: it must not claim a model is
configured when it is not, and it must not claim a tool is registered when the
registry would refuse it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from evalpilot.app import create_app
from evalpilot.config import Settings, load_settings

from .llm_fakes import CANARY_KEY

EXPECTED_KEYS = {
    "mode",
    "llm_configured",
    "model",
    "base_url_host",
    "fallback_active",
    "tools",
}


def _client(tmp_path, **overrides) -> TestClient:
    base = {
        "db_path": tmp_path / "runtime.db",
        "artifacts_dir": tmp_path / "artifacts",
        "llm_base_url": None,
        "llm_api_key": None,
        "llm_model": None,
        "enable_python_tool": False,
        "demo_mode": True,
        "step_delay": 0.0,
        "version": "0.1.0",
        "llm_mode": "deterministic",
        "llm_timeout_seconds": 45.0,
    }
    base.update(overrides)
    return TestClient(create_app(Settings(**base)))  # type: ignore[arg-type]


def test_deterministic_mode_reports_no_model(tmp_path) -> None:
    with _client(tmp_path) as client:
        payload = client.get("/api/runtime").json()
    assert set(payload) == EXPECTED_KEYS
    assert payload == {
        "mode": "deterministic",
        "llm_configured": False,
        "model": None,
        "base_url_host": None,
        "fallback_active": False,
        "tools": ["kb_search"],
    }


def test_live_mode_reports_the_model_and_host(tmp_path) -> None:
    with _client(
        tmp_path,
        llm_mode="live",
        llm_base_url="https://api.deepseek.com",
        llm_api_key=CANARY_KEY,
        llm_model="deepseek-v4-pro",
    ) as client:
        response = client.get("/api/runtime")
    payload = response.json()
    assert payload["mode"] == "live"
    assert payload["llm_configured"] is True
    assert payload["model"] == "deepseek-v4-pro"
    assert payload["base_url_host"] == "api.deepseek.com"
    assert payload["fallback_active"] is False


def test_live_mode_with_an_incomplete_key_reports_it_is_not_configured(
    tmp_path,
) -> None:
    with _client(
        tmp_path,
        llm_mode="live",
        llm_base_url="https://api.deepseek.com",
        llm_model="deepseek-v4-pro",
    ) as client:
        payload = client.get("/api/runtime").json()
    assert payload["mode"] == "live"
    assert payload["llm_configured"] is False
    # No provider means no host to report: the endpoint does not echo a URL for
    # a mode that will never call it.
    assert payload["base_url_host"] is None


def test_the_endpoint_never_returns_the_api_key(tmp_path) -> None:
    with _client(
        tmp_path,
        llm_mode="live",
        llm_base_url="https://api.deepseek.com",
        llm_api_key=CANARY_KEY,
        llm_model="deepseek-v4-pro",
    ) as client:
        response = client.get("/api/runtime")
    assert CANARY_KEY not in response.text
    assert "Authorization" not in response.text
    assert "Bearer" not in response.text


def test_tools_are_read_from_the_registry_not_hard_coded(tmp_path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/api/runtime").json()["tools"] == ["kb_search"]
    with _client(tmp_path, enable_python_tool=True) as client:
        tools = client.get("/api/runtime").json()["tools"]
    assert "python_run" in tools
    # The stubs stay unlisted: the registry refuses them, so the endpoint must
    # not imply the capability.
    assert "http_get" not in tools
    assert "file_read" not in tools


def test_the_endpoint_is_reachable_with_no_environment_configured() -> None:
    """No key, no network: the default deployment answers."""
    with TestClient(create_app(load_settings({}))) as client:
        assert client.get("/api/runtime").status_code == 200
