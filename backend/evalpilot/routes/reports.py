"""``GET /api/runs/{run_id}/report``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.models import ReleaseGate, Report, RunStatus
from evalpilot.release_gate import build_release_gate
from evalpilot.repository import NotFoundError

router = APIRouter()


@router.get("/runs/{run_id}/gate", response_model=ReleaseGate)
def get_release_gate(
    run_id: str,
    request: Request,
    container: Container = Depends(get_container),
) -> ReleaseGate:
    """Return the CI-compatible release decision for a completed run."""
    try:
        run = container.repo.get_run(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        report = container.repo.get_report(run_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"run {run_id} is {run.status.value}; a gate decision is available "
                f"once the run reaches {RunStatus.COMPLETED.value}"
            ),
        ) from exc

    return build_release_gate(
        run_id=run_id,
        metrics=report.metrics,
        report_url=str(request.url_for("get_report", run_id=run_id)),
    )


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
