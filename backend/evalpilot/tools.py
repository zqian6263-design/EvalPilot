"""Allowlisted tool layer.

Every tool is a pure, deterministic, in-process function: no network access and
no arbitrary code execution in the default configuration. The Python tool is
present but refuses to run unless ``EVALPILOT_ENABLE_PYTHON_TOOL`` is enabled,
per the collaboration contract.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from evalpilot.fixtures import KNOWLEDGE_BASE, KnowledgeDoc


class ToolError(RuntimeError):
    """Raised when a tool is unknown, disabled, or misused."""


@dataclass
class ToolResult:
    name: str
    ok: bool
    output: dict[str, Any]
    trace: dict[str, Any] = field(default_factory=dict)


def kb_search(query: str, top_k: int = 2) -> ToolResult:
    """Keyword retrieval over the static knowledge base.

    Documents are ranked by how many distinct keywords they match, then by
    ``doc_id`` to keep ties deterministic.
    """
    scored: list[tuple[int, KnowledgeDoc]] = []
    for doc in KNOWLEDGE_BASE:
        hits = doc.hit_count(query)
        if hits:
            scored.append((hits, doc))
    scored.sort(key=lambda pair: (-pair[0], pair[1].doc_id))
    hits = scored[:top_k]

    return ToolResult(
        name="kb_search",
        ok=True,
        output={
            "query": query,
            "documents": [
                {"doc_id": doc.doc_id, "title": doc.title, "text": doc.text}
                for _, doc in hits
            ],
        },
        trace={
            "tool": "kb_search",
            "query": query,
            "candidates_scanned": len(KNOWLEDGE_BASE),
            "scores": {doc.doc_id: score for score, doc in scored},
            "hits": [doc.doc_id for _, doc in hits],
            "mode": "deterministic-keyword",
        },
    )


def _unsupported(name: str) -> Callable[..., ToolResult]:
    def _call(**_kwargs: Any) -> ToolResult:
        raise ToolError(f"tool {name!r} is not available in the MVP backend")

    return _call


def http_get(*, url: str, **_kwargs: Any) -> ToolResult:
    """Placeholder for the HTTP tool. Deliberately not implemented in the MVP.

    The seeded scenario is fully local, so no outbound request is ever made.
    """
    _unsupported("http_get")
    raise AssertionError("unreachable")


def file_read(*, path: str, **_kwargs: Any) -> ToolResult:
    """Placeholder for the file-parsing tool (not needed by the seeded demo)."""
    _unsupported("file_read")
    raise AssertionError("unreachable")


def python_run(*, source: str, allow: bool = False, **_kwargs: Any) -> ToolResult:
    """Allowlisted Python tool. Disabled unless explicitly enabled."""
    if not allow:
        raise ToolError(
            "python tool is disabled; set EVALPILOT_ENABLE_PYTHON_TOOL=true to enable"
        )
    raise ToolError("python tool has no implementation in the MVP backend")


@dataclass
class ToolRegistry:
    """Resolves tool names to callables and records every invocation."""

    enable_python: bool = False
    calls: list[dict[str, Any]] = field(default_factory=list)

    _TOOLS: dict[str, str] = field(
        default_factory=lambda: {
            "kb_search": "kb_search",
            "http_get": "http_get",
            "file_read": "file_read",
            "python_run": "python_run",
        }
    )

    def available(self) -> list[str]:
        names = ["kb_search"]
        # http_get / file_read are stubs; listing them would imply capability we
        # do not have. python_run is listed only when explicitly enabled.
        if self.enable_python:
            names.append("python_run")
        return names

    def invoke(self, name: str, **kwargs: Any) -> ToolResult:
        if name == "python_run" and not self.enable_python:
            raise ToolError(
                "python tool is disabled; set EVALPILOT_ENABLE_PYTHON_TOOL=true to enable"
            )
        handlers: dict[str, Callable[..., ToolResult]] = {"kb_search": kb_search}
        handler = handlers.get(name)
        if handler is None:
            raise ToolError(f"unknown or disabled tool: {name!r}")

        result = handler(**kwargs)
        self.calls.append({"tool": name, **result.trace})
        return result
