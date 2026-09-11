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
    Event,
    EventType,
    Evidence,
    Finding,
    Project,
    Report,
    Run,
    RunStatus,
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
        run_id=row["run_id"],
        sequence=row["sequence"],
        type=EventType(row["type"]),
        message=row["message"],
        data=_loads(row["data"]),
        created_at=from_iso(row["created_at"]),
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
        created_at = utc_now()
        with self.db.connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS next FROM events WHERE run_id = ?",
                (run_id,),
            ).fetchone()["next"]
            conn.execute(
                """
                INSERT INTO events (run_id, sequence, type, message, data, created_at)
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
                "SELECT * FROM events WHERE run_id = ? AND sequence > ? ORDER BY sequence",
                (run_id, after),
            ).fetchall()
        return [_event(row) for row in rows]

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
                "SELECT COUNT(*) AS n FROM events WHERE run_id = ?", (run_id,)
            ).fetchone()
        return int(row["n"])
