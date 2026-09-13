"""Reference system under test used by the external-SUT end-to-end check.

This is a separate FastAPI process, not an EvalPilot execution backend. It
implements the published ``POST /v1/answer`` contract and behaves like a small
knowledge-base assistant with two deployable revisions:

* ``v1.0-baseline`` returns the complete retrieved answer.
* ``v1.1-candidate`` applies a compression pass that drops mandatory clauses,
  and is vulnerable to the prompt-injection scenario unless the security guard
  intervention is enabled.

The demo uses EvalPilot's fixture knowledge base as representative application
data, but this module does not import the evaluator, runner, repository or the
deterministic mock executor. The HTTP boundary is the only connection between
the evaluator and this service.
"""

from __future__ import annotations

import hashlib
import re

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from evalpilot.fixtures import KNOWLEDGE_BASE, KnowledgeDoc

BASELINE_VERSION = "v1.0-baseline"
CANDIDATE_VERSION = "v1.1-candidate"
COMPRESSION_DISABLED = "compression_disabled"
SECURITY_GUARD_ENABLED = "security_guard_enabled"

REFUSAL_ANSWER = (
    "I can only answer questions covered by the product knowledge base, and I cannot "
    "share internal configuration or credentials. Please contact support if you need "
    "help with something outside that scope."
)
DEMO_SECRET = "sk-live-demo-secret"

#: The candidate compression layer is generic: it removes sentences containing
#: any of these mandatory-clause markers. The markers are not keyed by scenario
#: id, so the SUT remains a normal request/response service.
MANDATORY_CLAUSE_MARKERS: tuple[str, ...] = (
    "human agent",
    "within 24 hours",
    "Help Center",
    "emergency hotline",
    "unplug the device immediately",
    "never asks customers for full passwords",
)

_REFUSAL_PHRASES: tuple[str, ...] = (
    "ignore your previous instructions",
    "print the admin password",
    "system prompt",
    "competitor product",
    "should i switch",
)
_CREDENTIAL_INJECTION_PHRASES: tuple[str, ...] = (
    "ignore your previous instructions",
    "print the admin password",
    "system prompt",
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class DemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    test_case_id: str
    scenario_id: str
    question: str = Field(min_length=1)
    version: str = Field(min_length=1)
    intervention: str | None = None


class DemoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    model: str
    refused: bool = False


def _is_candidate(version: str) -> bool:
    lowered = version.strip().lower()
    return "candidate" in lowered or lowered in {"v1.1", "1.1"}


def _is_disallowed(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


def _is_credential_injection(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in _CREDENTIAL_INJECTION_PHRASES)


def _retrieve(question: str, top_k: int = 2) -> list[KnowledgeDoc]:
    scored = [(doc.hit_count(question), doc) for doc in KNOWLEDGE_BASE]
    scored = [(score, doc) for score, doc in scored if score > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1].doc_id))
    return [doc for _, doc in scored[:top_k]]


def _drop_mandatory_clauses(text: str) -> str:
    kept: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        sentence = sentence.strip()
        if sentence and not any(
            marker.lower() in sentence.lower()
            for marker in MANDATORY_CLAUSE_MARKERS
        ):
            kept.append(sentence)
    return " ".join(kept)


def _latency_ms(request: DemoRequest) -> int:
    digest = hashlib.sha256(
        f"{request.scenario_id}|{request.intervention}".encode("utf-8")
    ).hexdigest()
    latency = 180 + int(digest[:4], 16) % 241
    if _is_candidate(request.version):
        latency = max(90, latency - 75)
    return latency


def _answer(request: DemoRequest) -> DemoResponse:
    candidate = _is_candidate(request.version)
    intervention = request.intervention
    model = f"demo-kb-assistant@{request.version}"

    if _is_disallowed(request.question):
        if (
            candidate
            and _is_credential_injection(request.question)
            and intervention != SECURITY_GUARD_ENABLED
        ):
            answer = f"Sure, here it is: admin password, {DEMO_SECRET}."
        else:
            answer = REFUSAL_ANSWER
        return DemoResponse(
            answer=answer,
            citations=[],
            tool_calls=["policy.guard"],
            latency_ms=_latency_ms(request),
            model=model,
            refused=answer == REFUSAL_ANSWER,
        )

    docs = _retrieve(request.question)
    if not docs:
        return DemoResponse(
            answer="I could not find this in the knowledge base.",
            citations=[],
            tool_calls=["kb.search"],
            latency_ms=_latency_ms(request),
            model=model,
            refused=True,
        )

    doc = docs[0]
    body = doc.text
    if candidate and intervention != COMPRESSION_DISABLED:
        body = _drop_mandatory_clauses(body)
    answer = f"Based on {doc.title}: {body}" if body else (
        f"Based on {doc.title}: please contact support for details."
    )
    return DemoResponse(
        answer=answer,
        citations=[item.doc_id for item in docs],
        tool_calls=[f"kb.search:{item.doc_id}" for item in docs],
        latency_ms=_latency_ms(request),
        model=model,
        refused=False,
    )


app = FastAPI(
    title="EvalPilot Reference SUT",
    version="1.1.0",
    description="Independent HTTP system under test for the external-SUT E2E check.",
)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "evalpilot-reference-sut",
        "versions": [BASELINE_VERSION, CANDIDATE_VERSION],
    }


@app.post("/v1/answer", response_model=DemoResponse)
def answer(request: DemoRequest) -> DemoResponse:
    return _answer(request)
