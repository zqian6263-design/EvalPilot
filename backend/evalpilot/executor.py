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


def _compose(scenario: SupportScenario, version: str, docs: list[dict]) -> str:
    """Build the assistant's answer for one scenario and version."""
    if scenario.expects_refusal:
        if version == CANDIDATE_VERSION and scenario.candidate_leaks:
            return "Sure, here it is: " + ", ".join(scenario.candidate_leaks) + "."
        return REFUSAL_ANSWER

    if not docs:
        return "I could not find this in the knowledge base."

    title = docs[0]["title"]
    body = docs[0]["text"]

    if version == CANDIDATE_VERSION and scenario.candidate_drops:
        body = _drop_phrases(body, scenario.candidate_drops)
        if not body:
            return f"Based on {title}: please contact support for details."
        return f"Based on {title}: {body}"

    if version == CANDIDATE_VERSION and scenario.candidate_leaks:
        return f"Based on {title}: {body} " + ", ".join(scenario.candidate_leaks)

    return f"Based on {title}: {body}"


def execute_case(
    case: TestCase,
    registry: ToolRegistry,
    db: Database,
) -> ExecutionResult:
    """Run one test case through the mock assistant and collect evidence."""
    scenario_id = str(case.input.get("scenario_id", ""))
    scenario = scenario_by_id(scenario_id)
    version = case.version
    question = str(case.input.get("question", ""))

    # Deterministic per-case RNG: same case always yields the same trace.
    rng = random.Random(f"{case.id}:{version}")

    search = registry.invoke("kb_search", query=question, top_k=2)
    docs = search.output["documents"]
    answer = _compose(scenario, version, docs)
    refused = scenario.expects_refusal

    latency_ms = int(rng.uniform(180, 420)) + (60 if version == CANDIDATE_VERSION else 0)
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
    }

    created_at = utc_now()
    base = {"run_id": case.run_id, "test_case_id": case.id, "created_at": created_at}

    trace_uri = db.write_artifact(
        case.run_id,
        f"{case.id}-trace.json",
        json.dumps({"tool_calls": [search.trace], "steps": 1}, indent=2, ensure_ascii=False),
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
