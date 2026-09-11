"""``/api/projects`` routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from evalpilot.container import Container
from evalpilot.dependencies import get_container
from evalpilot.models import Project, ProjectCreate
from evalpilot.repository import NotFoundError

router = APIRouter()


@router.get("/projects", response_model=list[Project])
def list_projects(container: Container = Depends(get_container)) -> list[Project]:
    return container.repo.list_projects()


@router.post("/projects", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate, container: Container = Depends(get_container)
) -> Project:
    return container.repo.create_project(body.name, body.scenario)


@router.get("/projects/{project_id}", response_model=Project)
def get_project(
    project_id: str, container: Container = Depends(get_container)
) -> Project:
    try:
        return container.repo.get_project(project_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
