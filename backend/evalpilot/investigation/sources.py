"""Source tags recorded on investigation steps.

Lives in its own module so both the deterministic engine and the live-mode
augmenter can import it without either importing the other. ``data.source`` is
how a reader tells an engine-produced step from a model-contributed one, so the
two halves of the investigation have to agree on the vocabulary.
"""

from __future__ import annotations

#: The step was produced by the deterministic engine.
SOURCE_DETERMINISTIC = "deterministic"
#: The step was produced by, or contributed to by, the configured model.
SOURCE_LLM = "llm"

#: The values a ``data.source`` may take.
SOURCES: tuple[str, ...] = (SOURCE_DETERMINISTIC, SOURCE_LLM)

#: ``data.authoritative`` is ``False`` on every model-contributed step: it is
#: commentary, and the measured values it sits beside are the facts.
AUTHORITATIVE_MEASURED = True

#: Keys on a step's ``data`` that are measured facts. A model contribution may
#: never write one, whatever the provider does.
MEASURED_DATA_KEYS: frozenset[str] = frozenset(
    {
        "verdict",
        "risk_level",
        "confidence",
        "blocking_findings",
        "blocking_scenarios",
        "baseline_score",
        "candidate_score",
        "delta",
        "baseline_pass_rate",
        "candidate_pass_rate",
        "matched_scenarios",
        "direction",
        "failing_checks",
        "scenarios",
        "control_scenarios",
        "advisory_scenarios",
        "regressed_scenarios",
    }
)

#: Every key a model contribution is allowed to add. Anything else is dropped
#: rather than persisted, so a provider cannot smuggle a key into a step's data.
LLM_DATA_KEYS: frozenset[str] = frozenset(
    {
        "source",
        "model",
        "llm_call_id",
        "usage",
        "objective",
        "claim",
        "mechanism",
        "model_confidence",
        "proposals",
        "discarded",
        "deterministic_hypothesis_count",
        "rationale",
        "llm_evidence_ids",
        "llm_recommendations",
        "proposed_verdict",
        "proposed_risk_level",
        "verdict_disagreement",
        "recommended_actions",
        "fallback",
        "fallback_reason",
        "provider",
        "authoritative",
        "replay_plan",
        "replay_plan_rejected",
    }
)

__all__ = [
    "AUTHORITATIVE_MEASURED",
    "LLM_DATA_KEYS",
    "MEASURED_DATA_KEYS",
    "SOURCE_DETERMINISTIC",
    "SOURCE_LLM",
    "SOURCES",
]
