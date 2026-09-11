"""Evaluation boundary for EvalPilot.

The runner depends only on :class:`~evalpilot.orchestration_eval.service.EvaluationService`
and its :class:`~evalpilot.orchestration_eval.service.EvaluationOutcome`. Replacing the
deterministic checks with the full causal-evaluation pipeline (rubric LLM
judging, repeated sampling, significance testing) is a change confined to this
package plus the constructor call in :mod:`evalpilot.runner`.

Not implemented in the MVP, by design:

- LLM judging — see :class:`~evalpilot.orchestration_eval.service.JudgeHook`.
- Repeated sampling and variance estimates.
- Cross-version statistical significance testing.
"""

from evalpilot.orchestration_eval.checks import CaseEvaluation, CheckOutcome, evaluate_case
from evalpilot.orchestration_eval.compare import (
    RegressionComparison,
    compare_matched_cases,
    summarize_metrics,
)
from evalpilot.orchestration_eval.findings import build_findings
from evalpilot.orchestration_eval.service import (
    EvaluationOutcome,
    EvaluationService,
    JudgeHook,
)

__all__ = [
    "CaseEvaluation",
    "CheckOutcome",
    "EvaluationOutcome",
    "EvaluationService",
    "JudgeHook",
    "RegressionComparison",
    "build_findings",
    "compare_matched_cases",
    "evaluate_case",
    "summarize_metrics",
]

