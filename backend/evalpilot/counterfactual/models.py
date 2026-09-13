"""Typed models for the counterfactual replay engine.

Field names for the persisted entity mirror ``docs/V2_INTERFACES.md``
(``CounterfactualExperiment``). Everything else here is internal to this
package, which knows nothing about the database, the repository or the HTTP
layer: the investigation backend maps :class:`ReplayRunResult` and
:class:`ExperimentResult` onto its own rows.

Two shapes exist because two different things are being reported, and
conflating them is how a replay result ends up overclaiming:

- :class:`ReplayRunResult` is one *observation* — one condition, one score, one
  evidence id. It is the measured fact.
- :class:`ExperimentResult` is the *classification* derived from the original
  observation and the replayed one. It is the claim, and it carries the verdict
  vocabulary from ``docs/V2_INTERFACES.md``.

Conventions from the repository contract: UUID string ids, UTC ISO-8601
timestamps.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CaseVersion = Literal["baseline", "candidate"]


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime.

    Local rather than imported from :mod:`evalpilot.clock` so this module stays
    free of backend modules that could drag in shared state; it matches that
    helper's behaviour.
    """
    return datetime.now(timezone.utc)


class CounterfactualModel(BaseModel):
    """Base class: rejects unknown fields, so a typo fails loudly."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Intervention(str, enum.Enum):
    """A candidate behaviour that a replay can switch back off.

    A ``StrEnum`` is used deliberately: an intervention name is a plain string
    on the wire (the experiment row's ``intervention`` column is ``str``), and
    ``Intervention.COMPRESSION_DISABLED == "compression_disabled"`` lets the
    two be compared and serialized without a conversion step at every boundary.
    """

    COMPRESSION_DISABLED = "compression_disabled"
    SECURITY_GUARD_ENABLED = "security_guard_enabled"
    RETRIEVAL_TOP_K_RESTORED = "retrieval_top_k_restored"
    UNICODE_NORMALIZATION_RESTORED = "unicode_normalization_restored"
    MEMORY_SCOPE_RESTORED = "memory_scope_restored"
    CACHE_BYPASS_ENABLED = "cache_bypass_enabled"
    NONE = "none"

    @classmethod
    def parse(cls, value: str) -> "Intervention":
        """Resolve a caller-supplied name.

        Raises:
            ValueError: for a name this engine cannot execute. An unrecognised
                intervention must fail here rather than fall through to "no
                change": a replay that silently ran the unmodified candidate
                would report ``no_effect`` for every hypothesis, which reads as
                a clean bill of health for a defect that was never tested.
        """
        text = str(value).strip()
        for member in cls:
            if member.value == text:
                return member
        known = ", ".join(repr(member.value) for member in cls)
        raise ValueError(f"Unknown intervention {value!r}; supported interventions are {known}.")

    @property
    def is_control(self) -> bool:
        """``NONE`` — the replay that asserts nothing was changed."""
        return self is Intervention.NONE

    @property
    def executor_value(self) -> str | None:
        """The value :func:`evalpilot.executor.execute_case` expects."""
        return None if self.is_control else self.value


class ExperimentVerdict(str, enum.Enum):
    """What a replay established, in the frozen vocabulary.

    ``docs/V2_INTERFACES.md`` fixes these four values. They are strings for the
    same reason as :class:`Intervention`: the API returns them verbatim.
    """

    ROOT_CAUSE = "root_cause"
    PARTIAL = "partial"
    NO_EFFECT = "no_effect"
    INCONCLUSIVE = "inconclusive"


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


class CounterfactualTarget(CounterfactualModel):
    """The failing case a caller wants explained, and where it came from.

    ``original_evidence_ids`` is what the caller already has on disk for the
    candidate's failing run. The engine reads the original output and score
    *through* these ids, so an experiment can never be grounded in a score that
    is not attached to persisted evidence.
    """

    scenario_id: str
    run_id: str
    test_case_id: str
    intervention: Intervention
    expected: dict[str, Any] = Field(default_factory=dict)
    question: str = ""
    #: Run-specific revision label the external SUT should execute. The
    #: internal ``case.version`` remains the comparison arm used for pairing.
    version_label: str | None = None
    original_evidence_ids: list[str] = Field(default_factory=list)
    #: The candidate's score as the caller recorded it. Reported alongside the
    #: engine's own re-read of the original evidence so a disagreement between
    #: the two is visible instead of hidden.
    original_score: float | None = None
    failing_checks: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_non_blank_identity(self) -> "CounterfactualTarget":
        for name in ("scenario_id", "run_id", "test_case_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"CounterfactualTarget.{name} must not be blank")
        return self


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


class ReplayRunResult(CounterfactualModel):
    """One measured observation: a case re-executed under one condition.

    Every field is a measured fact from a real execution. ``evidence_ids`` are
    the ids of the evidence rows the replay produced and passed through; they
    are the handles a persisted claim must cite.
    """

    scenario_id: str
    run_id: str
    test_case_id: str
    #: The intervention this observation was produced under, as the executor
    #: received it (``None`` for the unmodified original).
    intervention: str | None = None
    version: str
    answer: str
    refused: bool
    citations: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    #: ``None`` when no check was applicable — distinct from a score of 0.0.
    score: float | None = None
    passed: bool | None = None
    failing_checks: list[str] = Field(default_factory=list)
    check_rationales: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    #: An evidence id that is known to be persisted. Set only when the caller
    #: supplied a non-empty ``original_evidence_ids``; read from the persisted
    #: payload, never copied from a replayed row.
    original_evidence_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ExperimentResult(CounterfactualModel):
    """The classification of one replay against the original failure.

    This is the interface the investigation layer persists as a
    ``CounterfactualExperiment`` row. It carries no timestamps of its own
    beyond ``created_at`` and no database ids: ``evidence_ids`` are the
    persisted evidence references the claim rests on.
    """

    investigation_id: str
    scenario_id: str
    run_id: str
    test_case_id: str
    intervention: str
    verdict: ExperimentVerdict
    original_score: float | None = None
    original_score_source: Literal["evidence", "caller", "unavailable"] = "unavailable"
    counterfactual_score: float | None = None
    delta: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str
    #: Structured measurements behind the rationale, so the UI can render the
    #: before/after panel without re-parsing prose.
    metrics: dict[str, Any] = Field(default_factory=dict)
    original: ReplayRunResult | None = None
    replayed: ReplayRunResult | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def is_positive(self) -> bool:
        """True when the intervention explained the failure.

        ``root_cause`` and ``partial`` are the two verdicts that attribute the
        failure to the intervention. ``no_effect`` is a real, reportable
        finding in its own right (the hypothesis was tested and rejected);
        ``inconclusive`` is the only one that asserts nothing.
        """
        return self.verdict in (ExperimentVerdict.ROOT_CAUSE, ExperimentVerdict.PARTIAL)


class ReplayRunSummary(CounterfactualModel):
    """Aggregate of many experiments — the shape a "run a batch" caller wants.

    Deliberately just counts and the per-experiment results: an aggregate must
    never collapse several independent replays into a single claim stronger
    than any of them.
    """

    run_id: str
    investigation_id: str
    experiments: list[ExperimentResult] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utc_now)

    @property
    def counts_by_verdict(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for experiment in self.experiments:
            counts[experiment.verdict.value] = counts.get(experiment.verdict.value, 0) + 1
        return counts
