"""``GET /api/events`` — run progress stream.

``docs/INTERFACES.md`` specifies ``GET /runs/{run_id}/events`` with SSE or
newline-delimited progress events. The frozen path lives under ``/runs``, so
that exact route is registered here too; the alias under ``/events`` exists so
clients can connect once and be notified when a run is created or started.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.models import TERMINAL_RUN_STATUSES, Event
from evalpilot.repository import NotFoundError

router = APIRouter()

NDJSON_MEDIA_TYPE = "application/x-ndjson"
# Safety valve so a stream can never hang a client forever.
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


def _resolve_run_id(container: Container, run_id: str | None) -> str:
    if run_id:
        container.repo.get_run(run_id)  # 404s if unknown
        return run_id

    runs = container.repo.list_runs()
    active = [run for run in runs if run.status.value not in TERMINAL_RUN_STATUSES]
    if active:
        return active[0].id
    if runs:
        return runs[0].id
    raise HTTPException(
        status_code=404,
        detail="no runs exist yet; create a run before opening the event stream",
    )


async def _stream(
    container: Container, run_id: str, cursor: int, fmt: str, follow: bool
) -> AsyncIterator[str]:
    render = _sse if fmt == "sse" else _ndjson
    loop = asyncio.get_running_loop()
    deadline = loop.time() + MAX_STREAM_SECONDS
    idle_ticks = 0

    while True:
        events = container.repo.list_events(run_id, after=cursor)
        for event in events:
            cursor = max(cursor, event.sequence)
            yield render(event)

        if not follow:
            return

        try:
            run = container.repo.get_run(run_id)
        except NotFoundError:
            return

        # Close once every event of a finished run has been delivered.
        if run.status.value in TERMINAL_RUN_STATUSES and not events:
            return

        if loop.time() > deadline:
            return

        # Keep intermediary proxies from closing an idle connection.
        if not events:
            idle_ticks += 1
            if idle_ticks % 25 == 0:
                yield ": keep-alive\n\n" if fmt == "sse" else "\n"

        await asyncio.sleep(0.2)


@router.get("/events")
def run_events(
    run_id: str | None = Query(default=None, description="Run to follow."),
    after: int = Query(default=0, ge=0, description="Last sequence already seen."),
    fmt: str = Query(default="sse", pattern="^(sse|ndjson)$"),
    follow: bool = Query(default=True, description="Keep the stream open until the run ends."),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    resolved = _resolve_run_id(container, run_id)
    media_type = "text/event-stream" if fmt == "sse" else NDJSON_MEDIA_TYPE
    return StreamingResponse(
        _stream(container, resolved, after, fmt, follow),
        media_type=media_type,
        headers=SSE_HEADERS if fmt == "sse" else {},
    )


@router.get("/runs/{run_id}/events")
def run_events_frozen_path(
    run_id: str,
    after: int = Query(default=0, ge=0),
    fmt: str = Query(default="sse", pattern="^(sse|ndjson)$"),
    follow: bool = Query(default=True),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """The exact path frozen in ``docs/INTERFACES.md``."""
    try:
        container.repo.get_run(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    media_type = "text/event-stream" if fmt == "sse" else NDJSON_MEDIA_TYPE
    return StreamingResponse(
        _stream(container, run_id, after, fmt, follow),
        media_type=media_type,
        headers=SSE_HEADERS if fmt == "sse" else {},
    )
