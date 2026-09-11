"""Evaluation boundary for EvalPilot.

The runner depends only on :class:`~evalpilot.evaluation.service.EvaluationService`
and its :class:`~evalpilot.evaluation.service.EvaluationOutcome`. Replacing the
deterministic checks with the full causal-evaluation pipeline (rubric LLM
judging, repeated sampling, significance testing) is a change confined to this
package plus the constructor call in :mod:`evalpilot.runner`.

Not implemented in the MVP, by design:

- LLM judging — see :class:`~evalpilot.evaluation.service.JudgeHook`.
- Repeated sampling and variance estimates.
- Cross-version statistical significance testing.
"""

from evalpilot.evaluation.checks import CaseEvaluation, CheckOutcome, evaluate_case
from evalpilot.evaluation.compare import (
    RegressionComparison,
    compare_matched_cases,
    summarize_metrics,
)
from evalpilot.evaluation.findings import build_findings
from evalpilot.evaluation.service import (
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
