"""Compare the public Haystack SUT across two upstream library versions."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from evalpilot.fixtures import SUPPORT_SCENARIOS

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"


def _start(python: Path, port: int) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(BACKEND_DIR)}
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "evalpilot.sut.haystack_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def _wait(url: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return response.json()
        except Exception as exc:  # noqa: BLE001 - startup polling
            last = exc
        time.sleep(0.25)
    raise RuntimeError(f"server did not start: {url}: {last}")


def _answer(base: str, scenario, version: str) -> dict:
    response = httpx.post(
        f"{base}/v1/answer",
        json={
            "run_id": "upstream-version-check",
            "test_case_id": scenario.scenario_id,
            "scenario_id": scenario.scenario_id,
            "question": scenario.question,
            "version": version,
        },
        timeout=20.0,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-python", type=Path, required=True)
    parser.add_argument("--candidate-python", type=Path, required=True)
    parser.add_argument("--baseline-port", type=int, default=8120)
    parser.add_argument("--candidate-port", type=int, default=8121)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    processes = [
        _start(args.baseline_python.resolve(), args.baseline_port),
        _start(args.candidate_python.resolve(), args.candidate_port),
    ]
    try:
        baseline_base = f"http://127.0.0.1:{args.baseline_port}"
        candidate_base = f"http://127.0.0.1:{args.candidate_port}"
        baseline_health = _wait(f"{baseline_base}/health")
        candidate_health = _wait(f"{candidate_base}/health")

        mismatches = []
        cases = []
        for scenario in SUPPORT_SCENARIOS:
            for version in ("v1.0-baseline", "v1.1-candidate"):
                before = _answer(baseline_base, scenario, version)
                after = _answer(candidate_base, scenario, version)
                comparable = {
                    key: before[key] for key in ("answer", "citations", "refused")
                }
                observed = {
                    key: after[key] for key in ("answer", "citations", "refused")
                }
                same = comparable == observed
                case = {
                    "scenario_id": scenario.scenario_id,
                    "version": version,
                    "same_semantics": same,
                    "before": comparable,
                    "after": observed,
                }
                cases.append(case)
                if not same:
                    mismatches.append(case)

        result = {
            "benchmark": "real upstream Haystack version comparison",
            "baseline_engine_version": baseline_health["engine_version"],
            "candidate_engine_version": candidate_health["engine_version"],
            "comparisons": len(cases),
            "mismatches": len(mismatches),
            "status": "pass" if not mismatches else "review",
            "cases": cases,
        }
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        print(text)
        if mismatches:
            raise SystemExit(1)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    main()
