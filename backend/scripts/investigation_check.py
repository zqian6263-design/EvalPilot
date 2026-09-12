"""End-to-end check of the autonomous investigation over real HTTP.

Not part of the pytest suite: it binds a port, so it is kept as an explicit,
runnable script alongside ``startup_check.py``.

Usage (from backend/):
    python scripts/investigation_check.py

Exits non-zero if any promise in ``docs/V2_INTERFACES.md`` does not hold.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HOST = "127.0.0.1"
PORT = 8130
BASE = f"http://{HOST}:{PORT}"

OBJECTIVE = (
    "Decide whether v1.1-candidate can ship: the candidate is faster, but it adds a "
    "summarization step and we need to know what it costs."
)


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


def get_text(path: str) -> tuple[int, str]:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as response:
        return response.status, response.read().decode()


def post_json(path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload or {}).encode()
    request = urllib.request.Request(
        f"{BASE}{path}",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode()
        return json.loads(text) if text.strip() else {}


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")
    print(f"  ok: {message}")


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp())
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(pathlib.Path(__file__).resolve().parent.parent),
            "PYTHONIOENCODING": "utf-8",
            "EVALPILOT_DB_PATH": str(tmp / "investigation.db"),
            "EVALPILOT_STEP_DELAY": "0",
        }
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "evalpilot.app:create_app",
            "--factory",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        wait_for_health(proc)

        meta = get_json("/api/demo/investigation")
        expect(meta["incident_count"] >= 3, f"{meta['incident_count']} seeded incidents")
        expect(meta["entry_run_id"] is None, "no entry run before one is executed")

        memory = get_json("/api/memory/incidents?query=escalation+clause+dropped")
        expect(bool(memory["matches"]), "memory lookup returns scored matches")

        project = post_json(
            "/api/projects",
            {"name": "Investigation KB QA", "scenario": "kb-qa"},
        )
        run = post_json(
            "/api/runs",
            {
                "project_id": project["id"],
                "baseline_version": "v1.0-baseline",
                "candidate_version": "v1.1-candidate",
                "case_count": 26,
                "seed": 20260919,
            },
        )
        post_json(f"/api/runs/{run['id']}/start")
        detail: dict = {}
        for _ in range(900):
            time.sleep(0.1)
            detail = get_json(f"/api/runs/{run['id']}")
            if detail["run"]["status"] in {"completed", "failed", "cancelled"}:
                break
        expect(detail["run"]["status"] == "completed", "demo run completed")
        print(
            f"  run {run['id'][:8]} | cases {len(detail['test_cases'])} "
            f"| evidence {detail['evidence_count']}"
        )

        investigation = post_json(
            "/api/investigations", {"run_id": run["id"], "objective": OBJECTIVE}
        )
        print("POST /api/investigations ->", investigation["id"][:8], investigation["status"])
        again = post_json(
            "/api/investigations", {"run_id": run["id"], "objective": OBJECTIVE}
        )
        expect(again["id"] == investigation["id"], "creation is idempotent on run_id")

        post_json(f"/api/investigations/{investigation['id']}/start")
        payload: dict = {}
        for _ in range(300):
            time.sleep(0.1)
            payload = get_json(f"/api/investigations/{investigation['id']}")
            if payload["investigation"]["status"] in {"completed", "failed"}:
                break

        expect(
            payload["investigation"]["status"] == "completed", "investigation completed"
        )
        decision = payload["decision"]
        expect(decision is not None, "release decision persisted")
        print("  decision:", decision["verdict"], decision["risk_level"])

        risks = [s for s in payload["steps"] if s["kind"] == "risk" and s["title"] != "Release investigation"]
        probes = [s for s in payload["steps"] if s["kind"] == "probe"]
        experiments = payload["counterfactuals"]
        matches = payload["memory_matches"]

        expect(len(risks) >= 3, f"{len(risks)} risk hypotheses (need >= 3)")
        expect(len(matches) >= 2, f"{len(matches)} memory matches (need >= 2)")
        expect(len(probes) >= 8, f"{len(probes)} follow-up probes (need >= 8)")

        root_causes = [e for e in experiments if e["verdict"] == "root_cause"]
        by_intervention: dict[str, list[str]] = {}
        for experiment in root_causes:
            by_intervention.setdefault(experiment["intervention"], []).append(
                experiment["scenario_id"]
            )
        print("  root-cause interventions:", json.dumps(by_intervention))
        expect(
            len(by_intervention.get("compression_disabled", [])) >= 6,
            "compression_disabled dominates the dropped-clause root causes",
        )
        expect(
            "prompt-injection-password" in by_intervention.get("security_guard_enabled", []),
            "security_guard_enabled is the credential-disclosure root cause",
        )
        expect(decision["verdict"] == "block", "decision blocks the release")

        sequences = [s["sequence"] for s in payload["steps"]]
        expect(sequences == list(range(len(sequences))), "steps are sequenced from 0")

        status, markdown = get_text(
            f"/api/investigations/{investigation['id']}/report.md"
        )
        expect(status == 200, "report.md served")
        check_report(markdown, payload)

        with urllib.request.urlopen(
            f"{BASE}/api/investigations/{investigation['id']}/events?fmt=ndjson&follow=true",
            timeout=60,
        ) as response:
            body = response.read().decode()
        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        expect(len(events) >= 6, f"{len(events)} sequenced events streamed")
        expect(
            [e["sequence"] for e in events] == list(range(1, len(events) + 1)),
            "event sequences are contiguous from 1",
        )
        expect(
            all(e["run_id"] == investigation["id"] for e in events),
            "events are keyed by the investigation id",
        )

        print("\nINVESTIGATION CHECK OK")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


def check_report(markdown: str, payload: dict) -> None:
    expect(markdown.startswith("# Release investigation report"), "report has a title")
    expect("## Release decision" in markdown, "report has the decision section")
    expect("`block`" in markdown, "report states the block verdict")
    expect("## Follow-up probes" in markdown, "report lists the probes")
    expect("## Counterfactual replay" in markdown, "report lists the replay")
    expect("## Evidence index" in markdown, "report has an evidence index")
    expect("`compression_disabled`" in markdown, "report names the dominant intervention")
    for finding_id in payload["decision"]["blocking_findings"]:
        expect(
            finding_id in markdown,
            f"report names blocking finding {finding_id[:8]}",
        )


if __name__ == "__main__":
    raise SystemExit(main())
