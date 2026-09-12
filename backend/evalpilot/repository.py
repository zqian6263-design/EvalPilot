"""Repository layer: all SQL reads and writes live here.

Rows are converted to and from the Pydantic models in :mod:`evalpilot.models`
so that the rest of the application never touches ``sqlite3.Row`` directly.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from evalpilot.clock import from_iso, new_id, to_iso, utc_now
from evalpilot.db import Database
from evalpilot.models import (
    CounterfactualExperiment,
    Event,
    EventType,
    Evidence,
    Finding,
    HistoricalIncident,
    Investigation,
    InvestigationStatus,
    InvestigationStep,
    InvestigationStepKind,
    MemoryMatch,
    Project,
    ReleaseDecision,
    Report,
    Run,
    RunStatus,
    StepStatus,
    TestCase,
)


class NotFoundError(LookupError):
    """Raised when a referenced entity does not exist."""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(raw: str) -> Any:
    return json.loads(raw)


# --- row mappers ------------------------------------------------------------


def _project(row: Any) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        scenario=row["scenario"],
        created_at=from_iso(row["created_at"]),
    )


def _run(row: Any) -> Run:
    return Run(
        id=row["id"],
        project_id=row["project_id"],
        baseline_version=row["baseline_version"],
        candidate_version=row["candidate_version"],
        status=RunStatus(row["status"]),
        case_count=row["case_count"],
        created_at=from_iso(row["created_at"]),
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
    )


def _test_case(row: Any) -> TestCase:
    return TestCase(
        id=row["id"],
        run_id=row["run_id"],
        title=row["title"],
        category=row["category"],
        input=_loads(row["input"]),
        expected=_loads(row["expected"]),
        difficulty=row["difficulty"],
        status=row["status"],
        version=row["version"],
        output=_loads(row["output"]) if row["output"] else None,
    )


def _evidence(row: Any) -> Evidence:
    return Evidence(
        id=row["id"],
        run_id=row["run_id"],
        test_case_id=row["test_case_id"],
        kind=row["kind"],
        uri=row["uri"],
        payload=_loads(row["payload"]),
        created_at=from_iso(row["created_at"]),
    )


def _finding(row: Any) -> Finding:
    return Finding(
        id=row["id"],
        run_id=row["run_id"],
        test_case_id=row["test_case_id"],
        severity=row["severity"],
        title=row["title"],
        description=row["description"],
        confidence=row["confidence"],
        evidence_ids=_loads(row["evidence_ids"]),
        recommendation=row["recommendation"],
    )


def _event(row: Any) -> Event:
    return Event(
        run_id=row["entity_id"],
        sequence=row["sequence"],
        type=EventType(row["type"]),
        message=row["message"],
        data=_loads(row["data"]),
        created_at=from_iso(row["created_at"]),
    )


# --- V2 row mappers ---------------------------------------------------------
# The event envelope is shared with runs: for an investigation the row's
# ``run_id`` holds the investigation id, so ``_event`` above maps both streams.


def _investigation(row: Any) -> Investigation:
    return Investigation(
        id=row["id"],
        run_id=row["run_id"],
        objective=row["objective"],
        status=InvestigationStatus(row["status"]),
        summary=row["summary"],
        risk_level=row["risk_level"],
        decision_verdict=row["decision_verdict"],
        created_at=from_iso(row["created_at"]),
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
    )


def _step(row: Any) -> InvestigationStep:
    return InvestigationStep(
        id=row["id"],
        investigation_id=row["investigation_id"],
        parent_id=row["parent_id"],
        sequence=row["seq"],
        kind=InvestigationStepKind(row["kind"]),
        title=row["title"],
        status=StepStatus(row["status"]),
        detail=row["detail"],
        data=_loads(row["data"]),
        evidence_ids=_loads(row["evidence_ids"]),
        created_at=from_iso(row["created_at"]),
        completed_at=from_iso(row["completed_at"]) if row["completed_at"] else None,
    )


def _incident(row: Any) -> HistoricalIncident:
    return HistoricalIncident(
        id=row["id"],
        title=row["title"],
        symptoms=_loads(row["symptoms"]),
        tags=_loads(row["tags"]),
        root_cause=row["root_cause"],
        resolution=row["resolution"],
        intervention=row["intervention"],
        guard_scenario_id=row["guard_scenario_id"],
        occurred_at=from_iso(row["occurred_at"]),
    )


def _memory_match(row: Any) -> MemoryMatch:
    return MemoryMatch(
        incident_id=row["incident_id"],
        score=row["score"],
        reason=row["reason"],
        matched_terms=_loads(row["matched_terms"]),
    )


def _counterfactual(row: Any) -> CounterfactualExperiment:
    return CounterfactualExperiment(
        id=row["id"],
        investigation_id=row["investigation_id"],
        scenario_id=row["scenario_id"],
        intervention=row["intervention"],
        original_score=row["original_score"],
        counterfactual_score=row["counterfactual_score"],
        delta=row["delta"],
        confidence=row["confidence"],
        verdict=row["verdict"],
        evidence_ids=_loads(row["evidence_ids"]),
        rationale=row["rationale"],
        created_at=from_iso(row["created_at"]),
    )


def _decision(row: Any) -> ReleaseDecision:
    return ReleaseDecision(
        verdict=row["verdict"],
        risk_level=row["risk_level"],
        summary=row["summary"],
        blocking_findings=_loads(row["blocking_findings"]),
        recommended_actions=_loads(row["recommended_actions"]),
        confidence=row["confidence"],
        generated_at=from_iso(row["generated_at"]),
    )


# --- repository -------------------------------------------------------------


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- projects -----------------------------------------------------------

    def create_project(self, name: str, scenario: str) -> Project:
        project = Project(
            id=new_id(), name=name, scenario=scenario, created_at=utc_now()
        )
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, scenario, created_at) VALUES (?, ?, ?, ?)",
                (
                    project.id,
                    project.name,
                    project.scenario,
                    to_iso(project.created_at),
                ),
            )
        return project

    def get_project(self, project_id: str) -> Project:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"project {project_id} not found")
        return _project(row)

    def list_projects(self) -> list[Project]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY created_at, id"
            ).fetchall()
        return [_project(row) for row in rows]

    # -- runs ---------------------------------------------------------------

    def create_run(
        self,
        project_id: str,
        baseline_version: str,
        candidate_version: str,
        seed: int,
        case_count: int,
    ) -> Run:
        run = Run(
            id=new_id(),
            project_id=project_id,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
            status=RunStatus.QUEUED,
            case_count=case_count,
            created_at=utc_now(),
            completed_at=None,
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, project_id, baseline_version, candidate_version,
                    status, created_at, completed_at, seed, case_count
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    run.id,
                    run.project_id,
                    run.baseline_version,
                    run.candidate_version,
                    run.status.value,
                    to_iso(run.created_at),
                    seed,
                    case_count,
                ),
            )
        return run

    def get_run(self, run_id: str) -> Run:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"run {run_id} not found")
        return _run(row)

    def get_run_seed(self, run_id: str) -> tuple[int, int]:
        """Return ``(seed, case_count)`` used to plan this run."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT seed, case_count FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"run {run_id} not found")
        return int(row["seed"] or 0), int(row["case_count"] or 0)

    def list_runs(self) -> list[Run]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, id"
            ).fetchall()
        return [_run(row) for row in rows]

    def set_run_status(
        self, run_id: str, status: RunStatus, completed_at: datetime | None = None
    ) -> Run:
        if completed_at is None and status in (RunStatus.COMPLETED, RunStatus.FAILED):
            completed_at = utc_now()
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE runs SET status = ?, completed_at = ? WHERE id = ?",
                (
                    status.value,
                    to_iso(completed_at) if completed_at else None,
                    run_id,
                ),
            )
        return self.get_run(run_id)

    # -- test cases ---------------------------------------------------------

    def add_test_case(self, case: TestCase) -> TestCase:
        with self.db.connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS next FROM test_cases WHERE run_id = ?",
                (case.run_id,),
            ).fetchone()["next"]
            conn.execute(
                """
                INSERT INTO test_cases (
                    id, run_id, seq, title, category, input, expected,
                    difficulty, status, version, output
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case.id,
                    case.run_id,
                    seq,
                    case.title,
                    case.category,
                    _dumps(case.input),
                    _dumps(case.expected),
                    case.difficulty,
                    case.status,
                    case.version,
                    _dumps(case.output) if case.output is not None else None,
                ),
            )
        return case

    def update_test_case(
        self, case_id: str, status: CaseStatus, output: dict[str, Any] | None
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE test_cases SET status = ?, output = ? WHERE id = ?",
                (status, _dumps(output) if output is not None else None, case_id),
            )
        return self.get_test_case(case_id)

    def get_test_case(self, case_id: str) -> TestCase:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM test_cases WHERE id = ?", (case_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"test case {case_id} not found")
        return _test_case(row)

    def list_test_cases(self, run_id: str) -> list[TestCase]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM test_cases WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        return [_test_case(row) for row in rows]

    # -- evidence -----------------------------------------------------------

    def add_evidence(self, evidence: Evidence) -> Evidence:
        with self.db.connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS next FROM evidence WHERE run_id = ?",
                (evidence.run_id,),
            ).fetchone()["next"]
            conn.execute(
                """
                INSERT INTO evidence (
                    id, run_id, test_case_id, seq, kind, uri, payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id,
                    evidence.run_id,
                    evidence.test_case_id,
                    seq,
                    evidence.kind,
                    evidence.uri,
                    _dumps(evidence.payload),
                    to_iso(evidence.created_at),
                ),
            )
        return evidence

    def list_evidence(self, run_id: str) -> list[Evidence]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM evidence WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        return [_evidence(row) for row in rows]

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        """Return one persisted evidence row, or ``None`` when it is absent."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM evidence WHERE id = ?", (evidence_id,)
            ).fetchone()
        return _evidence(row) if row is not None else None

    # -- findings -----------------------------------------------------------

    def add_finding(self, finding: Finding) -> Finding:
        with self.db.connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS next FROM findings WHERE run_id = ?",
                (finding.run_id,),
            ).fetchone()["next"]
            conn.execute(
                """
                INSERT INTO findings (
                    id, run_id, test_case_id, seq, severity, title,
                    description, confidence, evidence_ids, recommendation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.id,
                    finding.run_id,
                    finding.test_case_id,
                    seq,
                    finding.severity,
                    finding.title,
                    finding.description,
                    finding.confidence,
                    _dumps(finding.evidence_ids),
                    finding.recommendation,
                ),
            )
        return finding

    def list_findings(self, run_id: str) -> list[Finding]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM findings WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        return [_finding(row) for row in rows]

    # -- reports ------------------------------------------------------------

    def save_report(self, run_id: str, summary: str, metrics: dict[str, Any]) -> Report:
        report = Report(
            id=new_id(),
            run_id=run_id,
            summary=summary,
            metrics=metrics,
            findings=[],
            generated_at=utc_now(),
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (id, run_id, summary, metrics, generated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    summary = excluded.summary,
                    metrics = excluded.metrics,
                    generated_at = excluded.generated_at
                """,
                (
                    report.id,
                    run_id,
                    summary,
                    _dumps(metrics),
                    to_iso(report.generated_at),
                ),
            )
        return self.get_report(run_id)

    def get_report(self, run_id: str) -> Report:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"report for run {run_id} not found")
        return Report(
            id=row["id"],
            run_id=row["run_id"],
            summary=row["summary"],
            metrics=_loads(row["metrics"]),
            findings=self.list_findings(run_id),
            generated_at=from_iso(row["generated_at"]),
        )

    # -- events -------------------------------------------------------------

    def append_event(
        self,
        run_id: str,
        type_: EventType,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> Event:
        """Append to a stream. ``run_id`` is the id of the owning entity.

        The column is ``entity_id`` — the envelope is shared between a run's
        events and an investigation's (``docs/V2_INTERFACES.md``), so the same
        reader serves both. The parameter keeps its contract name because
        ``Event.run_id`` is the frozen field.
        """
        created_at = utc_now()
        with self.db.connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next FROM events WHERE entity_id = ?",
                (run_id,),
            ).fetchone()["next"]
            conn.execute(
                """
                INSERT INTO events (entity_id, sequence, type, message, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    seq,
                    type_.value,
                    message,
                    _dumps(data or {}),
                    to_iso(created_at),
                ),
            )
        return Event(
            run_id=run_id,
            sequence=seq,
            type=type_,
            message=message,
            data=data or {},
            created_at=created_at,
        )

    def list_events(self, run_id: str, after: int = 0) -> list[Event]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE entity_id = ? AND sequence > ? ORDER BY sequence",
                (run_id, after),
            ).fetchall()
        return [_event(row) for row in rows]

    # -- historical incidents (V2) ------------------------------------------

    def add_historical_incident(
        self, incident: HistoricalIncident, seq: int
    ) -> bool:
        """Insert an incident unless it already exists.

        Returns ``True`` when a row was written. Idempotent on purpose: seeding
        runs on every container build, and an existing investigation's recalled
        incidents must not shift under it when a fixture is edited.
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO historical_incidents (
                    id, seq, title, symptoms, tags, root_cause, resolution,
                    intervention, guard_scenario_id, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident.id,
                    seq,
                    incident.title,
                    _dumps(incident.symptoms),
                    _dumps(incident.tags),
                    incident.root_cause,
                    incident.resolution,
                    incident.intervention,
                    incident.guard_scenario_id,
                    to_iso(incident.occurred_at),
                ),
            )
            return cursor.rowcount > 0

    def get_historical_incident(self, incident_id: str) -> HistoricalIncident:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM historical_incidents WHERE id = ?", (incident_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"historical incident {incident_id} not found")
        return _incident(row)

    def list_historical_incidents(self) -> list[HistoricalIncident]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM historical_incidents ORDER BY seq, id"
            ).fetchall()
        return [_incident(row) for row in rows]

    def count_historical_incidents(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM historical_incidents"
            ).fetchone()
        return int(row["n"])

    # -- investigations (V2) ------------------------------------------------

    def create_investigation(
        self, run_id: str, objective: str
    ) -> Investigation:
        """Create a queued investigation for ``run_id``.

        Idempotent: a run has at most one investigation, so re-posting the same
        ``run_id`` returns the existing record instead of starting a second
        narrative over the same evidence.
        """
        existing = self.find_investigation_for_run(run_id)
        if existing is not None:
            return existing

        investigation = Investigation(
            id=new_id(),
            run_id=run_id,
            objective=objective,
            status=InvestigationStatus.QUEUED,
            summary="",
            risk_level="low",
            decision_verdict="allow",
            created_at=utc_now(),
            completed_at=None,
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO investigations (
                    id, run_id, objective, status, summary, risk_level,
                    decision_verdict, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    investigation.id,
                    investigation.run_id,
                    investigation.objective,
                    investigation.status.value,
                    investigation.summary,
                    investigation.risk_level,
                    investigation.decision_verdict,
                    to_iso(investigation.created_at),
                ),
            )
        return investigation

    def get_investigation(self, investigation_id: str) -> Investigation:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM investigations WHERE id = ?", (investigation_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"investigation {investigation_id} not found")
        return _investigation(row)

    def find_investigation_for_run(self, run_id: str) -> Investigation | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM investigations WHERE run_id = ? ORDER BY created_at, id LIMIT 1",
                (run_id,),
            ).fetchone()
        return _investigation(row) if row is not None else None

    def list_investigations(self) -> list[Investigation]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM investigations ORDER BY created_at DESC, id"
            ).fetchall()
        return [_investigation(row) for row in rows]

    def update_investigation(
        self,
        investigation_id: str,
        *,
        status: InvestigationStatus | None = None,
        summary: str | None = None,
        risk_level: str | None = None,
        decision_verdict: str | None = None,
        completed_at: datetime | None = None,
        clear_completed_at: bool = False,
    ) -> Investigation:
        """Patch the mutable fields of an investigation."""
        assignments: list[str] = []
        values: list[Any] = []
        if status is not None:
            assignments.append("status = ?")
            values.append(status.value)
        if summary is not None:
            assignments.append("summary = ?")
            values.append(summary)
        if risk_level is not None:
            assignments.append("risk_level = ?")
            values.append(risk_level)
        if decision_verdict is not None:
            assignments.append("decision_verdict = ?")
            values.append(decision_verdict)
        if clear_completed_at:
            assignments.append("completed_at = NULL")
        elif completed_at is not None:
            assignments.append("completed_at = ?")
            values.append(to_iso(completed_at))

        if assignments:
            values.append(investigation_id)
            with self.db.connect() as conn:
                conn.execute(
                    f"UPDATE investigations SET {', '.join(assignments)} WHERE id = ?",
                    tuple(values),
                )
        return self.get_investigation(investigation_id)

    # -- investigation steps (V2) -------------------------------------------

    def add_step(self, step: InvestigationStep) -> InvestigationStep:
        """Insert a step. The caller owns ``sequence``.

        Unlike test cases and evidence, a step's sequence is decided by the
        investigation engine: steps are a narrative, and their order is part of
        what the report asserts, so it is not left to insertion order.

        A step created already-``completed`` gets a completion timestamp here.
        The engine builds most steps in one shot, and a port that left
        ``completed_at`` null on a finished step would report a duration of
        "never" to anything reading the timeline.
        """
        completed_at = step.completed_at
        if completed_at is None and step.status is StepStatus.COMPLETED:
            completed_at = utc_now()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO investigation_steps (
                    id, investigation_id, parent_id, seq, kind, title, status,
                    detail, data, evidence_ids, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step.id,
                    step.investigation_id,
                    step.parent_id,
                    step.sequence,
                    step.kind.value,
                    step.title,
                    step.status.value,
                    step.detail,
                    _dumps(step.data),
                    _dumps(step.evidence_ids),
                    to_iso(step.created_at),
                    to_iso(completed_at) if completed_at else None,
                ),
            )
        return step.model_copy(update={"completed_at": completed_at})

    def update_step(
        self,
        step_id: str,
        *,
        status: StepStatus,
        detail: str | None = None,
        completed_at: datetime | None = None,
    ) -> InvestigationStep:
        with self.db.connect() as conn:
            if detail is None:
                conn.execute(
                    "UPDATE investigation_steps SET status = ?, completed_at = ? WHERE id = ?",
                    (
                        status.value,
                        to_iso(completed_at) if completed_at else None,
                        step_id,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE investigation_steps SET status = ?, detail = ?, "
                    "completed_at = ? WHERE id = ?",
                    (
                        status.value,
                        detail,
                        to_iso(completed_at) if completed_at else None,
                        step_id,
                    ),
                )
        return self.get_step(step_id)

    def save_step_data(self, step_id: str, data: dict[str, Any]) -> InvestigationStep:
        """Replace a step's ``data`` payload.

        Separate from :meth:`update_step` because the two are genuinely
        different writes: ``update_step`` moves a step through its lifecycle
        (status, detail, completion time), while this one amends the structured
        payload a finished step carries.

        Live mode uses it to *merge* model commentary into a step's ``data``
        after the deterministic keys were written. The caller is responsible
        for merging rather than overwriting, which is what keeps a measured
        value from being rewritten by a model.
        """
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE investigation_steps SET data = ? WHERE id = ?",
                (_dumps(data), step_id),
            )
        return self.get_step(step_id)

    def get_step(self, step_id: str) -> InvestigationStep:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM investigation_steps WHERE id = ?", (step_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"investigation step {step_id} not found")
        return _step(row)

    def list_steps(self, investigation_id: str) -> list[InvestigationStep]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM investigation_steps WHERE investigation_id = ? "
                "ORDER BY seq, id",
                (investigation_id,),
            ).fetchall()
        return [_step(row) for row in rows]

    # -- recalled memory (V2) -----------------------------------------------

    def add_memory_match(
        self, investigation_id: str, match: MemoryMatch, seq: int
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_matches (
                    investigation_id, incident_id, seq, score, reason, matched_terms
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id, incident_id) DO NOTHING
                """,
                (
                    investigation_id,
                    match.incident_id,
                    seq,
                    match.score,
                    match.reason,
                    _dumps(match.matched_terms),
                ),
            )

    def list_memory_matches(self, investigation_id: str) -> list[MemoryMatch]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_matches WHERE investigation_id = ? "
                "ORDER BY seq, incident_id",
                (investigation_id,),
            ).fetchall()
        return [_memory_match(row) for row in rows]

    # -- counterfactual experiments (V2) ------------------------------------

    def add_counterfactual(
        self, experiment: CounterfactualExperiment
    ) -> CounterfactualExperiment:
        with self.db.connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 AS next FROM counterfactual_experiments "
                "WHERE investigation_id = ?",
                (experiment.investigation_id,),
            ).fetchone()["next"]
            conn.execute(
                """
                INSERT INTO counterfactual_experiments (
                    id, investigation_id, seq, scenario_id, intervention,
                    original_score, counterfactual_score, delta, confidence,
                    verdict, evidence_ids, rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment.id,
                    experiment.investigation_id,
                    seq,
                    experiment.scenario_id,
                    experiment.intervention,
                    experiment.original_score,
                    experiment.counterfactual_score,
                    experiment.delta,
                    experiment.confidence,
                    experiment.verdict,
                    _dumps(experiment.evidence_ids),
                    experiment.rationale,
                    to_iso(experiment.created_at),
                ),
            )
        return experiment

    def list_counterfactuals(
        self, investigation_id: str
    ) -> list[CounterfactualExperiment]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM counterfactual_experiments WHERE investigation_id = ? "
                "ORDER BY seq, id",
                (investigation_id,),
            ).fetchall()
        return [_counterfactual(row) for row in rows]

    # -- release decision (V2) ----------------------------------------------

    def save_decision(
        self, investigation_id: str, decision: ReleaseDecision
    ) -> ReleaseDecision:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO release_decisions (
                    investigation_id, verdict, risk_level, summary,
                    blocking_findings, recommended_actions, confidence, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id) DO UPDATE SET
                    verdict = excluded.verdict,
                    risk_level = excluded.risk_level,
                    summary = excluded.summary,
                    blocking_findings = excluded.blocking_findings,
                    recommended_actions = excluded.recommended_actions,
                    confidence = excluded.confidence,
                    generated_at = excluded.generated_at
                """,
                (
                    investigation_id,
                    decision.verdict,
                    decision.risk_level,
                    decision.summary,
                    _dumps(decision.blocking_findings),
                    _dumps(decision.recommended_actions),
                    decision.confidence,
                    to_iso(decision.generated_at),
                ),
            )
        return decision

    def get_decision(self, investigation_id: str) -> ReleaseDecision | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM release_decisions WHERE investigation_id = ?",
                (investigation_id,),
            ).fetchone()
        return _decision(row) if row is not None else None

    # -- counts -------------------------------------------------------------

    def count_evidence(self, run_id: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM evidence WHERE run_id = ?", (run_id,)
            ).fetchone()
        return int(row["n"])

    def count_findings(self, run_id: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM findings WHERE run_id = ?", (run_id,)
            ).fetchone()
        return int(row["n"])

    def count_events(self, run_id: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE entity_id = ?", (run_id,)
            ).fetchone()
        return int(row["n"])
