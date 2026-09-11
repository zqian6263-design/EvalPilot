"""Typed domain models for evidence-backed evaluation.

Field names for the shared domain objects (``Finding``, ``Severity``) mirror
``docs/INTERFACES.md``. Everything else in this module is internal to the
evaluation subsystem.

Conventions (from the repository contract):
- IDs are UUID strings.
- Timestamps are UTC ISO-8601.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class EvaluationModel(BaseModel):
    """Base class: rejects unknown fields, so a typo'd field name fails loudly
    instead of being silently dropped."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Severity(str, enum.Enum):
    """Severity vocabulary, matching ``docs/INTERFACES.md``."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        """Numeric rank so severities are comparable."""
        return _SEVERITY_ORDER.index(self)


_SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.INFO,
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)


class CheckKind(str, enum.Enum):
    """Which deterministic check produced an outcome."""

    FORMAT = "format"
    REFUSAL = "refusal"
    CITATION = "citation"
    FACTS = "facts"
    TOOL_TRACE = "tool_trace"


class EvidenceKind(str, enum.Enum):
    """Evidence vocabulary, matching ``docs/INTERFACES.md``."""

    TEXT = "text"
    SCREENSHOT = "screenshot"
    LOG = "log"
    CITATION = "citation"
    TRACE = "trace"
    METRIC = "metric"


class ComparisonDirection(str, enum.Enum):
    """Outcome of a matched baseline/candidate comparison."""

    IMPROVEMENT = "improvement"
    REGRESSION = "regression"
    INCONCLUSIVE = "inconclusive"


class Version(str, enum.Enum):
    """Which arm of the comparison an observation belongs to."""

    BASELINE = "baseline"
    CANDIDATE = "candidate"


# --------------------------------------------------------------------------
# Test case inputs and expectations
# --------------------------------------------------------------------------


class AnswerFormat(EvaluationModel):
    """Structural constraints the answer text must satisfy."""

    required_markers: list[str] = Field(default_factory=list)
    forbidden_markers: list[str] = Field(default_factory=list)
    min_characters: int | None = Field(default=None, ge=0)
    max_characters: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_character_window(self) -> "AnswerFormat":
        if (
            self.min_characters is not None
            and self.max_characters is not None
            and self.min_characters > self.max_characters
        ):
            raise ValueError("min_characters must not exceed max_characters")
        return self


class Citation(EvaluationModel):
    """A structured citation attached to an answer."""

    uri: str
    title: str | None = None


class AnswerInput(EvaluationModel):
    """The answer under evaluation."""

    text: str = ""
    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)


class ExpectedBehavior(EvaluationModel):
    """What a correct answer for a test case must contain or do.

    Every field is optional: an empty ``ExpectedBehavior`` means "no
    deterministic expectation", which is a legitimate baseline.
    """

    required_keywords: list[str] = Field(default_factory=list)
    require_citation: bool = False
    require_refusal: bool = False
    require_tool_trace: bool = False
    refusal_markers: list[str] = Field(default_factory=list)
    format: AnswerFormat | None = None


# --------------------------------------------------------------------------
# Observations
# --------------------------------------------------------------------------


class SampleObservation(EvaluationModel):
    """One sampled execution of one test case under one version.

    ``trial_index`` distinguishes repeated samples of the same case, which is
    what lets the comparison separate sampling noise from a real effect.
    """

    id: str
    case_id: str
    run_id: str
    version: str
    trial_index: int = Field(default=0, ge=0)
    answer: AnswerInput = Field(default_factory=AnswerInput)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


# --------------------------------------------------------------------------
# Check outcomes
# --------------------------------------------------------------------------


class CheckOutcome(EvaluationModel):
    """Result of one deterministic check against one observation."""

    kind: CheckKind
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    applicable: bool = True
    weight: float = Field(default=1.0, ge=0.0)
    evidence_ids: list[str] = Field(default_factory=list)


class MissingEvidence(EvaluationModel):
    """A required piece of evidence that an answer did not provide.

    This is the deduplicated form: repeated trials of the same case collapse
    into a single gap with an ``occurrences`` count, because "the answer cited
    nothing" is one defect per case and version, not one per trial.
    """

    case_id: str
    version: str
    kind: EvidenceKind
    detected_by: CheckKind
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    occurrences: int = Field(default=1, ge=1)


# --------------------------------------------------------------------------
# LLM judge payload
# --------------------------------------------------------------------------


class JudgeCriterionScore(EvaluationModel):
    """A per-criterion score inside a judge verdict."""

    name: str
    score: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class JudgeRequest(EvaluationModel):
    """Everything the judge needs to score one answer.

    This is also the exact payload handed to the injected async callable, so
    the callable signature stays stable if the request grows fields later.
    """

    case_id: str
    question: str
    answer_text: str
    rubric: str
    criteria: list[str] = Field(default_factory=list)
    context: str | None = None


class JudgeOutput(EvaluationModel):
    """A validated judge verdict. Constructed only from strict JSON."""

    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = ""
    criteria: list[JudgeCriterionScore] = Field(default_factory=list)

    def score_for(self, name: str) -> float | None:
        """Return the score for a named criterion, or ``None`` if absent."""
        for criterion in self.criteria:
            if criterion.name == name:
                return criterion.score
        return None


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


class Finding(EvaluationModel):
    """A reportable defect.

    ``evidence_ids`` is required and must be non-empty: a finding that cannot
    point at evidence is not a finding. See ``findings.py`` for the builders
    that enforce this at construction time.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str | None = None
    case_id: str | None = Field(default=None)
    severity: Severity
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)
    rationale: str
    recommendation: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _reject_blank_evidence_ids(self) -> "Finding":
        if not any(evidence_id.strip() for evidence_id in self.evidence_ids):
            raise ValueError("Finding.evidence_ids must contain at least one non-empty id")
        return self
