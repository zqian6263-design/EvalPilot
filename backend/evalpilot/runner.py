"""Asynchronous run state machine.

Drives a run through ``queued -> planning -> executing -> evaluating -> completed``
(``failed`` / ``cancelled`` on the other paths), persisting every transition as a
sequenced event so the UI can follow progress.

The runner deliberately contains no evaluation logic: it hands the executed
cases to :class:`~evalpilot.evaluation.service.EvaluationService` and persists
whatever that service returns.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from evalpilot.clock import utc_now
from evalpilot.config import Settings
from evalpilot.db import Database
from evalpilot.evaluation.service import EvaluationService, JudgeHook
from evalpilot.evaluator import persist_evidence
from evalpilot.executor import execute_case
from evalpilot.models import (
    TERMINAL_RUN_STATUSES,
    Evidence,
    EventType,
    Run,
    RunStatus,
    TestCase,
)
from evalpilot.planner import (
    PlannerError,
    build_cases,
    plan_case_count,
    risk_map,
    select_scenarios,
)
from evalpilot.repository import NotFoundError, Repository
from evalpilot.tools import ToolRegistry

logger = logging.getLogger("evalpilot.runner")

# Run states from which a transition to "cancelled" is still possible.
ACTIVE_RUN_STATUSES = frozenset(
    {
        RunStatus.QUEUED.value,
        RunStatus.PLANNING.value,
        RunStatus.EXECUTING.value,
        RunStatus.EVALUATING.value,
    }
)


class RunConflictError(RuntimeError):
    """Raised when an action is invalid for the run's current status."""


class CancelledError_(RuntimeError):
    """Raised internally when a run was cancelled mid-flight."""


class RunRunner:
    """Executes runs. One instance per application; safe for concurrent runs."""

    def __init__(
        self,
        repo: Repository,
        db: Database,
        settings: Settings,
        evaluation_service: EvaluationService | None = None,
    ) -> None:
        self.repo = repo
        self.db = db
        self.settings = settings
        self.evaluation_service = evaluation_service or EvaluationService(
            judge=JudgeHook(base_url=settings.llm_base_url, model=settings.llm_model)
        )

    # -- public API ---------------------------------------------------------

    async def start(self, run_id: str) -> Run:
        """Mark a queued run as started and schedule its execution."""
        run = self.repo.get_run(run_id)
        if run.status != RunStatus.QUEUED:
            raise RunConflictError(
                f"run {run_id} is {run.status.value}; only queued runs can be started"
            )
        asyncio.create_task(self._drive(run_id))
        return run

    def cancel(self, run_id: str) -> Run:
        """Cancel a non-terminal run."""
        run = self.repo.get_run(run_id)
        if run.status.value in TERMINAL_RUN_STATUSES:
            raise RunConflictError(
                f"run {run_id} is already {run.status.value} and cannot be cancelled"
            )
        cancelled = self.repo.set_run_status(run_id, RunStatus.CANCELLED, utc_now())
        # event type vocabulary has no run.cancelled; reuse run.failed to stay
        # within the frozen contract, and say so in the message.
        self.repo.append_event(
            run_id,
            EventType.RUN_FAILED,
            f"Run cancelled by request (status={cancelled.status.value}).",
            {"status": cancelled.status.value, "cancelled": True},
        )
        return cancelled

    # -- internals ----------------------------------------------------------

    def _check_active(self, run_id: str) -> None:
        run = self.repo.get_run(run_id)
        if run.status.value not in ACTIVE_RUN_STATUSES:
            raise CancelledError_(f"run {run_id} is {run.status.value}")

    def _is_active(self, run_id: str) -> bool:
        return self.repo.get_run(run_id).status.value in ACTIVE_RUN_STATUSES

    async def _pause(self, multiplier: float = 1.0) -> None:
        delay = self.settings.step_delay * multiplier
        if delay > 0:
            await asyncio.sleep(delay)

    async def _drive(self, run_id: str) -> None:
        try:
            await self._execute(run_id)
        except CancelledError_:
            logger.info("run %s stopped after cancellation", run_id)
        except NotFoundError as exc:
            logger.warning("run %s disappeared: %s", run_id, exc)
        except PlannerError as exc:
            self._fail(run_id, f"Planning failed: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            logger.exception("run %s failed", run_id)
            self._fail(run_id, f"{type(exc).__name__}: {exc}")

    def _fail(self, run_id: str, message: str) -> None:
        # A cancelled run is already terminal; never append to its event log.
        if not self._is_active(run_id):
            return
        self.repo.set_run_status(run_id, RunStatus.FAILED, utc_now())
        self.repo.append_event(
            run_id, EventType.RUN_FAILED, message, {"status": RunStatus.FAILED.value}
        )

    async def _execute(self, run_id: str) -> None:
        run = self.repo.get_run(run_id)
        seed, stored_case_count = self.repo.get_run_seed(run_id)
        requested_case_count = stored_case_count or None

        run = self.repo.set_run_status(run_id, RunStatus.PLANNING)
        # Resolved before planning so the event payload reports the real number.
        case_count = plan_case_count(requested_case_count, seed)
        self.repo.append_event(
            run_id,
            EventType.RUN_STARTED,
            (
                f"Run started: comparing {run.baseline_version} (baseline) against "
                f"{run.candidate_version} (candidate)."
            ),
            {
                "baseline_version": run.baseline_version,
                "candidate_version": run.candidate_version,
                "seed": seed,
                "planned_case_count": case_count,
            },
        )

        # --- planning ------------------------------------------------------
        scenarios = select_scenarios(case_count)
        cases = build_cases(run_id, case_count, seed)
        for case in cases:
            self.repo.add_test_case(case)
        self.repo.append_event(
            run_id,
            EventType.TASK_CREATED,
            f"Planner produced {len(cases)} test cases across {len(scenarios)} scenarios.",
            {
                "case_count": len(cases),
                "scenario_count": len(scenarios),
                "risk_map": risk_map(scenarios),
            },
        )
        await self._pause()

        # --- executing -----------------------------------------------------
        self._check_active(run_id)
        self.repo.set_run_status(run_id, RunStatus.EXECUTING)
        registry = ToolRegistry(enable_python=self.settings.enable_python_tool)
        evidence_by_case: dict[str, list[Evidence]] = {}

        for index, case in enumerate(cases, start=1):
            self._check_active(run_id)
            self.repo.update_test_case(case.id, "running", None)
            self.repo.append_event(
                run_id,
                EventType.TASK_STARTED,
                f"[{index}/{len(cases)}] Executing '{case.title}' ({case.category}).",
                {
                    "test_case_id": case.id,
                    "scenario_id": case.input.get("scenario_id"),
                    "version": case.version,
                    "category": case.category,
                },
            )
            await self._pause()

            result = execute_case(case, registry, self.db)
            persist_evidence(self.repo, result.evidence)
            evidence_by_case[case.id] = result.evidence
            self.repo.update_test_case(
                case.id,
                "passed" if result.output.get("answer") else "error",
                result.output,
            )
            # Cancellation can land while the case is executing, so re-check
            # before writing the post-execution events.
            self._check_active(run_id)
            self.repo.append_event(
                run_id,
                EventType.EVIDENCE_CREATED,
                f"Captured {len(result.evidence)} evidence records for '{case.title}'.",
                {
                    "test_case_id": case.id,
                    "evidence_ids": [item.id for item in result.evidence],
                    "kinds": sorted({item.kind for item in result.evidence}),
                },
            )
            self.repo.append_event(
                run_id,
                EventType.TASK_COMPLETED,
                f"[{index}/{len(cases)}] Finished '{case.title}'.",
                {
                    "test_case_id": case.id,
                    "status": "executed",
                    "latency_ms": result.output.get("latency_ms"),
                },
            )
            await self._pause(0.5)

        # --- evaluating ----------------------------------------------------
        self._check_active(run_id)
        self.repo.set_run_status(run_id, RunStatus.EVALUATING)
        await self._pause()

        executed = self.repo.list_test_cases(run_id)
        outcome = self.evaluation_service.evaluate_run(
            run_id=run_id,
            cases=executed,
            evidence_by_case=evidence_by_case,
        )

        # Case verdicts come from the evaluation service, not the executor.
        verdicts = {evaluation.test_case_id: evaluation for evaluation in outcome.cases}
        for case in executed:
            evaluation = verdicts.get(case.id)
            if evaluation is None:
                continue
            self.repo.update_test_case(
                case.id, "passed" if evaluation.passed else "failed", case.output
            )

        for finding in outcome.findings:
            self.repo.add_finding(finding)
            self.repo.append_event(
                run_id,
                EventType.FINDING_CREATED,
                f"[{finding.severity}] {finding.title}",
                {
                    "finding_id": finding.id,
                    "severity": finding.severity,
                    "confidence": finding.confidence,
                    "evidence_ids": finding.evidence_ids,
                },
            )

        self.repo.save_report(run_id, outcome.summary, outcome.metrics)

        # --- completed -----------------------------------------------------
        self._check_active(run_id)
        self.repo.set_run_status(run_id, RunStatus.COMPLETED, utc_now())
        self.repo.append_event(
            run_id,
            EventType.RUN_COMPLETED,
            outcome.summary,
            {
                "status": RunStatus.COMPLETED.value,
                "metrics": _event_metrics(outcome.metrics),
                "finding_count": len(outcome.findings),
            },
        )

    # -- background helpers -------------------------------------------------


def _event_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Trim the metrics blob to what the UI needs on the event stream."""
    keys = (
        "matched_scenarios",
        "baseline_pass_rate",
        "candidate_pass_rate",
        "baseline_score",
        "candidate_score",
        "regression_detected",
        "regressed_scenarios",
    )
    return {key: metrics[key] for key in keys if key in metrics}
