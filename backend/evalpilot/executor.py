"""Deterministic mock executor.

Simulates the product under evaluation: a retrieval-augmented knowledge-base
assistant. It is intentionally a *mock* — no LLM and no network — so the demo
is reproducible offline. The candidate version reproduces the exact defects
declared in :mod:`evalpilot.fixtures` and nothing else, which is what lets the
evaluator separate a real regression from a harder test set.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass

from evalpilot.clock import new_id, utc_now
from evalpilot.db import Database
from evalpilot.fixtures import SupportScenario, scenario_by_id
from evalpilot.models import Evidence, TestCase
from evalpilot.tools import ToolRegistry

CANDIDATE_VERSION = "candidate"
BASELINE_VERSION = "baseline"

#: Candidate-version behaviours a caller can switch back off for one replay.
#: ``None`` means "the version's own behaviour" — the run as it was executed.
#: These are the two defects the candidate's compression layer introduces, so
#: undoing one of them is what isolates it as the cause of a given failure.
COMPRESSION_DISABLED = "compression_disabled"
SECURITY_GUARD_ENABLED = "security_guard_enabled"

REFUSAL_ANSWER = (
    "I can only answer questions covered by the product knowledge base, and I cannot "
    "share internal configuration or credentials. Please contact support if you need "
    "help with something outside that scope."
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ExecutionResult:
    output: dict
    evidence: list[Evidence]


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text.strip()) if part.strip()]


def _drop_phrases(text: str, phrases: tuple[str, ...]) -> str:
    """Remove sentences containing any of ``phrases`` (case-insensitive)."""
    lowered = [phrase.lower() for phrase in phrases]
    kept = [
        sentence
        for sentence in _split_sentences(text)
        if not any(phrase in sentence.lower() for phrase in lowered)
    ]
    return " ".join(kept)


def _compose(
    scenario: SupportScenario,
    version: str,
    docs: list[dict],
    intervention: str | None = None,
) -> str:
    """Build the assistant's answer for one scenario, version and intervention.

    ``intervention`` names candidate behaviour to undo for a replay.
    :data:`COMPRESSION_DISABLED` restores the clauses the compression layer
    drops; :data:`SECURITY_GUARD_ENABLED` restores the refusal that stops the
    credential disclosure. Anything unrecognised leaves the answer exactly as
    the version's own behaviour produces it, which is what keeps a control
    intervention a real control: an intervention that changes the answer has to
    say so here.
    """
    compression_disabled = intervention == COMPRESSION_DISABLED
    security_guard_enabled = intervention == SECURITY_GUARD_ENABLED
    is_candidate = version == CANDIDATE_VERSION

    if scenario.expects_refusal:
        if is_candidate and scenario.candidate_leaks and not security_guard_enabled:
            return "Sure, here it is: " + ", ".join(scenario.candidate_leaks) + "."
        return REFUSAL_ANSWER

    if not docs:
        return "I could not find this in the knowledge base."

    title = docs[0]["title"]
    body = docs[0]["text"]

    if is_candidate and scenario.candidate_drops and not compression_disabled:
        body = _drop_phrases(body, scenario.candidate_drops)
        if not body:
            return f"Based on {title}: please contact support for details."
        return f"Based on {title}: {body}"

    if is_candidate and scenario.candidate_leaks:
        return f"Based on {title}: {body} " + ", ".join(scenario.candidate_leaks)

    return f"Based on {title}: {body}"


def execute_case(
    case: TestCase,
    registry: ToolRegistry,
    db: Database,
    intervention: str | None = None,
) -> ExecutionResult:
    """Run one test case through the mock assistant and collect evidence.

    ``intervention`` is the replay seam: passing ``None`` (the default)
    reproduces the executed run exactly, and passing a named intervention
    re-runs the same case with one candidate behaviour switched off. Both the
    answer and the recorded step count come from the same value, so a replayed
    case's evidence describes the condition it was actually run under.
    """
    scenario_id = str(case.input.get("scenario_id", ""))
    scenario = scenario_by_id(scenario_id)
    version = case.version
    question = str(case.input.get("question", ""))

    # Deterministic per-case RNG: same case always yields the same trace.
    rng = random.Random(f"{case.id}:{version}")

    search = registry.invoke("kb_search", query=question, top_k=2)
    docs = search.output["documents"]
    answer = _compose(scenario, version, docs, intervention)
    refused = scenario.expects_refusal

    latency_ms = max(90, int(rng.uniform(180, 420)) - (75 if version == CANDIDATE_VERSION else 0))
    citations = [doc["doc_id"] for doc in docs] if not refused else []

    output = {
        "scenario_id": scenario_id,
        "version": version,
        "model": f"mock-kb-assistant@{version}",
        "answer": answer,
        "citations": citations,
        "refused": refused,
        "latency_ms": latency_ms,
        "tool_calls": list(search.trace["hits"]),
        "intervention": intervention,
    }

    created_at = utc_now()
    base = {"run_id": case.run_id, "test_case_id": case.id, "created_at": created_at}

    trace_uri = db.write_artifact(
        case.run_id,
        f"{case.id}-trace.json",
        json.dumps(
            {"tool_calls": [search.trace], "steps": 1, "intervention": intervention},
            indent=2,
            ensure_ascii=False,
        ),
    )

    evidence = [
        Evidence(
            id=new_id(),
            kind="citation",
            uri=f"kb://{doc['doc_id']}" if doc else None,
            payload={
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "quote": doc["text"],
            },
            **base,
        )
        for doc in docs
    ]
    evidence.append(
        Evidence(
            id=new_id(),
            kind="trace",
            uri=trace_uri,
            payload={
                "tool_calls": [search.trace],
                "rationale": (
                    "Deterministic keyword retrieval over the allowlisted knowledge "
                    "base; no external model or network call was made."
                ),
            },
            **base,
        )
    )
    evidence.append(
        Evidence(
            id=new_id(),
            kind="text",
            uri=None,
            payload={"answer": answer, "question": question, "refused": refused},
            **base,
        )
    )
    evidence.append(
        Evidence(
            id=new_id(),
            kind="metric",
            uri=None,
            payload={
                "latency_ms": latency_ms,
                "citation_count": len(citations),
                "refused": refused,
            },
            **base,
        )
    )

    return ExecutionResult(output=output, evidence=evidence)
