"""``/api/memory`` routes: the seeded historical incident history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.memory import DEFAULT_MATCH_LIMIT, select_incidents
from evalpilot.models import IncidentQueryResult
from evalpilot.repository import NotFoundError

router = APIRouter()


@router.get("/memory/incidents", response_model=IncidentQueryResult)
def list_incidents(
    query: str | None = Query(
        default=None, description="Free-text query; when given, results are scored."
    ),
    tag: str | None = Query(default=None, description="Restrict to one incident tag."),
    limit: int = Query(default=DEFAULT_MATCH_LIMIT, ge=1, le=20),
    container: Container = Depends(get_container),
) -> IncidentQueryResult:
    """List the seeded incidents, or score them against ``query``.

    Read from SQLite rather than from the fixture module so the endpoint reports
    what is actually seeded. Without a query this is a filtered listing and
    ``matches`` is empty; with one, both lists are in match order.
    """
    try:
        seeded = container.repo.list_historical_incidents()
    except NotFoundError as exc:  # pragma: no cover - a table read cannot 404
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not query:
        incidents = [item for item in seeded if tag is None or tag in item.tags]
        return IncidentQueryResult(query=None, tag=tag, incidents=incidents, matches=[])

    matched_incidents, matches = select_incidents(query=query, tag=tag, limit=limit)
    # `select_incidents` scores the in-process fixtures. Re-read each matched row
    # so the response is the seeded record, not a fixture copy.
    seeded_by_id = {item.id: item for item in seeded}
    incidents = [
        seeded_by_id.get(item.id, item) for item in matched_incidents
    ]
    return IncidentQueryResult(query=query, tag=tag, incidents=incidents, matches=matches)


__all__ = ["router"]
