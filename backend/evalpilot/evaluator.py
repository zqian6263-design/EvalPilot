"""Evidence persistence helpers.

Kept separate from the runner so evidence storage can evolve (deduplication,
retention windows, object storage) without touching the state machine.
"""

from __future__ import annotations

from collections.abc import Iterable

from evalpilot.models import Evidence
from evalpilot.repository import Repository


def persist_evidence(repo: Repository, items: Iterable[Evidence]) -> list[Evidence]:
    """Persist each evidence record and return them in order."""
    return [repo.add_evidence(item) for item in items]


def evidence_by_case(items: Iterable[Evidence]) -> dict[str, list[Evidence]]:
    """Group evidence rows by their test case."""
    grouped: dict[str, list[Evidence]] = {}
    for item in items:
        grouped.setdefault(item.test_case_id, []).append(item)
    return grouped
