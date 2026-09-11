"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from evalpilot.container import Container


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover - only if the app was misassembled
        raise RuntimeError("application container is not configured")
    return container
