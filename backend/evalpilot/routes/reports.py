"""``GET /api/runs/{run_id}/report``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.models import ReleaseGate, Report, RunStatus
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

    metrics = report.metrics
    confirmed = metrics.get("regression_confirmed") is True
    detected = metrics.get("regression_detected") is True
    if confirmed:
        decision = "block"
        exit_code = 2
        reasons = ["regression_confirmed"]
    elif detected:
        decision = "review"
        exit_code = 1
        reasons = ["localized_regression_requires_review"]
    else:
        decision = "allow"
        exit_code = 0
        reasons = ["no_regression_detected"]

    return ReleaseGate(
        run_id=run_id,
        decision=decision,
        exit_code=exit_code,
        regression_detected=detected,
        regression_confirmed=confirmed,
        baseline_pass_rate=float(metrics.get("baseline_pass_rate", 0.0)),
        candidate_pass_rate=float(metrics.get("candidate_pass_rate", 0.0)),
        mean_difference=_optional_float(metrics.get("mean_difference")),
        ci_lower=_optional_float(metrics.get("ci_lower")),
        ci_upper=_optional_float(metrics.get("ci_upper")),
        threshold=_optional_float(metrics.get("regression_threshold")),
        reasons=reasons,
        report_url=str(request.url_for("get_report", run_id=run_id)),
    )


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None

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
