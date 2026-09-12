"""Pydantic v2 domain models.

Field names and enum values are frozen by ``docs/INTERFACES.md``. Do not rename
or reorder contract fields here without updating that document first.
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


# --- Response envelopes -----------------------------------------------------


class RunDetail(_Model):
    """``GET /runs/{run_id}`` -> Run with test cases and evidence summaries."""

    run: Run
    test_cases: list[TestCase]
    evidence: list[Evidence]
    evidence_count: int
    finding_count: int
    event_count: int
