"""FastAPI application factory and dependency wiring."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from evalpilot import __version__
from evalpilot.config import Settings, load_settings
from evalpilot.container import Container, build_container
from evalpilot.routes import ci_export as ci_routes
from evalpilot.routes import demo as demo_routes
from evalpilot.routes import events as event_routes
from evalpilot.routes import health as health_routes
from evalpilot.routes import investigations as investigation_routes
from evalpilot.routes import memory as memory_routes
from evalpilot.routes import projects as project_routes
from evalpilot.routes import reports as report_routes
from evalpilot.routes import runs as run_routes
from evalpilot.routes import runtime as runtime_routes


def create_app(settings: Settings | None = None) -> FastAPI:
    container = build_container(settings)

    app = FastAPI(
        title="EvalPilot API",
        version=__version__,
        description=(
            "Regression evaluation backend. MVP runs are deterministic and require "
            "no external model or network access. Contracts: docs/INTERFACES.md, "
            "docs/V2_INTERFACES.md and docs/V3_LLM_INTERFACES.md"
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.container = container

    app.include_router(health_routes.router, prefix="/api", tags=["health"])
    app.include_router(project_routes.router, prefix="/api", tags=["projects"])
    app.include_router(run_routes.router, prefix="/api", tags=["runs"])
    app.include_router(report_routes.router, prefix="/api", tags=["reports"])
    app.include_router(ci_routes.router, prefix="/api", tags=["ci"])
    app.include_router(event_routes.router, prefix="/api", tags=["events"])
    app.include_router(demo_routes.router, prefix="/api", tags=["demo"])
    app.include_router(
        investigation_routes.router, prefix="/api", tags=["investigations"]
    )
    app.include_router(memory_routes.router, prefix="/api", tags=["memory"])
    app.include_router(runtime_routes.router, prefix="/api", tags=["runtime"])

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "evalpilot-backend", "version": __version__, "docs": "/docs"}

    return app


def settings_from_env_file(env_file: Path | None = None) -> Settings:
    """Settings loader that also lets a ``.env`` file override the environment."""
    if env_file is not None and env_file.exists():
        overrides: dict[str, str] = {}
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            overrides[key.strip()] = value.strip()
        return load_settings({**os.environ, **overrides})
    return load_settings()


__all__ = ["create_app", "settings_from_env_file"]
