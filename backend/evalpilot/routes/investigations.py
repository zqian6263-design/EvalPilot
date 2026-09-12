"""``/api/investigations`` routes: create, start, detail, events, report."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, StreamingResponse

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.investigation import InvestigationError
from evalpilot.models import (
    Event,
    Investigation,
    InvestigationCreate,
    InvestigationDetail,
)
from evalpilot.repository import NotFoundError

router = APIRouter()

#: The investigation event stream emits the envelope frozen in
#: ``docs/INTERFACES.md`` — ``docs/V2_INTERFACES.md`` asks for exactly that
#: reuse. The rendering lives here rather than in ``routes/events.py`` because
#: the two streams have different terminal conditions (a run ends, an
#: investigation completes) and sharing the helper would couple them for six
#: lines of formatting.
NDJSON_MEDIA_TYPE = "application/x-ndjson"
MAX_STREAM_SECONDS = 300.0
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _ndjson(event: Event) -> str:
    return json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"


def _sse(event: Event) -> str:
    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return f"event: {event.type.value}\ndata: {payload}\n\n"


async def _stream(
    container: Container, investigation_id: str, cursor: int, fmt: str, follow: bool
) -> AsyncIterator[str]:
    render = _sse if fmt == "sse" else _ndjson
    loop = asyncio.get_running_loop()
    deadline = loop.time() + MAX_STREAM_SECONDS
    idle_ticks = 0

    while True:
        events = container.repo.list_events(investigation_id, after=cursor)
        for event in events:
            cursor = max(cursor, event.sequence)
            yield render(event)

        if not follow:
            return

        try:
            investigation = container.repo.get_investigation(investigation_id)
        except NotFoundError:
            return

        # Close once every event of a finished investigation has been delivered.
        if investigation.status.is_terminal and not events:
            return

        if loop.time() > deadline:
            return

        if not events:
            idle_ticks += 1
            if idle_ticks % 25 == 0:
                yield ": keep-alive\n\n" if fmt == "sse" else "\n"

        await asyncio.sleep(0.2)


@router.get("/investigations", response_model=list[Investigation])
def list_investigations(
    container: Container = Depends(get_container),
) -> list[Investigation]:
    return container.repo.list_investigations()


@router.post(
    "/investigations",
    response_model=Investigation,
    status_code=status.HTTP_201_CREATED,
)
def create_investigation(
    body: InvestigationCreate, container: Container = Depends(get_container)
) -> Investigation:
    """Create a queued investigation over a completed run.

    Idempotent on ``run_id``: a run has at most one investigation, so re-posting
    returns the existing record rather than starting a second narrative over the
    same evidence.
    """
    try:
        run = container.repo.get_run(body.run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if run.status.value != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"run {run.id} is {run.status.value}; an investigation needs a "
                "completed run with a persisted report"
            ),
        )

    return container.repo.create_investigation(body.run_id, body.objective)


@router.post(
    "/investigations/{investigation_id}/start",
    response_model=Investigation,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_investigation(
    investigation_id: str, container: Container = Depends(get_container)
) -> Investigation:
    """Start a queued investigation. Returns immediately; poll or stream for progress."""
    try:
        investigation = container.repo.get_investigation(investigation_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if investigation.status.value != "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"investigation {investigation_id} is {investigation.status.value}; "
                "only a queued investigation can be started"
            ),
        )

    asyncio.create_task(_drive(container, investigation_id))
    return investigation


async def _drive(container: Container, investigation_id: str) -> None:
    """Run the investigation in the background.

    Failures reach the caller through the persisted status and event log, not an
    exception handler: by the time one happens the HTTP response has already
    been sent. The service marks the investigation failed and logs the reason
    before re-raising, so there is nothing left to do here.
    """
    try:
        await container.investigation_runner.run(investigation_id)
    except Exception:  # noqa: BLE001 - already recorded on the investigation
        return


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetail)
def get_investigation(
    investigation_id: str, container: Container = Depends(get_container)
) -> InvestigationDetail:
    try:
        payload = container.investigation_runner.detail(investigation_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return InvestigationDetail.model_validate(payload)


@router.get("/investigations/{investigation_id}/events")
def investigation_events(
    investigation_id: str,
    after: int = Query(default=0, ge=0, description="Last sequence already seen."),
    fmt: str = Query(default="sse", pattern="^(sse|ndjson)$"),
    follow: bool = Query(default=True, description="Keep the stream open until it ends."),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    try:
        container.repo.get_investigation(investigation_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    media_type = "text/event-stream" if fmt == "sse" else NDJSON_MEDIA_TYPE
    return StreamingResponse(
        _stream(container, investigation_id, after, fmt, follow),
        media_type=media_type,
        headers=SSE_HEADERS if fmt == "sse" else {},
    )


@router.get("/investigations/{investigation_id}/report.md")
def get_report_markdown(
    investigation_id: str, container: Container = Depends(get_container)
) -> PlainTextResponse:
    try:
        markdown = container.investigation_runner.report_markdown(investigation_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvestigationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return PlainTextResponse(content=markdown, media_type="text/markdown")


__all__ = ["router"]
