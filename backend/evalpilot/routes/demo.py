"""``/api/demo`` — deterministic demo metadata only, no side effects."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from evalpilot import demo
from evalpilot.container import Container
from evalpilot.dependencies import get_container

router = APIRouter()


@router.get("/demo/seed")
def demo_seed() -> dict[str, Any]:
    """Describe the seeded demo.

    Contractually read-only: this endpoint never writes to the database and
    never starts a run. Use ``python -m evalpilot.cli seed`` for the
    side-effecting setup.
    """
    return demo.demo_metadata()


@router.get("/demo/investigation")
def demo_investigation(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Describe the autonomous-investigation workspace.

    Also read-only, in the same sense as ``/demo/seed``: it reports the entry
    run, whether an investigation already exists for it, and the fixed phase
    list, so the UI can render the workspace before anything is created. It
    never creates a project, a run, or an investigation.
    """
    return demo.investigation_metadata(container.repo)
