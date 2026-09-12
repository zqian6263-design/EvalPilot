from __future__ import annotations

import sqlite3
from pathlib import Path

from evalpilot.db import Database


def test_v1_events_table_migrates_to_entity_id(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE events (
            run_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, sequence)
        );
        INSERT INTO events VALUES ('run-1', 1, 'run.started', 'legacy', '{}', '2026-01-01T00:00:00Z');
        PRAGMA user_version = 1;
        """
    )
    conn.close()

    Database(db_path, tmp_path / "artifacts").initialize()

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        assert "entity_id" in columns and "run_id" not in columns
        row = conn.execute("SELECT entity_id, sequence, message FROM events").fetchone()
        assert row == ("run-1", 1, "legacy")
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        conn.close()
