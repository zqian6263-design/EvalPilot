"""Evidence-backed evaluation for EvalPilot.

This package turns sampled agent outputs into an auditable regression verdict:

- :mod:`~evalpilot.evaluation.checks` — deterministic, offline answer checks.
- :mod:`~evalpilot.evaluation.judge` — LLM-judge protocol with strict JSON
  validation and an injected async callable (no SDK, no network in tests).
- :mod:`~evalpilot.evaluation.comparison` — matched-case statistics: paired
  effect size, bootstrap confidence interval, explicit regression decision.
- :mod:`~evalpilot.evaluation.findings` — severity and evidence-linked findings.
- :mod:`~evalpilot.evaluation.service` — the boundary the API layer calls.

See ``backend/EVALUATION.md`` for usage and JSON examples.
"""

from .checks import (
    CitationPresenceCheck,
    ExpectedFactsCheck,
    RequiredRefusalCheck,
    ResponseFormatCheck,
    ToolTraceCheck,
    default_checks,
    run_deterministic_checks,
)
from .comparison import (
    DEFAULT_REGRESSION_THRESHOLD,
    ComparisonResult,
    ConfidenceInterval,
    compare_matched_cases,
    mean_confidence_interval,
    paired_effect_size,
)
from .findings import (
    build_comparison_findings,
    build_missing_evidence_findings,
    severity_for,
)
from .judge import DEFAULT_RUBRIC, JudgeError, JudgeOutput, RubricJudge, parse_judge_output
from .models import (
    AnswerFormat,
    AnswerInput,
    CheckKind,
    CheckOutcome,
    Citation,
    ComparisonDirection,
    EvidenceKind,
    ExpectedBehavior,
    Finding,
    JudgeCriterionScore,
    JudgeRequest,
    MissingEvidence,
    SampleObservation,
    Severity,
)
from .service import CaseEvaluation, ComparisonReport, EvaluationService

__all__ = [
    "DEFAULT_REGRESSION_THRESHOLD",
    "DEFAULT_RUBRIC",
    "AnswerFormat",
    "AnswerInput",
    "CaseEvaluation",
    "CheckKind",
    "CheckOutcome",
    "Citation",
    "CitationPresenceCheck",
    "ComparisonDirection",
    "ComparisonReport",
    "ComparisonResult",
    "ConfidenceInterval",
    "EvaluationService",
    "EvidenceKind",
    "ExpectedBehavior",
    "ExpectedFactsCheck",
    "Finding",
    "JudgeCriterionScore",
    "JudgeError",
    "JudgeOutput",
    "JudgeRequest",
    "MissingEvidence",
    "RequiredRefusalCheck",
    "ResponseFormatCheck",
    "RubricJudge",
    "SampleObservation",
    "Severity",
    "ToolTraceCheck",
    "build_comparison_findings",
    "build_missing_evidence_findings",
    "compare_matched_cases",
    "default_checks",
    "mean_confidence_interval",
    "paired_effect_size",
    "parse_judge_output",
    "run_deterministic_checks",
    "severity_for",
]
