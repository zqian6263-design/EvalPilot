"""``GET /api/health``."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from evalpilot.container import Container
from evalpilot.dependencies import get_container

router = APIRouter()


@router.get("/health")
def health(container: Container = Depends(get_container)) -> dict[str, str]:
    return {"status": "ok", "version": container.settings.version}
