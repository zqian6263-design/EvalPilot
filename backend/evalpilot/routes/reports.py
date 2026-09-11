"""``GET /api/runs/{run_id}/report``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.models import Report, RunStatus
from evalpilot.repository import NotFoundError

router = APIRouter()


@router.get("/runs/{run_id}/report", response_model=Report)
def get_report(run_id: str, container: Container = Depends(get_container)) -> Report:
    try:
        run = container.repo.get_run(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        return container.repo.get_report(run_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"run {run_id} is {run.status.value}; a report is available once the run "
                f"reaches {RunStatus.COMPLETED.value}"
            ),
        ) from exc
