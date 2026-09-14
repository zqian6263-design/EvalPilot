"""Run a real ASGI application under uvicorn for HTTP-level tests.

Several tests need a genuine socket rather than an in-process ASGI transport:
the onboarding validator, the external-intervention replay, and anything else
that must prove bytes crossed a network boundary. This module is the one place
that knows how to start and stop such a server.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import uvicorn

STARTUP_TIMEOUT_SECONDS = 30.0
SHUTDOWN_TIMEOUT_SECONDS = 20.0


def free_port() -> int:
    """An ephemeral localhost port that is free right now."""

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def serve_app(app: Any) -> Iterator[str]:
    """Serve ``app`` on an ephemeral port and yield its base URL.

    The server runs in a background thread so the calling test can talk to it
    over real HTTP. It is always stopped on exit, including on assertion failure.
    """

    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("uvicorn test server did not start")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=SHUTDOWN_TIMEOUT_SECONDS)
