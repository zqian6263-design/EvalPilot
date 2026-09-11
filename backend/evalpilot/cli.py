"""Command-line entry points.

``python -m evalpilot.cli seed``   create the deterministic demo project and run
``python -m evalpilot.cli run``    seed, execute, and print the regression verdict
``python -m evalpilot.cli serve``  start the API with uvicorn
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from evalpilot.app import build_container, create_app
from evalpilot.demo import ensure_demo_project, scripted_regressions
from evalpilot.models import RunStatus


def _cmd_seed(args: argparse.Namespace) -> int:
    container = build_container()
    project, run = ensure_demo_project(container.repo, container.settings)
    payload = {
        "project_id": project.id,
        "run_id": run.id if run else None,
        "baseline_version": run.baseline_version if run else None,
        "candidate_version": run.candidate_version if run else None,
        "db_path": str(container.settings.db_path),
        "next": f"POST /api/runs/{run.id}/start" if run else None,
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    container = build_container()
    _, run = ensure_demo_project(container.repo, container.settings)
    assert run is not None

    async def _drive() -> None:
        if run.status == RunStatus.QUEUED:
            await container.runner.start(run.id)
        for _ in range(2000):
            await asyncio.sleep(0.05)
            if container.repo.get_run(run.id).status.is_terminal:
                return
        raise TimeoutError(f"run {run.id} did not finish")

    asyncio.run(_drive())

    finished = container.repo.get_run(run.id)
    report = container.repo.get_report(run.id)
    print(f"run {finished.id} -> {finished.status.value}")
    print()
    print(report.summary)
    print()
    print("metrics:", json.dumps(report.metrics, indent=2))
    print()
    print(f"findings ({len(report.findings)}):")
    for finding in report.findings:
        print(f"  [{finding.severity}] {finding.title} (confidence={finding.confidence})")

    expected = set(scripted_regressions())
    detected = set(report.metrics.get("regressed_scenarios", []))
    missing = expected - detected
    if missing:
        print(
            f"\nFAIL: scripted regressions were not detected: {sorted(missing)}",
            file=sys.stderr,
        )
        return 1
    print(f"\nOK: all {len(expected)} scripted regressions detected.")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evalpilot", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="create the deterministic demo project and run")

    run_parser = sub.add_parser("run", help="seed and execute the demo run end to end")
    run_parser.add_argument(
        "--no-fail-on-missing-regression",
        action="store_true",
        help="exit 0 even if a scripted regression goes undetected",
    )

    serve = sub.add_parser("serve", help="start the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--log-level", default="info")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seed":
        return _cmd_seed(args)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "serve":
        return _cmd_serve(args)
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
