"""Pydantic v2 domain models.

Field names and enum values are frozen by ``docs/INTERFACES.md`` and
``docs/V2_INTERFACES.md``. Do not rename or reorder contract fields here
without updating those documents first.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["normal", "boundary", "adversarial", "regression"]
CaseVersion = Literal["baseline", "candidate"]
CaseStatus = Literal["pending", "running", "passed", "failed", "error"]
EvidenceKind = Literal["text", "screenshot", "log", "citation", "trace", "metric"]
Severity = Literal["info", "low", "medium", "high", "critical"]

TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})


class RunStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self.value in TERMINAL_RUN_STATUSES


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    EVIDENCE_CREATED = "evidence.created"
    TASK_COMPLETED = "task.completed"
    FINDING_CREATED = "finding.created"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Project(_Model):
    id: str
    name: str
    scenario: str
    created_at: datetime


class Run(_Model):
    id: str
    project_id: str
    baseline_version: str
    candidate_version: str
    status: RunStatus
    case_count: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class TestCase(_Model):
    id: str
    run_id: str
    title: str
    category: Category
    input: dict[str, Any]
    expected: dict[str, Any]
    difficulty: float = Field(ge=0.0, le=1.0)
    status: CaseStatus
    version: CaseVersion
    output: dict[str, Any] | None = None


class Evidence(_Model):
    id: str
    run_id: str
    test_case_id: str
    kind: EvidenceKind
    uri: str | None = None
    payload: dict[str, Any]
    created_at: datetime


class Finding(_Model):
    id: str
    run_id: str
    test_case_id: str | None = None
    severity: Severity
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str]
    recommendation: str | None = None


class Report(_Model):
    id: str
    run_id: str
    summary: str
    metrics: dict[str, Any]
    findings: list[Finding]
    generated_at: datetime


class Event(_Model):
    """Progress event, matching the payload in ``docs/INTERFACES.md``."""

    run_id: str
    sequence: int
    type: EventType
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# --- V2: autonomous investigation -------------------------------------------
# Field names are frozen by ``docs/V2_INTERFACES.md``. The event envelope is
# reused as-is: ``Event.run_id`` carries the investigation id, so the V2 stream
# is the same payload shape the run stream already uses.


class InvestigationStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    INVESTIGATING = "investigating"
    REPLAYING = "replaying"
    DECIDING = "deciding"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self.value in {"completed", "failed"}


class InvestigationStepKind(StrEnum):
    RISK = "risk"
    MEMORY = "memory"
    PROBE = "probe"
    TOOL = "tool"
    OBSERVATION = "observation"
    COUNTERFACTUAL = "counterfactual"
    DECISION = "decision"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


RiskLevel = Literal["low", "medium", "high", "critical"]
DecisionVerdict = Literal["allow", "review", "block"]
CounterfactualVerdict = Literal["root_cause", "partial", "no_effect", "inconclusive"]


class Investigation(_Model):
    id: str
    run_id: str
    objective: str
    status: InvestigationStatus
    summary: str
    risk_level: RiskLevel
    decision_verdict: DecisionVerdict
    created_at: datetime
    completed_at: datetime | None = None


class InvestigationStep(_Model):
    id: str
    investigation_id: str
    parent_id: str | None = None
    sequence: int
    kind: InvestigationStepKind
    title: str
    status: StepStatus
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class HistoricalIncident(_Model):
    """A past incident recalled by memory search.

    ``id`` is a stable slug, not a UUID: incidents are authored fixture data
    that a report cites by name, and a slug keeps those citations readable.

    ``intervention`` is the change that fixed the incident. It is what lets the
    investigation turn "we have seen this before" into a concrete counterfactual
    to replay, so it is persisted rather than recomputed from the tag list.
    """

    id: str
    title: str
    symptoms: list[str]
    tags: list[str]
    root_cause: str
    resolution: str
    intervention: str | None = None
    guard_scenario_id: str | None = None
    occurred_at: datetime


class MemoryMatch(_Model):
    incident_id: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str
    matched_terms: list[str]


class CounterfactualExperiment(_Model):
    id: str
    investigation_id: str
    scenario_id: str
    intervention: str
    original_score: float
    counterfactual_score: float
    delta: float
    confidence: float = Field(ge=0.0, le=1.0)
    verdict: CounterfactualVerdict
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str
    created_at: datetime


class ReleaseDecision(_Model):
    """The release gate's verdict.

    ``blocking_findings`` holds ids of the run's :class:`Finding` rows that are
    holding the release, not evidence ids: the run layer already owns the
    finding → evidence link, and naming a finding is what lets a reviewer open
    the run report and read the rationale. What this decision adds is the
    verdict, the risk level, and the actions — the evidence linkage is carried
    by the findings themselves and by the decision step's ``evidence_ids``.
    """

    verdict: DecisionVerdict
    risk_level: RiskLevel
    summary: str
    blocking_findings: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    generated_at: datetime


# --- Request bodies ---------------------------------------------------------


class ProjectCreate(_Model):
    name: str
    scenario: str


class RunCreate(_Model):
    project_id: str
    baseline_version: str
    candidate_version: str
    case_count: int | None = Field(default=None, ge=1, le=200)
    seed: int | None = None


class InvestigationCreate(_Model):
    run_id: str
    objective: str = Field(min_length=1)


# --- Response envelopes -----------------------------------------------------


class RunDetail(_Model):
    """``GET /runs/{run_id}`` -> Run with test cases and evidence summaries."""

    run: Run
    test_cases: list[TestCase]
    evidence: list[Evidence]
    evidence_count: int
    finding_count: int
    event_count: int


class ReleaseGate(_Model):
    """Machine-readable CI gate derived from one completed run report."""

    run_id: str
    decision: Literal["allow", "review", "block"]
    exit_code: int
    regression_detected: bool
    regression_confirmed: bool
    baseline_pass_rate: float
    candidate_pass_rate: float
    mean_difference: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    threshold: float | None = None
    reasons: list[str] = Field(default_factory=list)
    report_url: str

class InvestigationDetail(_Model):
    """``GET /investigations/{id}`` -> the full investigation artifact."""

    investigation: Investigation
    steps: list[InvestigationStep]
    memory_matches: list[MemoryMatch]
    counterfactuals: list[CounterfactualExperiment]
    decision: ReleaseDecision | None = None


class IncidentQueryResult(_Model):
    """``GET /memory/incidents`` -> incidents, plus matches when a query is given.

    With no ``query`` every seeded incident is returned in fixture order and
    ``matches`` is empty. With a query, ``matches`` carries the scored recall in
    descending order and ``incidents`` is the matched subset in that same order,
    so a client can render either view without re-sorting.
    """

    query: str | None = None
    tag: str | None = None
    incidents: list[HistoricalIncident]
    matches: list[MemoryMatch]


class InvestigationDemo(_Model):
    """``GET /demo/investigation`` -> deterministic demo metadata, no side effects."""

    entry_run_id: str | None = None
    run_status: str | None = None
    investigation_id: str | None = None
    investigation_status: str | None = None
    incident_count: int
    interventions: list[str]
    incidents: list[dict[str, Any]]
    steps: list[dict[str, str]]
    how_to_run: list[str]
