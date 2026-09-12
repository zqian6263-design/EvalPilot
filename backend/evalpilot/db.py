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

-- Progress streams. ``entity_id`` holds the id of whatever the stream belongs
-- to: a run id for a run's events, an investigation id for an investigation's.
-- It carries no foreign key because the two entities live in different tables
-- and the envelope (frozen in docs/INTERFACES.md) is deliberately shared.
CREATE TABLE IF NOT EXISTS events (
    entity_id  TEXT NOT NULL,
    sequence   INTEGER NOT NULL,
    type       TEXT NOT NULL,
    message    TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (entity_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_test_cases_run ON test_cases(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_id, sequence);
"""

#: Current schema version, recorded in the database file's ``user_version``.
#: Bump it whenever :data:`SCHEMA` changes shape in a way an older file has to
#: be migrated for.
SCHEMA_VERSION = 2

#: Rewrite of ``events`` from a run-scoped ``run_id`` to the shared
#: ``entity_id`` the V2 investigation stream needs. Skipped when the table
#: already has the new shape, which is what makes it safe on a fresh file.
_MIGRATE_EVENTS_TO_ENTITY_ID = """
CREATE TABLE IF NOT EXISTS events_v2 (
    entity_id  TEXT NOT NULL,
    sequence   INTEGER NOT NULL,
    type       TEXT NOT NULL,
    message    TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (entity_id, sequence)
);
INSERT OR IGNORE INTO events_v2 (
    entity_id, sequence, type, message, data, created_at
)
    SELECT run_id, sequence, type, message, data, created_at FROM events;
DROP TABLE events;
ALTER TABLE events_v2 RENAME TO events;
CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_id, sequence);
"""

# The autonomous-investigation layer (``docs/V2_INTERFACES.md``). Agent-owned
# modules create their own tables rather than widening the block above, so two
# worktrees touching different subsystems stay mergeable. Applied after
# :data:`SCHEMA`, and every statement is ``IF NOT EXISTS``, so re-running the
# schema is safe for an existing database file.
INVESTIGATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_incidents (
    id                TEXT PRIMARY KEY,
    seq               INTEGER NOT NULL,
    title             TEXT NOT NULL,
    symptoms          TEXT NOT NULL,
    tags              TEXT NOT NULL,
    root_cause        TEXT NOT NULL,
    resolution        TEXT NOT NULL,
    intervention      TEXT,
    guard_scenario_id TEXT,
    occurred_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigations (
    id               TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES runs(id),
    objective        TEXT NOT NULL,
    status           TEXT NOT NULL,
    summary          TEXT NOT NULL,
    risk_level       TEXT NOT NULL,
    decision_verdict TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    completed_at     TEXT
);

CREATE TABLE IF NOT EXISTS investigation_steps (
    id               TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    parent_id        TEXT,
    seq              INTEGER NOT NULL,
    kind             TEXT NOT NULL,
    title            TEXT NOT NULL,
    status           TEXT NOT NULL,
    detail           TEXT NOT NULL,
    data             TEXT NOT NULL,
    evidence_ids     TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    completed_at     TEXT
);

CREATE TABLE IF NOT EXISTS memory_matches (
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    incident_id      TEXT NOT NULL REFERENCES historical_incidents(id),
    seq              INTEGER NOT NULL,
    score            REAL NOT NULL,
    reason           TEXT NOT NULL,
    matched_terms    TEXT NOT NULL,
    PRIMARY KEY (investigation_id, incident_id)
);

CREATE TABLE IF NOT EXISTS counterfactual_experiments (
    id               TEXT PRIMARY KEY,
    investigation_id TEXT NOT NULL REFERENCES investigations(id),
    seq              INTEGER NOT NULL,
    scenario_id      TEXT NOT NULL,
    intervention     TEXT NOT NULL,
    original_score   REAL NOT NULL,
    counterfactual_score REAL NOT NULL,
    delta            REAL NOT NULL,
    confidence       REAL NOT NULL,
    verdict          TEXT NOT NULL,
    evidence_ids     TEXT NOT NULL,
    rationale        TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS release_decisions (
    investigation_id     TEXT PRIMARY KEY REFERENCES investigations(id),
    verdict              TEXT NOT NULL,
    risk_level           TEXT NOT NULL,
    summary              TEXT NOT NULL,
    blocking_findings    TEXT NOT NULL,
    recommended_actions  TEXT NOT NULL,
    confidence           REAL NOT NULL,
    generated_at         TEXT NOT NULL
);

-- The event envelope is shared with runs: ``run_id`` holds the investigation id
-- for investigations, so one table and one reader serve both streams.
CREATE INDEX IF NOT EXISTS idx_investigations_run ON investigations(run_id);
CREATE INDEX IF NOT EXISTS idx_investigation_steps ON investigation_steps(investigation_id, seq);
CREATE INDEX IF NOT EXISTS idx_memory_matches ON memory_matches(investigation_id, seq);
CREATE INDEX IF NOT EXISTS idx_counterfactuals ON counterfactual_experiments(investigation_id, seq);
CREATE INDEX IF NOT EXISTS idx_incidents_seq ON historical_incidents(seq);
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
            self._migrate(conn)
            conn.executescript(INVESTIGATION_SCHEMA)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Bring an existing database file up to :data:`SCHEMA_VERSION`.

        A fresh file gets the current shape straight from :data:`SCHEMA` and is
        simply stamped, so no data is copied. A file written by an older build
        has its ``events`` table rewritten once, guarded on the column shape so
        the row copy can never run twice.
        """
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(events)")}
        if not columns:
            raise RuntimeError("the events table is missing after applying the schema")
        if "run_id" in columns and "entity_id" not in columns:
            conn.executescript(_MIGRATE_EVENTS_TO_ENTITY_ID)
            conn.execute("PRAGMA foreign_keys = ON")

        if int(conn.execute("PRAGMA user_version").fetchone()[0]) != SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

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
