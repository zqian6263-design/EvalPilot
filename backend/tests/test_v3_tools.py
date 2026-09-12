"""The real tool layer: allowlisted HTTP and file access, proven offline.

``CLAUDE.md`` non-negotiable #4 and ``docs/SPEC.md`` both require that the
default configuration makes no outbound request and reads no file. These tests
pin that default, then prove each gate actually holds when a policy *does* grant
access -- allowlist denial, redirect refusal, timeouts, response-size caps,
path traversal, symlink escape, JSON parsing, and the shape of the structured
trace every call records.

No test here can reach the public internet. HTTP is served either by an
ephemeral loopback server bound to port 0, or by an injected ``httpx`` transport
that answers from memory. Both are constructed per test and torn down with it.
"""

from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from evalpilot.tools import (
    ToolError,
    ToolNotAllowed,
    ToolPolicy,
    ToolRegistry,
    ToolResult,
    ToolTimeout,
    file_read,
    http_get,
    kb_search,
)

# --------------------------------------------------------------------------
# A loopback server, bound to an ephemeral port
# --------------------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves the fixed routes the HTTP tests exercise.

    Content length is always declared, so the client never has to distinguish a
    chunked body from a truncated one; the oversized and truncated cases need
    that precision to mean what they say.
    """

    def log_message(self, *_args: object) -> None:  # keep pytest output clean
        pass

    def handle_one_request(self) -> None:
        """Swallow the client-disconnect the timeout test deliberately causes.

        The slow route holds the connection while the client gives up; without
        this, stdlib's handler prints a traceback to stderr for an expected,
        asserted disconnect.
        """
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/json":
            self._respond(200, "application/json", b'{"ok": true, "items": [1, 2, 3]}')
        elif self.path == "/text":
            self._respond(200, "text/plain; charset=utf-8", b"hello \xe4\xb8\x96\xe7\x95\x8c")
        elif self.path == "/slow":
            # Long enough that a tiny client timeout always fires first, short
            # enough that teardown never waits on it.
            threading.Event().wait(0.5)
            self._respond(200, "text/plain", b"late")
        elif self.path == "/oversized":
            self._respond(200, "text/plain", b"x" * 8192)
        elif self.path == "/badjson":
            self._respond(200, "application/json", b"{not json at all")
        elif self.path == "/binary":
            self._respond(200, "application/octet-stream", b"\x00\x01\x02\xff")
        elif self.path == "/truncated":
            # Declare more than is written, then close. The client sees a
            # transport error, not a short body.
            self.send_response(200)
            self.send_header("content-type", "text/plain")
            self.send_header("content-length", "100")
            self.end_headers()
            self.wfile.write(b"short")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("location", "http://evil.example.com/steal")
            self.send_header("content-length", "0")
            self.end_headers()
        else:
            self._respond(404, "text/plain", b"missing")

    def _respond(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server() -> Iterator[str]:
    """A loopback HTTP server on an ephemeral port; yields its base URL."""
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = httpd.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture
def http_policy() -> ToolPolicy:
    """A policy that allows exactly the loopback host and nothing else."""
    return ToolPolicy(http_allowed_hosts=("127.0.0.1",), http_timeout=5.0)


def _demo_roots(tmp_path: Path) -> Path:
    """A repo-shaped demo tree, distinct from the read root's parent."""
    root = tmp_path / "demo-root"
    (root / "docs").mkdir(parents=True)
    (root / "kb.json").write_text(
        json.dumps({"doc_id": "kb-demo", "title": "Demo"}), encoding="utf-8"
    )
    (root / "docs" / "policy.txt").write_text(
        "Escalate to a human agent within 24 hours.", encoding="utf-8"
    )
    (tmp_path / "secret.txt").write_text("must never be readable", encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# Default deny
# --------------------------------------------------------------------------


def test_default_registry_exposes_only_kb_search() -> None:
    registry = ToolRegistry()
    assert registry.available() == ["kb_search"]


def test_default_registry_refuses_http_and_file_with_structured_traces() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolError) as http_exc:
        registry.invoke("http_get", url="http://example.com/")
    with pytest.raises(ToolError) as file_exc:
        registry.invoke("file_read", path="/etc/passwd")

    assert http_exc.value.reason == "no_allowed_hosts"
    assert file_exc.value.reason == "no_roots"
    # A refusal is itself an observation: both are recorded as denied traces.
    assert [call["outcome"] for call in registry.calls] == ["denied", "denied"]
    assert [call["tool"] for call in registry.calls] == ["http_get", "file_read"]


def test_default_tool_policy_grants_nothing() -> None:
    policy = ToolPolicy()
    assert policy.allows_http() is False
    assert policy.allows_files() is False
    assert policy.roots() == ()


# --------------------------------------------------------------------------
# HTTP allowlist
# --------------------------------------------------------------------------


def test_http_host_outside_the_allowlist_is_denied(server: str, http_policy: ToolPolicy) -> None:
    # The server is up and reachable; the allowlist is what refuses the call.
    with pytest.raises(ToolNotAllowed) as exc:
        http_get(url="http://evil.example.com/steal", policy=http_policy)
    assert exc.value.reason == "host_not_allowed"
    assert "evil.example.com" in str(exc.value)
    assert exc.value.trace["allowed_hosts"] == ["127.0.0.1"]
    assert exc.value.trace["outcome"] == "denied"


def test_http_non_http_scheme_is_denied(http_policy: ToolPolicy) -> None:
    with pytest.raises(ToolNotAllowed) as exc:
        http_get(url="file:///etc/passwd", policy=http_policy)
    assert exc.value.reason == "scheme_not_allowed"


def test_http_redirect_is_not_followed_to_an_unlisted_host(
    server: str, http_policy: ToolPolicy
) -> None:
    """A redirect cannot hop the allowlist: the 302 is surfaced, not followed.

    Following it would send the request the allowlist exists to prevent, so the
    redirect is an observation about the endpoint rather than a new fetch.
    """
    result = http_get(url=f"{server}/redirect", policy=http_policy)
    assert result.output["status"] == 302
    assert result.output["bytes"] == 0
    # The unlisted target is never contacted, so it never appears in output.
    assert "evil.example.com" not in json.dumps(result.output)


# --------------------------------------------------------------------------
# HTTP content handling
# --------------------------------------------------------------------------


def test_http_json_is_parsed_into_output_and_traced(
    server: str, http_policy: ToolPolicy
) -> None:
    result = http_get(url=f"{server}/json", policy=http_policy)
    assert isinstance(result, ToolResult)
    assert result.ok is True
    assert result.output["json"] == {"ok": True, "items": [1, 2, 3]}
    assert result.output["kind"] == "json"
    assert result.output["status"] == 200

    trace = result.trace
    assert trace["tool"] == "http_get"
    assert trace["outcome"] == "ok"
    assert trace["host"] == "127.0.0.1"
    assert trace["status"] == 200
    assert trace["kind"] == "json"
    assert trace["mode"] == "allowlisted-http"
    assert trace["bytes"] > 0


def test_http_text_is_decoded_utf8(server: str, http_policy: ToolPolicy) -> None:
    result = http_get(url=f"{server}/text", policy=http_policy)
    assert result.ok is True
    assert result.output["kind"] == "text"
    assert result.output["text"] == "hello 世界"
    assert result.output["json"] is None


def test_http_invalid_json_is_a_soft_failure(server: str, http_policy: ToolPolicy) -> None:
    """A body that claims JSON but does not parse returns the bytes plus the error."""
    result = http_get(url=f"{server}/badjson", policy=http_policy)
    assert result.ok is True
    assert result.output["kind"] == "invalid-json"
    assert result.output["json"] is None
    assert "parse_error" in result.output
    assert result.trace["parse_error"]


def test_http_binary_body_is_summarised_not_dumped(
    server: str, http_policy: ToolPolicy
) -> None:
    result = http_get(url=f"{server}/binary", policy=http_policy)
    assert result.ok is True
    assert result.output["kind"] == "binary"
    assert result.output["text"] is None
    assert result.output["json"] is None
    assert result.output["bytes"] == 4


def test_http_error_status_is_a_result_not_an_exception(
    server: str, http_policy: ToolPolicy
) -> None:
    result = http_get(url=f"{server}/missing", policy=http_policy)
    assert result.ok is False
    assert result.output["status"] == 404
    assert result.trace["outcome"] == "http_error"


# --------------------------------------------------------------------------
# HTTP limits
# --------------------------------------------------------------------------


def test_http_response_over_the_cap_is_refused(server: str, http_policy: ToolPolicy) -> None:
    with pytest.raises(ToolError) as exc:
        http_get(url=f"{server}/oversized", policy=http_policy, max_bytes=256)
    assert exc.value.reason == "response_too_large"
    assert exc.value.trace["max_bytes"] == 256
    assert exc.value.trace["outcome"] == "too_large"


def test_http_timeout_is_refused(server: str, http_policy: ToolPolicy) -> None:
    with pytest.raises(ToolTimeout) as exc:
        http_get(url=f"{server}/slow", policy=http_policy, timeout=0.05)
    assert exc.value.reason == "timeout"
    assert exc.value.trace["timeout"] == 0.05


def test_http_transport_error_is_refused(server: str, http_policy: ToolPolicy) -> None:
    with pytest.raises(ToolError) as exc:
        http_get(url=f"{server}/truncated", policy=http_policy)
    assert exc.value.reason == "transport_error"


# --------------------------------------------------------------------------
# HTTP through the registry and an injected transport
# --------------------------------------------------------------------------


def test_registry_lists_http_only_when_a_host_is_allowed() -> None:
    assert "http_get" not in ToolRegistry().available()
    allowed = ToolRegistry(policy=ToolPolicy(http_allowed_hosts=("127.0.0.1",)))
    assert "http_get" in allowed.available()


def test_registry_http_call_is_recorded(server: str, http_policy: ToolPolicy) -> None:
    registry = ToolRegistry(policy=http_policy)
    result = registry.invoke("http_get", url=f"{server}/json")
    assert result.ok is True
    assert registry.calls[-1]["tool"] == "http_get"
    assert registry.calls[-1]["outcome"] == "ok"
    assert registry.calls[-1]["host"] == "127.0.0.1"


def test_injected_transport_needs_no_socket() -> None:
    """The transport seam lets a caller answer http_get from memory."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"injected": True},
            headers={"content-type": "application/json"},
            request=request,
        )

    registry = ToolRegistry(
        policy=ToolPolicy(http_allowed_hosts=("internal.example",)),
        http_transport=httpx.MockTransport(handler),
    )
    result = registry.invoke("http_get", url="http://internal.example/status")
    assert result.ok is True
    assert result.output["json"] == {"injected": True}


# --------------------------------------------------------------------------
# File reads
# --------------------------------------------------------------------------


def test_file_read_is_disabled_without_roots(tmp_path: Path) -> None:
    with pytest.raises(ToolNotAllowed) as exc:
        file_read(path=str(tmp_path / "kb.json"), policy=ToolPolicy())
    assert exc.value.reason == "no_roots"


def test_file_read_returns_text_from_an_allowed_root(tmp_path: Path) -> None:
    root = _demo_roots(tmp_path)
    policy = ToolPolicy(file_read_roots=(root,))
    result = file_read(path="docs/policy.txt", policy=policy)

    assert result.ok is True
    assert result.output["text"] == "Escalate to a human agent within 24 hours."
    assert result.output["json"] is None
    assert result.output["relative_path"] == "docs/policy.txt"
    assert result.trace["kind"] == "text"
    assert result.trace["mode"] == "allowlisted-read"


def test_file_read_parses_json_within_a_root(tmp_path: Path) -> None:
    root = _demo_roots(tmp_path)
    result = file_read(path="kb.json", policy=ToolPolicy(file_read_roots=(root,)))
    assert result.ok is True
    assert result.output["json"] == {"doc_id": "kb-demo", "title": "Demo"}
    assert result.trace["kind"] == "json"


def test_file_read_accepts_an_absolute_path_inside_a_root(tmp_path: Path) -> None:
    root = _demo_roots(tmp_path)
    policy = ToolPolicy(file_read_roots=(root,))
    result = file_read(path=str(root / "kb.json"), policy=policy)
    assert result.ok is True
    assert result.output["relative_path"] == "kb.json"


@pytest.mark.parametrize(
    "attack",
    ["../secret.txt", "docs/../../secret.txt", "../../secret.txt", "docs/./../../secret.txt"],
)
def test_file_read_rejects_path_traversal(tmp_path: Path, attack: str) -> None:
    root = _demo_roots(tmp_path)
    policy = ToolPolicy(file_read_roots=(root,))
    with pytest.raises(ToolNotAllowed) as exc:
        file_read(path=attack, policy=policy)
    assert exc.value.reason == "path_not_allowed"
    assert exc.value.trace["outcome"] == "denied"


def test_file_read_rejects_an_absolute_path_outside_every_root(tmp_path: Path) -> None:
    root = _demo_roots(tmp_path)
    outside = tmp_path / "secret.txt"
    with pytest.raises(ToolNotAllowed) as exc:
        file_read(path=str(outside), policy=ToolPolicy(file_read_roots=(root,)))
    assert exc.value.reason == "path_not_allowed"


def test_file_read_rejects_a_symlink_escape(tmp_path: Path) -> None:
    """A symlink inside the root that points outside it is refused."""
    root = _demo_roots(tmp_path)
    link = root / "escape.txt"
    try:
        link.symlink_to(tmp_path / "secret.txt")
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("symlinks are not available on this platform")
    with pytest.raises(ToolNotAllowed) as exc:
        file_read(path="escape.txt", policy=ToolPolicy(file_read_roots=(root,)))
    assert exc.value.reason == "path_not_allowed"


def test_file_read_refuses_a_file_over_the_cap(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "big.txt").write_text("y" * 4096, encoding="utf-8")
    with pytest.raises(ToolError) as exc:
        file_read(path="big.txt", policy=ToolPolicy(file_read_roots=(root,)), max_bytes=128)
    assert exc.value.reason == "file_too_large"
    assert exc.value.trace["bytes"] == 4096


def test_file_read_refuses_a_missing_file(tmp_path: Path) -> None:
    root = _demo_roots(tmp_path)
    with pytest.raises(ToolError) as exc:
        file_read(path="nope.txt", policy=ToolPolicy(file_read_roots=(root,)))
    assert exc.value.reason == "not_found"


def test_file_read_refuses_non_utf8_bytes(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "blob.txt").write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(ToolError) as exc:
        file_read(path="blob.txt", policy=ToolPolicy(file_read_roots=(root,)))
    assert exc.value.reason == "not_utf8"


# --------------------------------------------------------------------------
# Preserved behavior
# --------------------------------------------------------------------------


def test_kb_search_is_unchanged_by_the_real_tool_layer() -> None:
    result = kb_search("What is the refund window?", top_k=1)
    assert result.ok is True
    assert result.output["documents"][0]["doc_id"] == "kb-refund-policy"
    assert result.trace["mode"] == "deterministic-keyword"


def test_python_tool_still_refuses_when_enabled() -> None:
    registry = ToolRegistry(enable_python=True)
    assert "python_run" in registry.available()
    with pytest.raises(ToolError) as exc:
        registry.invoke("python_run", source="print('hi')")
    assert exc.value.reason == "python_unimplemented"


def test_trace_shape_is_stable_across_tools(server: str, tmp_path: Path) -> None:
    """Every tool trace carries a ``tool`` key naming the tool, and is JSON-serialisable."""
    root = _demo_roots(tmp_path)
    policy = ToolPolicy(http_allowed_hosts=("127.0.0.1",), file_read_roots=(root,))
    results = [
        kb_search("refund"),
        http_get(url=f"{server}/json", policy=policy),
        file_read(path="kb.json", policy=policy),
    ]
    for result in results:
        assert "tool" in result.trace
        assert result.trace["tool"] == result.name
        # Traces are persisted to a JSON artifact, so they must serialise.
        json.dumps(result.trace)

    # The tools that can fail report a machine-readable outcome; refusals carry
    # one too, so a denied call is as traceable as a successful one.
    assert [result.trace["outcome"] for result in results[1:]] == ["ok", "ok"]


# --------------------------------------------------------------------------
# The investigation's real tool observation
# --------------------------------------------------------------------------


def test_investigation_records_one_real_tool_observation(container, monkeypatch) -> None:
    """The deterministic investigation performs one real file_read observation.

    The read is aimed at the run's own artifact directory. The repo path here
    contains non-ASCII characters, which Windows' ``os.path`` handles but the
    path-containment check must too; asserting the call succeeded is part of the
    test, not incidental to it.
    """
    from evalpilot.demo import ensure_demo_project
    from evalpilot.models import InvestigationStepKind, RunStatus

    _, run = ensure_demo_project(container.repo, container.settings)
    if run.status == RunStatus.QUEUED:
        _drive(container, run.id)

    investigation = container.repo.create_investigation(run.id, "Can the candidate ship?")

    import asyncio

    outcome = asyncio.run(container.investigation_runner.run(investigation.id))
    tool_steps = [
        step for step in outcome.steps if step.kind is InvestigationStepKind.TOOL
    ]
    assert len(tool_steps) == 1, "the investigation must record exactly one tool step"

    step = tool_steps[0]
    assert step.data["tool"] == "file_read"
    assert step.data["checked"] > 0, "the cross-check must actually read an artifact"
    assert step.data["tool_calls"].get("kb_search")
    assert step.data["failures"] == []
    # The step cites a persisted evidence row, which is what makes it a claim
    # the report can back rather than an assertion.
    assert step.evidence_ids
    evidence = container.repo.get_evidence(step.evidence_ids[0])
    assert evidence is not None
    assert evidence.kind == "trace"
    assert evidence.payload["count"] == step.data["checked"]


def test_investigation_tool_observation_does_not_change_run_scores(container) -> None:
    """Adding the cross-check's evidence row cannot move the run's own metrics."""
    from evalpilot.demo import ensure_demo_project
    from evalpilot.models import RunStatus

    _, run = ensure_demo_project(container.repo, container.settings)
    if run.status == RunStatus.QUEUED:
        _drive(container, run.id)

    before = container.repo.get_report(run.id).metrics
    investigation = container.repo.create_investigation(run.id, "Can the candidate ship?")

    import asyncio

    asyncio.run(container.investigation_runner.run(investigation.id))
    after = container.repo.get_report(run.id).metrics
    assert before == after, "the diagnostic evidence row must be invisible to scoring"


def _drive(container, run_id: str) -> None:
    import asyncio

    from evalpilot.models import RunStatus

    async def _run() -> None:
        await container.runner.start(run_id)
        for _ in range(3000):
            await asyncio.sleep(0.02)
            if container.repo.get_run(run_id).status.is_terminal:
                return
        raise AssertionError(f"run {run_id} did not finish")

    assert container.repo.get_run(run_id).status == RunStatus.QUEUED
    asyncio.run(_run())
