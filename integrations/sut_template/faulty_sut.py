"""Deliberately broken SUTs used as negative fixtures for the onboarding check.

This file exists only so that ``scripts/validate-sut.ps1`` can be proven to
fail. It is **not part of the template you copy**: leave it behind with the rest
of the repository when you build your own service.

Each mode breaks exactly one part of the contract:

``health``        ``GET /health`` returns HTTP 503
``capabilities``  ``GET /capabilities`` returns HTTP 404
``version``       advertises a revision that ``POST /v1/answer`` cannot serve
``intervention``  advertises an intervention that returns HTTP 500
``silent``        answers HTTP 200 for a revision it never advertised
``response``      returns an answer record with empty and wrongly typed fields

Select a mode with ``create_app(mode)`` in tests, or with the
``EVALPILOT_FAULTY_MODE`` environment variable when running uvicorn:

    EVALPILOT_FAULTY_MODE=response uvicorn faulty_sut:app --port 8021
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

BASELINE_VERSION = "v1.0-baseline"
CANDIDATE_VERSION = "v1.1-candidate"
FULL_CONTEXT_ENABLED = "full_context_enabled"
GHOST_VERSION = "v2.0-ghost"
GHOST_INTERVENTION = "ghost_intervention"

MODES: tuple[str, ...] = (
    "health",
    "capabilities",
    "version",
    "intervention",
    "silent",
    "response",
)

GOOD_ANSWER: dict[str, Any] = {
    "answer": "Based on Refund Policy: Products may be returned within 30 days.",
    "citations": ["kb-refund"],
    "tool_calls": ["kb.search:kb-refund"],
    "latency_ms": 120,
    "model": f"faulty-kb-assistant@{BASELINE_VERSION}",
    "refused": False,
}


def _declared_versions(mode: str) -> list[str]:
    versions = [BASELINE_VERSION, CANDIDATE_VERSION]
    if mode == "version":
        versions.append(GHOST_VERSION)
    return versions


def _declared_interventions(mode: str) -> list[str]:
    interventions = [FULL_CONTEXT_ENABLED]
    if mode == "intervention":
        interventions.append(GHOST_INTERVENTION)
    return interventions


def create_app(mode: str) -> FastAPI:
    """Build a FastAPI app that breaks the contract in exactly one way."""

    if mode not in MODES:
        raise ValueError(f"unknown faulty SUT mode {mode!r}; expected one of {list(MODES)}")

    app = FastAPI(title=f"Faulty SUT ({mode})")

    @app.get("/health")
    def health() -> Any:
        if mode == "health":
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {
            "status": "ok",
            "service": f"faulty-sut-{mode}",
            "versions": _declared_versions(mode),
        }

    @app.get("/capabilities")
    def capabilities() -> Any:
        if mode == "capabilities":
            return JSONResponse(status_code=404, content={"detail": "not found"})
        return {
            "contract_version": "1.0",
            "versions": _declared_versions(mode),
            "interventions": _declared_interventions(mode),
            "features": ["citations"],
        }

    @app.post("/v1/answer")
    def answer(payload: dict[str, Any] | None = None) -> Any:
        body = payload or {}
        version = str(body.get("version") or "")
        intervention = body.get("intervention")

        if mode == "version" and version == GHOST_VERSION:
            return JSONResponse(status_code=500, content={"detail": "no such revision"})
        if mode == "intervention" and intervention == GHOST_INTERVENTION:
            return JSONResponse(status_code=500, content={"detail": "intervention crashed"})
        if mode == "silent":
            return JSONResponse(status_code=200, content=GOOD_ANSWER)
        if mode == "response":
            broken = dict(GOOD_ANSWER)
            broken["answer"] = ""
            broken["latency_ms"] = "fast"
            broken["refused"] = "no"
            broken["unexpected_field"] = True
            return JSONResponse(status_code=200, content=broken)

        if version not in (BASELINE_VERSION, CANDIDATE_VERSION):
            return JSONResponse(
                status_code=400, content={"detail": f"unsupported version {version!r}"}
            )
        if intervention is not None and intervention != FULL_CONTEXT_ENABLED:
            return JSONResponse(
                status_code=400,
                content={"detail": f"unsupported intervention {intervention!r}"},
            )
        return JSONResponse(status_code=200, content=GOOD_ANSWER)

    return app


app = create_app(os.environ.get("EVALPILOT_FAULTY_MODE", "response"))
