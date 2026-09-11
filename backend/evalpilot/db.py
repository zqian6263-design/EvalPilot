"""SQLite storage: connection factory, schema, and artifact paths.

Uses the standard library ``sqlite3`` only. Structured data lives in SQLite;
file-backed evidence lives under ``data/artifacts/{run_id}/`` as required by
``docs/INTERFACES.md``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    scenario    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(id),
    baseline_version  TEXT NOT NULL,
    candidate_version TEXT NOT NULL,
    status            TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    completed_at      TEXT,
    seed              INTEGER,
    case_count        INTEGER
);

CREATE TABLE IF NOT EXISTS test_cases (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES runs(id),
    seq         INTEGER NOT NULL,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,
    input       TEXT NOT NULL,
    expected    TEXT NOT NULL,
    difficulty  REAL NOT NULL,
    status      TEXT NOT NULL,
    version     TEXT NOT NULL,
    output      TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES runs(id),
    test_case_id TEXT NOT NULL REFERENCES test_cases(id),
    seq          INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    uri          TEXT,
    payload      TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id            TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES runs(id),
    test_case_id  TEXT,
    seq           INTEGER NOT NULL,
    severity      TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL,
    confidence    REAL NOT NULL,
    evidence_ids  TEXT NOT NULL,
    recommendation TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL UNIQUE REFERENCES runs(id),
    summary      TEXT NOT NULL,
    metrics      TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    run_id     TEXT NOT NULL REFERENCES runs(id),
    sequence   INTEGER NOT NULL,
    type       TEXT NOT NULL,
    message    TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_test_cases_run ON test_cases(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, sequence);
"""


class Database:
    """Owns the SQLite file and the artifact directory for one configuration."""

    def __init__(self, db_path: Path, artifacts_dir: Path) -> None:
        self.db_path = Path(db_path)
        self.artifacts_dir = Path(artifacts_dir)

    # -- lifecycle ----------------------------------------------------------

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    # -- artifacts ----------------------------------------------------------

    def run_artifact_dir(self, run_id: str) -> Path:
        path = self.artifacts_dir / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_artifact(self, run_id: str, filename: str, content: str) -> str:
        """Persist a text artifact and return its repository-relative path."""
        path = self.run_artifact_dir(run_id) / filename
        path.write_text(content, encoding="utf-8")
        return f"data/artifacts/{run_id}/{filename}"
