"""Evaluation boundary for EvalPilot.

The runner depends on exactly one thing here: :class:`EvaluationService` and
its :meth:`~evalpilot.orchestration_eval.service.EvaluationService.evaluate_run_async`.

This package used to hold a second, weaker evaluator — pass/fail keyword checks
with a per-scenario ``changed`` flag and no notion of sampling error. That layer
has been retired. The evaluation logic now lives in :mod:`evalpilot.evaluation`,
which does matched-case scoring, repeated sampling, a paired effect size, a
bootstrap confidence interval, and an explicit regression decision. What remains
here is the seam: mapping backend rows into the engine's models, turning the
engine's comparison into the case verdicts and findings the backend persists,
and reporting the engine's numbers as metrics.

Keeping the seam separate from the engine leaves the engine a pure library with
no database or HTTP knowledge, and leaves the runner a single stable method to
call.
"""

from evalpilot.orchestration_eval.service import (
    CaseVerdict,
    EvaluationOutcome,
    EvaluationService,
    count_by_severity,
    summarize,
)

__all__ = [
    "CaseVerdict",
    "EvaluationOutcome",
    "EvaluationService",
    "count_by_severity",
    "summarize",
]
