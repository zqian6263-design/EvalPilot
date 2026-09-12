"""``GET /api/runtime``.

Reports which mode the backend resolved and what it will actually do, without
ever returning a credential. It is the one endpoint an operator checks after
setting ``EVALPILOT_LLM_MODE=live``: it says whether the model is configured,
which model, which host it will be called on, whether any call has fallen back,
and which tools are registered.

``tools`` is read from the live :class:`~evalpilot.tools.ToolRegistry` rather
than hard-coded, so the endpoint cannot claim a capability the process does not
have — an enabled Python tool changes the answer here too.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from evalpilot.container import Container
from evalpilot.dependencies import get_container

router = APIRouter()


@router.get("/runtime")
def runtime(container: Container = Depends(get_container)) -> dict:
    return container.llm_runtime.status(tools=container.tools.available())
