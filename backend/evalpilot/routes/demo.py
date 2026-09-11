"""``GET /api/demo/seed`` — deterministic demo metadata only, no side effects."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from evalpilot import demo

router = APIRouter()


@router.get("/demo/seed")
def demo_seed() -> dict[str, Any]:
    """Describe the seeded demo.

    Contractually read-only: this endpoint never writes to the database and
    never starts a run. Use ``python -m evalpilot.cli seed`` for the
    side-effecting setup.
    """
    return demo.demo_metadata()
