"""GitHub webhook adapter for PR release-gate comments."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.integrations.github import (
    GitHubClient,
    GitHubError,
    verify_webhook_signature,
)
from evalpilot.release_gate import build_release_gate
from evalpilot.repository import NotFoundError

router = APIRouter()


def _payload_value(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


@router.post("/integrations/github/webhook")
async def github_webhook(
    request: Request,
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Accept a repository-dispatch style event and comment the gate on a PR."""

    settings = container.settings
    if not settings.github_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="EVALPILOT_GITHUB_WEBHOOK_SECRET is not configured",
        )

    raw = await request.body()
    if not verify_webhook_signature(
        raw,
        request.headers.get("X-Hub-Signature-256"),
        settings.github_webhook_secret,
    ):
        raise HTTPException(status_code=401, detail="invalid GitHub webhook signature")

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON payload") from exc

    client_payload = payload.get("client_payload") or {}
    run_id = str(
        client_payload.get("run_id")
        or payload.get("run_id")
        or ""
    ).strip()
    repository = str(
        client_payload.get("repository")
        or _payload_value(payload, "repository", "full_name")
        or ""
    ).strip()
    pr_number = client_payload.get("pr_number") or _payload_value(
        payload, "pull_request", "number"
    )

    if not run_id:
        raise HTTPException(status_code=422, detail="run_id is required")
    if not repository:
        raise HTTPException(status_code=422, detail="repository is required")

    try:
        report = container.repo.get_report(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=409, detail="run has no completed report") from exc

    report_url = (
        str(request.base_url).rstrip("/") + f"/api/runs/{run_id}/report"
    )
    gate = build_release_gate(
        run_id=run_id,
        metrics=report.metrics,
        report_url=report_url,
    )

    comment_url = ""
    if pr_number is not None:
        if not settings.github_token:
            raise HTTPException(
                status_code=503,
                detail="EVALPILOT_GITHUB_TOKEN is not configured",
            )
        body = "\n".join(
            [
                "## EvalPilot Release Gate",
                "",
                f"- Run: `{run_id}`",
                f"- Decision: **{gate.decision.upper()}**",
                f"- Exit code: `{gate.exit_code}`",
                f"- Baseline pass rate: `{gate.baseline_pass_rate}`",
                f"- Candidate pass rate: `{gate.candidate_pass_rate}`",
                f"- Mean difference: `{gate.mean_difference}`",
                f"- Reasons: `{', '.join(gate.reasons)}`",
                f"- Report: {gate.report_url}",
            ]
        )
        try:
            comment_url = GitHubClient(
                token=settings.github_token,
                api_url=settings.github_api_url,
            ).comment_on_pull_request(repository, int(pr_number), body)
        except (GitHubError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "accepted": True,
        "run_id": run_id,
        "repository": repository,
        "pull_request": pr_number,
        "decision": gate.decision,
        "exit_code": gate.exit_code,
        "comment_url": comment_url,
        "commented": bool(comment_url),
    }


__all__ = ["router"]
