"""Allowlisted tool layer.

Two kinds of tool live here.

**Pure tools.** :func:`kb_search` is a deterministic in-process function over the
static knowledge base: no network, no filesystem, no randomness.

**Gated tools.** :func:`http_get` and :func:`file_read` reach outside the
process, so neither is reachable until a :class:`ToolPolicy` explicitly names
what it may reach. A registry built with no policy exposes neither tool and
refuses both: the default remains "no outbound request, no file access", which
is what ``CLAUDE.md`` non-negotiable #4 and ``docs/SPEC.md`` require. Granting
access is a per-instance decision, not an environment side effect.

The Python tool is present but refuses to run unless
``EVALPILOT_ENABLE_PYTHON_TOOL`` is enabled, per the collaboration contract.

Every call is recorded on the registry as a structured trace row -- tool name,
arguments, outcome, and a rationale string -- so an evaluation report can show
what a tool actually did rather than asserting that it worked. Nothing here
interprets tool output: a fetched document is data, and no instruction inside
one is ever executed.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from evalpilot.browser_tool import BrowserError, run_browser
from evalpilot.fixtures import KNOWLEDGE_BASE, KnowledgeDoc

#: Defaults. Deliberately small: a tool that is granted access should still be
#: cheap to call and unable to turn one request into an unbounded read.
DEFAULT_HTTP_TIMEOUT = 5.0
DEFAULT_MAX_RESPONSE_BYTES = 512 * 1024
DEFAULT_MAX_FILE_BYTES = 256 * 1024
DEFAULT_USER_AGENT = "EvalPilot/1.0 (+offline-evaluation-tool)"

#: Media types this layer is willing to decode as UTF-8 text. Anything else is
#: summarised by content type and length rather than dumped into evidence.
_TEXTUAL_MEDIA_TYPES = frozenset(
    {"application/json", "application/x-ndjson", "application/xml", "application/xhtml+xml"}
)


class ToolError(RuntimeError):
    """A tool is unknown, disabled, denied by policy, or returned unusable data.

    ``reason`` is a stable machine-readable code (``not_allowed``,
    ``unknown_tool``, ``timeout``, ``response_too_large``, ``path_not_allowed``,
    ...) and ``trace`` is the partial structured trace for the failed call, so a
    caller can persist *why* a tool was refused even though no result exists.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str = "tool_error",
        trace: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.trace = trace or {}


class ToolTimeout(ToolError):
    """A tool exceeded its configured time budget."""


class ToolNotAllowed(ToolError):
    """A tool call was denied by policy (host allowlist, read roots)."""


@dataclass(frozen=True)
class ToolPolicy:
    """What the gated tools are allowed to reach.

    Both allowlists default to empty, so a default :class:`ToolPolicy` grants
    nothing. Hosts are compared literally (case-insensitive) against the URL's
    hostname; ports are not part of the match, which is what lets a test point
    ``http_get`` at an ephemeral local port without widening the allowlist.
    Read roots are resolved and every candidate path must stay inside one of
    them, including through symlinks.
    """

    http_allowed_hosts: tuple[str, ...] = ()
    file_read_roots: tuple[Path, ...] = ()
    http_timeout: float = DEFAULT_HTTP_TIMEOUT
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    user_agent: str = DEFAULT_USER_AGENT
    browser_enabled: bool = False
    browser_allowed_hosts: tuple[str, ...] = ()
    browser_screenshot_root: Path | None = None
    browser_timeout_seconds: float = 30.0
    browser_executable_path: str | None = None
    browser_headless: bool = True

    def allows_http(self) -> bool:
        return bool(self.http_allowed_hosts)

    def allows_files(self) -> bool:
        return bool(self.file_read_roots)

    def allows_browser(self) -> bool:
        return self.browser_enabled and bool(self.browser_allowed_hosts)

    def allows_host(self, host: str) -> bool:
        return host.lower() in {allowed.lower() for allowed in self.http_allowed_hosts}

    def allows_browser_host(self, host: str) -> bool:
        return host.lower() in {allowed.lower() for allowed in self.browser_allowed_hosts}

    def browser_root(self) -> Path | None:
        return None if self.browser_screenshot_root is None else Path(self.browser_screenshot_root).expanduser().resolve()

    def roots(self) -> tuple[Path, ...]:
        return tuple(Path(root).expanduser().resolve() for root in self.file_read_roots)


@dataclass
class ToolResult:
    name: str
    ok: bool
    output: dict[str, Any]
    trace: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Pure tools
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# HTTP tool
# --------------------------------------------------------------------------


def _http_trace(
    *,
    url: str,
    allowed_hosts: Sequence[str],
    outcome: str,
    **extra: Any,
) -> dict[str, Any]:
    parsed = urlparse(url)
    trace: dict[str, Any] = {
        "tool": "http_get",
        "url": url,
        "host": parsed.hostname or "",
        "port": parsed.port,
        "allowed_hosts": list(allowed_hosts),
        "outcome": outcome,
    }
    trace.update(extra)
    return trace


def _decode_http_body(
    *, url: str, status: int, content_type: str, body: bytes, max_bytes: int
) -> dict[str, Any]:
    """Turn a checked response body into the tool's structured output.

    JSON is parsed; textual media types are decoded as UTF-8; anything else is
    reported by content type and length rather than decoded. A body that claims
    to be JSON but does not parse is a soft failure -- the bytes are still
    returned, with the parse error recorded, because a caller debugging an
    endpoint needs to see what actually came back.
    """
    media_type = content_type.split(";", 1)[0].strip().lower()
    parsed: Any = None
    parse_error: str | None = None

    decoded = media_type == "application/json" or media_type.endswith("+json")
    textual = decoded or media_type in _TEXTUAL_MEDIA_TYPES or media_type.startswith("text/")
    text: str | None = None
    if textual:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            return {
                "url": url,
                "status": status,
                "content_type": content_type,
                "bytes": len(body),
                "kind": "binary",
                "text": None,
                "json": None,
                "parse_error": f"declared {content_type or 'text'} but is not valid UTF-8: {exc}",
            }

    if text is not None:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
            if decoded:
                return {
                    "url": url,
                    "status": status,
                    "content_type": content_type,
                    "bytes": len(body),
                    "kind": "invalid-json",
                    "text": text[:max_bytes],
                    "json": None,
                    "parse_error": parse_error,
                }

    if parsed is not None:
        return {
            "url": url,
            "status": status,
            "content_type": content_type,
            "bytes": len(body),
            "kind": "json",
            "text": None,
            "json": parsed,
            "parse_error": None,
        }

    if text is not None:
        return {
            "url": url,
            "status": status,
            "content_type": content_type,
            "bytes": len(body),
            "kind": "text",
            "text": text,
            "json": None,
            "parse_error": parse_error,
        }

    return {
        "url": url,
        "status": status,
        "content_type": content_type,
        "bytes": len(body),
        "kind": "binary",
        "text": None,
        "json": None,
        "parse_error": None,
    }


def _file_trace(
    *, path: str, roots: Sequence[Path], outcome: str, **extra: Any
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "tool": "file_read",
        "path": path,
        "roots": [str(root) for root in roots],
        "outcome": outcome,
    }
    trace.update(extra)
    return trace


def http_get(
    *,
    url: str,
    policy: ToolPolicy | None = None,
    timeout: float | None = None,
    max_bytes: int | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ToolResult:
    """Fetch one allowlisted URL, with a timeout and a response-size cap.

    Refusals that must not be silently retried (host not allowlisted, timeout,
    oversized body) raise :class:`ToolError`; an HTTP error status is a soft
    failure and is returned as an ``ok=False`` result, because 404 is a real
    answer about the endpoint, not a failure of the tool layer.
    """
    resolved = policy or ToolPolicy()
    limit = max_bytes if max_bytes is not None else resolved.max_response_bytes
    budget = timeout if timeout is not None else resolved.http_timeout

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ToolNotAllowed(
            f"http_get only supports http/https URLs, got {parsed.scheme or 'no scheme'!r}",
            reason="scheme_not_allowed",
            trace=_http_trace(
                url=url,
                allowed_hosts=resolved.http_allowed_hosts,
                outcome="denied",
                reason="scheme_not_allowed",
            ),
        )
    host = (parsed.hostname or "").lower()
    if not resolved.allows_host(host):
        raise ToolNotAllowed(
            f"host {host!r} is not in the http allowlist {sorted(resolved.http_allowed_hosts)}",
            reason="host_not_allowed",
            trace=_http_trace(
                url=url,
                allowed_hosts=resolved.http_allowed_hosts,
                outcome="denied",
                reason="host_not_allowed",
            ),
        )

    # Read one byte past the cap so an oversized body is detected without
    # buffering the whole thing into memory first. Redirects are not followed:
    # a redirect target would bypass the allowlist check that already ran, so it
    # is reported as a non-2xx outcome instead.
    body = bytearray()
    try:
        with httpx.Client(
            transport=transport,
            timeout=budget,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream(
                "GET", url, headers={"user-agent": resolved.user_agent}
            ) as response:
                status = response.status_code
                headers = response.headers
                final_url = str(response.url)
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise ToolError(
                            f"response for {url} exceeds the {limit}-byte cap",
                            reason="response_too_large",
                            trace=_http_trace(
                                url=url,
                                allowed_hosts=resolved.http_allowed_hosts,
                                outcome="too_large",
                                reason="response_too_large",
                                max_bytes=limit,
                            ),
                        )
    except httpx.TimeoutException as exc:
        raise ToolTimeout(
            f"http_get timed out after {budget}s for {url}",
            reason="timeout",
            trace=_http_trace(
                url=url,
                allowed_hosts=resolved.http_allowed_hosts,
                outcome="timeout",
                reason="timeout",
                timeout=budget,
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise ToolError(
            f"http_get failed for {url}: {exc}",
            reason="transport_error",
            trace=_http_trace(
                url=url,
                allowed_hosts=resolved.http_allowed_hosts,
                outcome="error",
                reason="transport_error",
                error=f"{type(exc).__name__}: {exc}",
            ),
        ) from exc

    content_type = headers.get("content-type", "")
    raw = bytes(body)
    output = _decode_http_body(
        url=url, status=status, content_type=content_type, body=raw, max_bytes=limit
    )
    ok = status < 400
    trace = _http_trace(
        url=url,
        allowed_hosts=resolved.http_allowed_hosts,
        outcome="ok" if ok else "http_error",
        status=status,
        content_type=content_type,
        bytes=len(raw),
        kind=output["kind"],
        request="GET",
        mode="allowlisted-http",
    )
    if final_url != url:
        trace["redirected_to"] = final_url
    if output.get("parse_error"):
        trace["parse_error"] = output["parse_error"]
    return ToolResult(name="http_get", ok=ok, output=output, trace=trace)


# --------------------------------------------------------------------------
# File tool
# --------------------------------------------------------------------------


def _resolve_within(path: str, roots: Sequence[Path], *, tool: str) -> Path:
    """Resolve ``path`` under one of ``roots``, or refuse.

    The candidate is resolved (symlinks included) before the containment check,
    so a symlink pointing outside a root is rejected rather than followed. A
    relative candidate is tried against each root in order; an absolute one must
    already be inside a root.
    """
    raw = Path(path)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.extend(Path(root) / raw for root in roots)
    if not candidates:
        empty = {"tool": tool, "path": path, "roots": [],
                 "outcome": "denied", "reason": "no_roots"}
        raise ToolNotAllowed(
            f"{tool} has no configured read roots",
            reason="no_roots",
            trace=empty,
        )

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        for root in roots:
            if resolved == root or root in resolved.parents:
                return resolved
    denied = {"tool": tool, "path": path, "roots": [str(root) for root in roots],
              "outcome": "denied", "reason": "path_not_allowed"}
    raise ToolNotAllowed(
        f"{tool} refused {path!r}: it resolves outside the configured read roots",
        reason="path_not_allowed",
        trace=denied,
    )


def file_read(
    *,
    path: str,
    policy: ToolPolicy | None = None,
    max_bytes: int | None = None,
) -> ToolResult:
    """Read one text or JSON file from inside a configured root.

    Paths are resolved before containment is checked, so traversal and symlink
    escapes are refused. The file is read as UTF-8; a JSON file is parsed. Sizes
    above the cap, missing files and undecodable bytes are raised as
    :class:`ToolError` -- a partial file read into evidence would be worse than
    a refusal, because it would look complete.
    """
    resolved_policy = policy or ToolPolicy()
    roots = resolved_policy.roots()
    if not roots:
        raise ToolNotAllowed(
            "file_read is disabled: no read roots are configured",
            reason="no_roots",
            trace=_file_trace(path=path, roots=roots, outcome="denied", reason="no_roots"),
        )

    limit = max_bytes if max_bytes is not None else resolved_policy.max_file_bytes
    resolved = _resolve_within(path, roots, tool="file_read")

    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise ToolError(
            f"file_read could not stat {path!r}: {exc}",
            reason="not_found",
            trace=_file_trace(path=path, roots=roots, outcome="error", reason="not_found"),
        ) from exc
    if not resolved.is_file():
        raise ToolError(
            f"file_read refused {path!r}: it is not a regular file",
            reason="not_a_file",
            trace=_file_trace(path=path, roots=roots, outcome="denied", reason="not_a_file"),
        )
    if size > limit:
        raise ToolError(
            f"file {path!r} is {size} bytes, above the {limit}-byte cap",
            reason="file_too_large",
            trace=_file_trace(
                path=path,
                roots=roots,
                outcome="too_large",
                reason="file_too_large",
                bytes=size,
                max_bytes=limit,
            ),
        )

    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise ToolError(
            f"file_read could not read {path!r}: {exc}",
            reason="read_error",
            trace=_file_trace(path=path, roots=roots, outcome="error", reason="read_error"),
        ) from exc

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(
            f"file {path!r} is not valid UTF-8 text: {exc}",
            reason="not_utf8",
            trace=_file_trace(
                path=path,
                roots=roots,
                outcome="error",
                reason="not_utf8",
                bytes=len(raw),
            ),
        ) from exc

    parsed: Any = None
    parse_error: str | None = None
    if resolved.suffix.lower() == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)

    output: dict[str, Any] = {
        "path": str(resolved),
        "relative_path": _relative_to_roots(resolved, roots),
        "bytes": len(raw),
        "text": text if parsed is None else None,
        "json": parsed,
        "parse_error": parse_error,
    }
    trace = _file_trace(
        path=path,
        roots=roots,
        outcome="ok",
        resolved_path=str(resolved),
        bytes=len(raw),
        kind="json" if parsed is not None else "text",
        mode="allowlisted-read",
    )
    if parse_error:
        trace["parse_error"] = parse_error
    return ToolResult(name="file_read", ok=True, output=output, trace=trace)


def _relative_to_roots(resolved: Path, roots: Sequence[Path]) -> str:
    for root in roots:
        if resolved == root or root in resolved.parents:
            try:
                return resolved.relative_to(root).as_posix() or "."
            except ValueError:  # pragma: no cover - containment already checked
                continue
    return resolved.name


# --------------------------------------------------------------------------
# Browser tool
# --------------------------------------------------------------------------


def browser_run(
    *,
    url: str,
    actions: Sequence[dict[str, Any]],
    screenshot_path: str,
    policy: ToolPolicy,
) -> ToolResult:
    """Run a bounded browser task under the configured policy."""
    if not policy.allows_browser():
        raise ToolNotAllowed(
            "browser_run is disabled: enable it and configure browser_allowed_hosts",
            reason="browser_disabled",
        )
    root = policy.browser_root()
    if root is None:
        raise ToolNotAllowed("browser screenshot root is not configured", reason="browser_screenshot_root_missing")
    try:
        output = run_browser(
            url=url,
            actions=actions,
            screenshot=screenshot_path,
            allowed_hosts=policy.browser_allowed_hosts,
            screenshot_root=root,
            timeout_seconds=policy.browser_timeout_seconds,
            executable_path=policy.browser_executable_path,
            headless=policy.browser_headless,
        )
    except BrowserError as exc:
        raise ToolError(str(exc), reason=exc.reason) from exc
    return ToolResult(
        name="browser_run",
        ok=True,
        output=output,
        trace={
            "tool": "browser_run",
            "outcome": "completed",
            "url": output.get("final_url"),
            "allowed_hosts": list(policy.browser_allowed_hosts),
            "actions": output.get("action_trace", []),
            "screenshot": output.get("screenshot_path"),
            "console_errors": output.get("console_errors", []),
        },
    )


# --------------------------------------------------------------------------
# Python tool
# --------------------------------------------------------------------------


def python_run(*, source: str, allow: bool = False, **_kwargs: Any) -> ToolResult:
    """Allowlisted Python tool. Disabled unless explicitly enabled."""
    if not allow:
        raise ToolError(
            "python tool is disabled; set EVALPILOT_ENABLE_PYTHON_TOOL=true to enable",
            reason="python_disabled",
        )
    raise ToolError(
        "python tool has no implementation in the MVP backend",
        reason="python_unimplemented",
    )


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


@dataclass
class ToolRegistry:
    """Resolves tool names to callables and records every invocation.

    ``available()`` reports what the registry's policy actually allows, so a UI
    never offers a tool the registry would refuse. Every call -- including one
    that raised -- is appended to :attr:`calls` as a structured trace row.
    """

    enable_python: bool = False
    policy: ToolPolicy = field(default_factory=ToolPolicy)
    #: Injected HTTP transport for ``http_get``. Production leaves this ``None``
    #: (real sockets); tests point it at an ephemeral local server or a mock
    #: transport so no test ever touches the public internet.
    http_transport: httpx.BaseTransport | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def available(self) -> list[str]:
        names = ["kb_search"]
        if self.policy.allows_http():
            names.append("http_get")
        if self.policy.allows_files():
            names.append("file_read")
        if self.policy.allows_browser():
            names.append("browser_run")
        # python_run is listed only when explicitly enabled, and even then it
        # refuses: enabling the flag does not grant execution.
        if self.enable_python:
            names.append("python_run")
        return names

    def invoke(self, name: str, **kwargs: Any) -> ToolResult:
        try:
            handler = self._handler(name)
            result = handler(**kwargs)
        except ToolError as exc:
            # A refused call is still an observation: record the denied trace so
            # an offline policy decision is visible rather than invisible.
            self.calls.append({"tool": name, "ok": False, **exc.trace})
            raise
        self.calls.append({"tool": name, **result.trace})
        return result

    def _handler(self, name: str) -> Callable[..., ToolResult]:
        if name == "python_run":
            if not self.enable_python:
                raise ToolError(
                    "python tool is disabled; set EVALPILOT_ENABLE_PYTHON_TOOL=true to enable",
                    reason="python_disabled",
                )
            return lambda **kwargs: python_run(allow=True, **kwargs)
        if name == "kb_search":
            return kb_search
        if name == "http_get":
            if not self.policy.allows_http():
                raise ToolError(
                    "http_get is disabled: no hosts are in the allowlist",
                    reason="no_allowed_hosts",
                    trace={
                        "tool": "http_get",
                        "allowed_hosts": [],
                        "outcome": "denied",
                        "reason": "no_allowed_hosts",
                    },
                )
            return lambda **kwargs: http_get(
                policy=self.policy, transport=self.http_transport, **kwargs
            )
        if name == "file_read":
            if not self.policy.allows_files():
                raise ToolError(
                    "file_read is disabled: no read roots are configured",
                    reason="no_roots",
                    trace={
                        "tool": "file_read",
                        "roots": [],
                        "outcome": "denied",
                        "reason": "no_roots",
                    },
                )
            return lambda **kwargs: file_read(policy=self.policy, **kwargs)
        if name == "browser_run":
            if not self.policy.allows_browser():
                raise ToolError(
                    "browser_run is disabled: no browser hosts are configured",
                    reason="no_browser_hosts",
                    trace={
                        "tool": "browser_run",
                        "allowed_hosts": [],
                        "outcome": "denied",
                        "reason": "no_browser_hosts",
                    },
                )
            return lambda **kwargs: browser_run(policy=self.policy, **kwargs)
        raise ToolError(f"unknown or disabled tool: {name!r}", reason="unknown_tool")
