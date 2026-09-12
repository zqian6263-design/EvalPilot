"""The read-only seam the replay engine depends on.

The engine must be callable from the investigation backend without importing
routes or the shared repository, and it must persist nothing of its own.
:class:`InvestigationReadingSource` is the protocol that keeps both true: it is
structural (no inheritance, no import of a concrete class), and its write side
is exactly three narrow methods for the artefacts the caller has asked to be
kept.

Why a read/write protocol rather than "the engine returns objects and the caller
stores them": a counterfactual claim is only worth as much as the evidence
behind it, and a claim about *one replay of one run* has to cite evidence from
*both* arms. The replayed arm — the baseline input re-run under an intervention
— does not exist on disk before the replay happens, so either the engine
persists it or the caller has to reconstruct evidence rows from returned dicts
and keep the two in step. Persisting it here, behind an injected protocol, is
the smaller surface and the one that cannot drift.

:class:`InMemoryReadingSource` implements it for tests and for CLI use: it holds
evidence in a list, exactly like the real one does in SQLite, and never touches
the database.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from evalpilot.models import Evidence, EvidenceKind

#: Evidence kind for a replayed observation's answer text. Reuses the frozen
#: ``text`` kind so the investigation backend stores replays alongside
#: originals in one evidence table rather than inventing a parallel one.
REPLAY_EVIDENCE_KIND: EvidenceKind = "text"

#: Payload key distinguishing a replayed observation from an executed one.
REPLAY_CONDITION_KEY = "condition"


@runtime_checkable
class InvestigationReadingSource(Protocol):
    """What the replay engine needs from the outside world.

    ``get_evidence`` is the only read: it resolves a persisted evidence id back
    to its payload, which is how the engine learns a case's question and — when
    the run stored one — its original answer and score. Everything else is
    write.

    Implementations must return the evidence row for an unknown id as ``None``
    rather than raising: "the id the caller cited does not exist" is a result
    the engine reports as ``inconclusive`` with a reason, not an exception that
    aborts an investigation.
    """

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        """The persisted evidence row for ``evidence_id``, or ``None``."""
        ...

    def add_evidence(self, evidence: Evidence) -> Evidence:
        """Persist one evidence row, preserving its assigned id.

        Takes a whole :class:`~evalpilot.models.Evidence` rather than field
        kwargs so it matches ``Repository.add_evidence`` exactly: the executor
        already builds fully-formed evidence rows, and an adapter that has to
        re-key them is an adapter that can drop a field.
        """
        ...

    def write_artifact(self, run_id: str, filename: str, content: str) -> str:
        """Persist a text artefact and return its location."""
        ...


class InMemoryReadingSource:
    """A dict-of-evidence implementation for tests and offline callers.

    ``get_evidence`` mirrors the repository's contract, not a relaxation of it:
    an id this source has never seen returns ``None``. A test that wants to
    simulate a missing evidence row only has to cite an id it never wrote.
    """

    def __init__(self, evidence: Iterable[Evidence] | None = None) -> None:
        self._evidence: dict[str, Evidence] = {item.id: item for item in evidence or ()}
        self._artifacts: dict[str, str] = {}
        self.added: list[Evidence] = []

    # -- reads ---------------------------------------------------------------

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        return self._evidence.get(evidence_id)

    def all_evidence(self) -> list[Evidence]:
        """Every row this source holds, insertion-ordered. Test convenience."""
        return list(self._evidence.values())

    def evidence_for_case(self, test_case_id: str) -> list[Evidence]:
        """This case's rows, insertion-ordered. Test convenience."""
        return [
            item
            for item in self._evidence.values()
            if item.test_case_id == test_case_id
        ]

    def get_artifact(self, uri: str) -> str | None:
        """The content written for ``uri``, if this source wrote it."""
        return self._artifacts.get(uri)

    # -- writes --------------------------------------------------------------

    def add_evidence(self, evidence: Evidence) -> Evidence:
        self._evidence[evidence.id] = evidence
        self.added.append(evidence)
        return evidence

    def write_artifact(self, run_id: str, filename: str, content: str) -> str:
        uri = f"memory://artifacts/{run_id}/{filename}"
        self._artifacts[uri] = content
        return uri


def resolve_evidence(
    source: InvestigationReadingSource, evidence_ids: Sequence[str]
) -> tuple[list[Evidence], list[str]]:
    """Look up ``evidence_ids``, returning the rows found and the ids missing.

    A missing id is returned rather than raised so the caller can decide: the
    engine downgrades the experiment to ``inconclusive`` and names the id,
    which is more useful to an investigation than an exception that loses the
    two ids that *did* resolve.
    """
    found: list[Evidence] = []
    missing: list[str] = []
    for evidence_id in evidence_ids:
        if not str(evidence_id).strip():
            continue
        row = source.get_evidence(str(evidence_id))
        if row is None:
            missing.append(str(evidence_id))
        else:
            found.append(row)
    return found, missing
