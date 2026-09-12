"""Manual startup check: run a real uvicorn server and exercise the HTTP API.

Not part of the pytest suite — it binds a port, so it is kept as an explicit,
runnable script. Verifies the same contract as the tests but over real sockets.

Usage (from backend/, with the venv active):
    python scripts/startup_check.py
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

HOST = "127.0.0.1"
PORT = 8129
BASE = f"http://{HOST}:{PORT}"


def wait_for_health(proc: subprocess.Popen) -> None:
    for _ in range(160):
        if proc.poll() is not None:
            raise SystemExit(f"server exited early:\n{proc.stdout.read()}")
        time.sleep(0.25)
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=1) as response:
                if response.status == 200:
                    print("GET /api/health ->", response.status, response.read().decode())
                    return
        except Exception:
            continue
    raise SystemExit("server never became ready")


def get_json(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as response:
        return json.loads(response.read().decode())


def post_json(path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload or {}).encode()
    request = urllib.request.Request(
        f"{BASE}{path}", method="POST", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode()
        return json.loads(text) if text.strip() else {}


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp())
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(pathlib.Path(__file__).resolve().parent.parent),
        "PYTHONIOENCODING": "utf-8",
        "EVALPILOT_DB_PATH": str(tmp / "startup.db"),
        "EVALPILOT_STEP_DELAY": "0",
    })

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "evalpilot.app:create_app", "--factory",
         "--host", HOST, "--port", str(PORT), "--log-level", "warning"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        wait_for_health(proc)

        meta = get_json("/api/demo/seed")
        print("GET /api/demo/seed -> 200 | cases:", meta["case_count"],
              "| scripted:", meta["scripted_regressions"])

        project = post_json("/api/projects",
                            {"name": "Startup KB QA", "scenario": "kb-qa"})
        print("POST /api/projects ->", project["id"][:8])

        run = post_json("/api/runs", {
            "project_id": project["id"],
            "baseline_version": "v1.0-baseline",
            "candidate_version": "v1.1-candidate",
            "case_count": 26,
            "seed": 20260919,
        })
        print("POST /api/runs ->", run["id"][:8], run["status"])

        post_json(f"/api/runs/{run['id']}/start")
        print("POST /api/runs/{id}/start -> 202")

        detail: dict = {}
        for _ in range(600):
            time.sleep(0.1)
            detail = get_json(f"/api/runs/{run['id']}")
            if detail["run"]["status"] in {"completed", "failed", "cancelled"}:
                break
        print("run status:", detail["run"]["status"],
              "| cases:", len(detail["test_cases"]),
              "| evidence:", detail["evidence_count"],
              "| findings:", detail["finding_count"])

        report = get_json(f"/api/runs/{run['id']}/report")
        print("GET /api/runs/{id}/report -> regression_detected:",
              report["metrics"]["regression_detected"],
              "| regression_confirmed:", report["metrics"]["regression_confirmed"],
              "| regressed:", report["metrics"]["regressed_scenarios"])

        with urllib.request.urlopen(
            f"{BASE}/api/runs/{run['id']}/events?fmt=ndjson&follow=true", timeout=60
        ) as response:
            body = response.read().decode()
        events = [line for line in body.splitlines() if line.strip()]
        print("GET /api/runs/{id}/events (ndjson, follow=true) ->",
              response.status, "| events:", len(events))

        print("\nSTARTUP CHECK OK")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
