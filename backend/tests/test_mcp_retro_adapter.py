from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = ROOT / "integrations" / "mcp_retro" / "server.py"
WORKLOAD_PATH = ROOT / "integrations" / "mcp_retro" / "workload.json"


def load_adapter():
    spec = importlib.util.spec_from_file_location("mcp_retro_server", ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_intervention_routes_candidate_to_fixed_runtime():
    adapter = load_adapter()

    assert (
        adapter.resolve_runtime_version(
            "mcp-1.30.0", "mcp_v2_error_path_enabled"
        )
        == "mcp-2.2.0"
    )


def test_regular_candidate_request_keeps_candidate_runtime():
    adapter = load_adapter()

    assert adapter.resolve_runtime_version("mcp-1.30.0", None) == "mcp-1.30.0"


def test_response_uses_measured_probe_observation(monkeypatch):
    adapter = load_adapter()
    observed = {
        "answer": "channel=jsonrpc_error; structured_code=-32000",
        "citations": ["mcp-sdk:2.2.0"],
        "tool_calls": ["mcp.call_tool:protocol_error"],
        "latency_ms": 7,
    }
    monkeypatch.setattr(adapter, "run_probe", lambda *args, **kwargs: observed)
    request = adapter.SutRequest(
        run_id="run-1",
        test_case_id="case-1",
        scenario_id="protocol-error-channel",
        question="What channel carries the protocol error?",
        version="mcp-1.30.0",
        intervention="mcp_v2_error_path_enabled",
    )

    response = adapter.answer(request)

    assert response.answer == observed["answer"]
    assert response.citations == observed["citations"]
    assert response.tool_calls == observed["tool_calls"]
    assert response.model == "mcp-tool-runtime@mcp-2.2.0+intervention"


def test_unknown_runtime_version_is_rejected():
    adapter = load_adapter()

    with pytest.raises(ValueError, match="unsupported MCP runtime version"):
        adapter.resolve_runtime_version("mcp-9.9.9", None)


def test_workload_contains_three_protocol_regressions_and_three_controls():
    workload = json.loads(WORKLOAD_PATH.read_text(encoding="utf-8"))
    scenarios = workload["scenarios"]
    regressions = [
        scenario
        for scenario in scenarios
        if scenario.get("suggested_intervention") == "mcp_v2_error_path_enabled"
    ]
    controls = [
        scenario
        for scenario in scenarios
        if not scenario.get("suggested_intervention")
    ]

    assert workload["baseline_version"] == "mcp-2.2.0"
    assert workload["candidate_version"] == "mcp-1.30.0"
    assert len(regressions) == 3
    assert len(controls) == 3
