"""HTTP SUT adapter for the public MCP Python SDK error-propagation gap.

This process never imports the ``mcp`` package itself. Each request is delegated
to a version-isolated interpreter, so the compared releases cannot contaminate
one another through ``sys.modules`` or dependency resolution.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

BASELINE_VERSION = "mcp-2.2.0"
CANDIDATE_VERSION = "mcp-1.30.0"
INTERVENTION = "mcp_v2_error_path_enabled"
ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = Path(__file__).with_name("probe.py")


class SutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    test_case_id: str
    scenario_id: str
    question: str
    version: str
    intervention: str | None = None


class SutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)
    model: str
    refused: bool = False


def resolve_runtime_version(version: str, intervention: str | None) -> str:
    """Resolve the isolated MCP runtime used for one request."""

    if version not in {BASELINE_VERSION, CANDIDATE_VERSION}:
        raise ValueError(f"unsupported MCP runtime version: {version}")
    if version == CANDIDATE_VERSION and intervention == INTERVENTION:
        return BASELINE_VERSION
    return version


def _python_for(version: str) -> str:
    if version == BASELINE_VERSION:
        configured = os.environ.get("EVALPILOT_MCP_V2_PYTHON")
        default = ROOT / ".runtime" / "p4-mcp-v2" / "Scripts" / "python.exe"
    else:
        configured = os.environ.get("EVALPILOT_MCP_V1_PYTHON")
        default = ROOT / ".runtime" / "p4-mcp-v1" / "Scripts" / "python.exe"
    path = Path(configured) if configured else default
    return str(path if path.exists() else Path(os.sys.executable))


def run_probe(
    *,
    version: str,
    scenario_id: str,
    intervention: str | None,
) -> dict[str, Any]:
    """Run the real MCP client/server probe under the selected release."""

    python = _python_for(version)
    command = [
        python,
        str(PROBE_PATH),
        scenario_id,
        "--intervention",
        intervention or "",
    ]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=PROBE_PATH.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(os.environ.get("EVALPILOT_MCP_PROBE_TIMEOUT_SECONDS", "45")),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"MCP probe timed out for {version}/{scenario_id}") from exc

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or not lines:
        detail = (completed.stderr or completed.stdout or "no output").strip()
        raise RuntimeError(
            f"MCP probe failed for {version}/{scenario_id}: {detail[-1200:]}"
        )
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"MCP probe returned invalid JSON for {version}/{scenario_id}: {lines[-1][:500]}"
        ) from exc

    answer = payload.get("answer")
    citations = payload.get("citations", [])
    tool_calls = payload.get("tool_calls", [])
    if not isinstance(answer, str) or not answer:
        raise RuntimeError("MCP probe payload is missing a non-empty answer")
    if not isinstance(citations, list) or not isinstance(tool_calls, list):
        raise RuntimeError("MCP probe citations/tool_calls must be arrays")

    measured_latency = int((time.perf_counter() - started) * 1000)
    return {
        "answer": answer,
        "citations": [str(item) for item in citations],
        "tool_calls": [str(item) for item in tool_calls],
        "latency_ms": measured_latency,
    }


def answer(request: SutRequest) -> SutResponse:
    try:
        runtime_version = resolve_runtime_version(
            request.version, request.intervention
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        observed = run_probe(
            version=runtime_version,
            scenario_id=request.scenario_id,
            intervention=request.intervention,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    suffix = "+intervention" if request.intervention else ""
    return SutResponse(
        answer=str(observed["answer"]),
        citations=list(observed["citations"]),
        tool_calls=list(observed["tool_calls"]),
        latency_ms=int(observed.get("latency_ms", 0)),
        model=f"mcp-tool-runtime@{runtime_version}{suffix}",
        refused=False,
    )


app = FastAPI(
    title="EvalPilot MCP Retrospective Adapter",
    version="1.0.0",
    description="Version-isolated public MCP SDK error-propagation retrospective.",
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "evalpilot-mcp-retro-sut",
        "engine": "modelcontextprotocol/python-sdk",
        "versions": [BASELINE_VERSION, CANDIDATE_VERSION],
        "source_issue": "https://github.com/modelcontextprotocol/python-sdk/issues/2770",
    }


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "versions": [BASELINE_VERSION, CANDIDATE_VERSION],
        "interventions": [INTERVENTION],
        "features": ["tool_calls", "protocol_error", "isolated_runtimes"],
    }


@app.post("/v1/answer", response_model=SutResponse)
def answer_endpoint(request: SutRequest) -> SutResponse:
    return answer(request)
