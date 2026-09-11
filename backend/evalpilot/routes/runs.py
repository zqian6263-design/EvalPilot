"""``/api/runs`` routes: creation, detail, start, and cancel."""

from __future__ import annotations

import random

from fastapi import APIRouter, Depends, HTTPException, status

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.models import Run, RunCreate, RunDetail, RunStatus
from evalpilot.repository import NotFoundError
from evalpilot.runner import RunConflictError

router = APIRouter()

DEFAULT_CASE_COUNT = 10


@router.get("/runs", response_model=list[Run])
def list_runs(container: Container = Depends(get_container)) -> list[Run]:
    return container.repo.list_runs()


@router.post("/runs", response_model=Run, status_code=status.HTTP_201_CREATED)
def create_run(body: RunCreate, container: Container = Depends(get_container)) -> Run:
    try:
        container.repo.get_project(body.project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    seed = body.seed if body.seed is not None else random.Random().randint(0, 2**31 - 1)
    case_count = body.case_count if body.case_count is not None else DEFAULT_CASE_COUNT
    return container.repo.create_run(
        project_id=body.project_id,
        baseline_version=body.baseline_version,
        candidate_version=body.candidate_version,
        seed=seed,
        case_count=case_count,
    )


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, container: Container = Depends(get_container)) -> RunDetail:
    try:
        run = container.repo.get_run(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RunDetail(
        run=run,
        test_cases=container.repo.list_test_cases(run_id),
        evidence=container.repo.list_evidence(run_id),
        evidence_count=container.repo.count_evidence(run_id),
        finding_count=container.repo.count_findings(run_id),
        event_count=container.repo.count_events(run_id),
    )


@router.post("/runs/{run_id}/start", response_model=Run, status_code=status.HTTP_202_ACCEPTED)
async def start_run(run_id: str, container: Container = Depends(get_container)) -> Run:
    try:
        return await container.runner.start(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post("/runs/{run_id}/cancel", response_model=Run)
def cancel_run(run_id: str, container: Container = Depends(get_container)) -> Run:
    try:
        return container.runner.cancel(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


# Re-exported for route tests that assert on the accepted status vocabulary.
__all__ = ["router", "RunStatus"]
