"""Memory lookup over the seeded incident history.

Public surface:

- :func:`seed_incidents` — idempotently load the fixtures into SQLite, and
  return the fixtures that were actually inserted.
- :func:`select_incidents` / :func:`match_incidents` — score and rank incidents.
- :data:`INCIDENTS` — the authored fixture set, also reachable through the
  repository once seeded.

The split is deliberate: ``incidents.py`` owns the data, ``retrieval.py`` owns
the scoring, and this module is the one import the rest of the backend needs.
"""

from __future__ import annotations

from evalpilot.memory.incidents import (
    INCIDENTS,
    INCIDENT_EPOCH,
    IncidentFixture,
    incident_by_id,
    incident_metadata,
)
from evalpilot.memory.retrieval import (
    DEFAULT_MATCH_LIMIT,
    confidence_for,
    match_incidents,
    search_terms,
    select_incidents,
)
from evalpilot.models import HistoricalIncident
from evalpilot.repository import Repository

__all__ = [
    "DEFAULT_MATCH_LIMIT",
    "INCIDENTS",
    "INCIDENT_EPOCH",
    "IncidentFixture",
    "confidence_for",
    "incident_by_id",
    "incident_metadata",
    "match_incidents",
    "search_terms",
    "seed_incidents",
    "select_incidents",
]


def seed_incidents(repo: Repository) -> list[HistoricalIncident]:
    """Seed the incident fixtures. Returns the rows that were actually added.

    Idempotent: an incident already in the table is left untouched, so calling
    this on every container build is safe and an edit to a fixture's prose does
    not rewrite the history under an investigation that already cited it.
    """
    added: list[HistoricalIncident] = []
    for fixture in INCIDENTS:
        incident = fixture.to_model()
        if repo.add_historical_incident(incident, fixture.seq):
            added.append(incident)
    return added
