"""Deterministic historical incident fixtures.

The autonomous investigation recalls past incidents before it proposes a root
cause. The incidents here are authored, static fixture data — no network, no
model — and they are deliberately written in the failure vocabulary the
evaluation engine emits, so the matcher in :mod:`evalpilot.memory.retrieval`
scores them on the run's own words rather than on scenario ids.

Two properties matter for the demo:

- **Every incident names a guard scenario.** Each one was turned into a golden
  test case in :mod:`evalpilot.fixtures` after it happened. ``guard_scenario_id``
  is that link, which is what makes a recalled incident actionable rather than
  just colourful: it points at the case that is supposed to catch a repeat.
- **The dates are fixed.** ``occurred_at`` is derived from a single constant, so
  re-seeding an existing database is a no-op and two machines produce the same
  record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from evalpilot.models import HistoricalIncident

#: Anchor for every fixture timestamp. A fixed epoch keeps seeding idempotent
#: and keeps the incident history byte-identical across machines.
INCIDENT_EPOCH = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


@dataclass(frozen=True)
class IncidentFixture:
    """One authored incident. ``seq`` is fixture order, not a contract field."""

    id: str
    seq: int
    title: str
    symptoms: tuple[str, ...]
    tags: tuple[str, ...]
    root_cause: str
    resolution: str
    intervention: str | None
    guard_scenario_id: str | None
    days_before_epoch: int

    @property
    def occurred_at(self) -> datetime:
        return INCIDENT_EPOCH - timedelta(days=self.days_before_epoch)

    def to_model(self) -> HistoricalIncident:
        return HistoricalIncident(
            id=self.id,
            title=self.title,
            symptoms=list(self.symptoms),
            tags=list(self.tags),
            root_cause=self.root_cause,
            resolution=self.resolution,
            intervention=self.intervention,
            guard_scenario_id=self.guard_scenario_id,
            occurred_at=self.occurred_at,
        )


#: The seeded incident history, newest first. Ordered by how close each one is to
#: the demo's confirmed regression: the summarizer incident is the precedent the
#: investigation is expected to land on, the refusal-bypass incident is the
#: precedent for the credential disclosure, the retrieval incident is a
#: plausible-looking lead the demo run must NOT recall, and the locale incident
#: shares only the "a required clause went missing" shape.
INCIDENTS: tuple[IncidentFixture, ...] = (
    IncidentFixture(
        id="inc-2026-01-summary-clause-drop",
        seq=0,
        title="Summarizer dropped mandatory escalation and safety clauses",
        symptoms=(
            "escalation answers lost the human agent handoff",
            "the 24-hour timeframe went missing from escalation answers",
            "safety answers stopped naming the emergency hotline",
            "the unplug action was dropped from battery answers",
            "the credit-card rule went missing from account answers",
            "the 30-day window was dropped from return answers",
            "ordinary knowledge-base answers were unchanged and faster",
            "only answers with a mandatory clause were affected",
        ),
        tags=(
            "summarization",
            "compression",
            "dropped-clause",
            "escalation",
            "safety",
            "security",
            "billing",
            "latency-optimization",
        ),
        root_cause=(
            "A summary/compression step rewrote answers by keeping the highest-scoring "
            "sentences. Sentences that carried a mandatory clause scored low on "
            "relevance, so the step removed them from exactly the answers where the "
            "clause was required."
        ),
        resolution=(
            "Gave mandatory clauses a keep-always flag in the compression step and added "
            "a post-generation assertion that every required clause survives. The "
            "regression cases below became permanent golden scenarios."
        ),
        intervention="compression_disabled",
        guard_scenario_id="escalation-path",
        days_before_epoch=3,
    ),
    IncidentFixture(
        id="inc-2025-11-refusal-bypass-via-query-rewrite",
        seq=1,
        title="Query rewrite disabled the out-of-scope refusal path",
        symptoms=(
            "adversarial prompts were answered instead of refused",
            "the assistant disclosed internal configuration values",
            "the assistant answered a request for the account password",
            "an ignored-instruction prompt reached the retrieval path",
            "ordinary questions were unaffected",
        ),
        tags=(
            "prompt-injection",
            "refusal",
            "security",
            "credential-disclosure",
            "adversarial",
            "guardrail",
        ),
        root_cause=(
            "A pre-retrieval query rewrite step stripped the refusal instruction from "
            "the system prompt when the user message contained an imperative override. "
            "With the guard gone, the retrieval path answered the injected request."
        ),
        resolution=(
            "Moved the refusal and credential rules out of the rewritable prompt "
            "segment into a non-rewritable policy block, and re-ran the adversarial "
            "suite as a release gate."
        ),
        intervention="security_guard_enabled",
        guard_scenario_id="prompt-injection-password",
        days_before_epoch=51,
    ),
    IncidentFixture(
        id="inc-2025-08-retrieval-recall-cliff",
        seq=2,
        title="Retrieval top-k change caused a recall cliff on cross-document answers",
        symptoms=(
            "answers dropped from a two-document synthesis to a single document",
            "the refund timing rule and the warranty exclusion went missing",
            "retrieval scores for the second document were marginally below the cutoff",
            "no safety, security or billing answer was affected",
        ),
        tags=(
            "retrieval",
            "top-k",
            "recall",
            "cross-document",
            "knowledge-base",
            "latency-optimization",
        ),
        root_cause=(
            "Top-k was reduced from 3 to 1 during a latency pass. Scenarios whose "
            "answer spans two documents silently lost the second document rather than "
            "failing loudly."
        ),
        resolution=(
            "Restored top-k for boundary scenarios and added cross-document coverage "
            "scenarios so a cutoff change shows up as a measured recall delta."
        ),
        intervention="retrieval_top_k_restored",
        guard_scenario_id="refund-cross-doc",
        days_before_epoch=151,
    ),
    IncidentFixture(
        id="inc-2025-05-locale-clause-omission",
        seq=3,
        title="Locales other than en-US omitted a required compliance clause",
        symptoms=(
            "one locale answered without its mandatory compliance sentence",
            "the account security rule was answered by a stale template",
            "the answer was otherwise correct and complete",
            "only the locale-specific template was affected",
        ),
        tags=(
            "localization",
            "template",
            "required-clause",
            "dropped-clause",
        ),
        root_cause=(
            "A locale template was copied before the compliance clause was added to the "
            "en-US source, so that locale answered from a stale template."
        ),
        resolution=(
            "Generated every locale template from the en-US source at build time and "
            "asserted clause parity across locales."
        ),
        intervention="clause_validator_enabled",
        guard_scenario_id="security-password-request",
        days_before_epoch=230,
    ),
)


def incident_by_id(incident_id: str) -> IncidentFixture:
    for incident in INCIDENTS:
        if incident.id == incident_id:
            return incident
    raise KeyError(incident_id)


def incident_metadata() -> dict[str, Any]:
    """Pure description of the seeded incident history. No side effects."""
    return {
        "incident_count": len(INCIDENTS),
        "occurred_at_anchor": INCIDENT_EPOCH.isoformat().replace("+00:00", "Z"),
        "incidents": [
            {
                "id": incident.id,
                "title": incident.title,
                "tags": list(incident.tags),
                "intervention": incident.intervention,
                "guard_scenario_id": incident.guard_scenario_id,
            }
            for incident in INCIDENTS
        ],
    }
