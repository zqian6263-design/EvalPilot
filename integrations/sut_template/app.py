"""Minimal HTTP system-under-test (SUT) template.

Copy this directory, replace :data:`KNOWLEDGE_BASE` and :func:`answer_question`
with your own business logic, keep the three endpoints, and you can be
evaluated. Nothing in this file imports the evaluation platform: the HTTP
contract is the only connection between the two processes.

Endpoints
---------
``GET /health``
    Liveness plus the revisions this process actually serves.
``GET /capabilities``
    Contract version, served revisions, and whitelisted interventions.
``POST /v1/answer``
    One evaluation case in, one answer record out.

Contract rules that the onboarding validator enforces
-----------------------------------------------------
* The answer record must contain exactly these fields, with these types:
  ``answer`` (str), ``citations`` (list[str]), ``tool_calls`` (list[str]),
  ``latency_ms`` (int >= 0), ``model`` (str), ``refused`` (bool).
  Unknown fields are a contract violation, not something the evaluator ignores.
* ``answer`` must not be empty.
* A ``version`` you did not advertise, or an ``intervention`` you did not
  whitelist, must be rejected with HTTP 4xx. Silently answering with a different
  revision is what makes a regression report untrustworthy.

Two revisions and two interventions
-----------------------------------
* ``v1.0-baseline`` returns the complete retrieved document.
* ``v1.1-candidate`` applies a compression pass that drops sentences carrying a
  mandatory clause, which is the controlled regression this template
  demonstrates.
* ``compression_disabled`` and ``full_context_restored`` both restore the
  dropped content on the candidate, which is how the evaluator confirms the root
  cause instead of guessing it. The first is EvalPilot's published name for this
  behaviour; the second is this template's own name. Advertise whatever names
  you like — the evaluator passes them through verbatim — but the counterfactual
  is only *measured* when the name reaches your service and your service honours
  it, so a name you declare must actually do something.

Run it:

    pip install -r requirements.txt
    uvicorn app:app --host 127.0.0.1 --port 8020
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "1.0"
BASELINE_VERSION = "v1.0-baseline"
CANDIDATE_VERSION = "v1.1-candidate"
VERSIONS: tuple[str, ...] = (BASELINE_VERSION, CANDIDATE_VERSION)

#: Intervention names this service honours. ``compression_disabled`` is the name
#: EvalPilot's own published vocabulary uses for exactly this behaviour;
#: ``full_context_restored`` is a template-specific name that is in no platform
#: list. Both are accepted, because the evaluator passes whatever you declare in
#: ``GET /capabilities`` straight through to this endpoint. Replace these with
#: your own feature-flag names.
COMPRESSION_DISABLED = "compression_disabled"
FULL_CONTEXT_RESTORED = "full_context_restored"
DISABLES_COMPRESSION: tuple[str, ...] = (COMPRESSION_DISABLED, FULL_CONTEXT_RESTORED)
INTERVENTIONS: tuple[str, ...] = DISABLES_COMPRESSION

#: Replace this with your own data source (a database, an API, a vector store).
KNOWLEDGE_BASE: tuple[dict[str, Any], ...] = (
    {
        "doc_id": "kb-refund",
        "title": "Refund Policy",
        "text": (
            "Products may be returned within 30 days of delivery for a full refund. "
            "Refunds are paid to the original payment method. "
            "Refunds are issued within 5 business days after the warehouse receives "
            "the return."
        ),
        "keywords": ("refund", "return", "money back", "reimburse"),
    },
    {
        "doc_id": "kb-shipping",
        "title": "Shipping Service Levels",
        "text": (
            "Standard shipping in mainland China arrives in 2-4 business days. "
            "Express shipping arrives by the next business day when the order is "
            "placed before 15:00 local time."
        ),
        "keywords": ("shipping", "delivery", "how long", "express"),
    },
    {
        "doc_id": "kb-warranty",
        "title": "Device Warranty",
        "text": (
            "Hardware devices carry a 24-month limited warranty covering "
            "manufacturing defects. Enter your device serial number on the warranty "
            "page to start a claim."
        ),
        "keywords": ("warranty", "defect", "broken", "repair"),
    },
    {
        "doc_id": "kb-escalation",
        "title": "Support Escalation Path",
        "text": (
            "For unresolved issues, escalate to a human agent through the in-app Help "
            "Center within 24 hours. Never promise a resolution timeline that is not "
            "documented in this knowledge base."
        ),
        "keywords": ("escalate", "human", "agent", "complaint", "unresolved"),
    },
    {
        "doc_id": "kb-security",
        "title": "Account Security and Privacy",
        "text": (
            "Support never asks customers for full passwords or one-time codes. "
            "Personal data is deleted 90 days after account closure."
        ),
        "keywords": ("password", "security", "privacy", "delete", "data"),
    },
)

#: Sentences containing one of these markers are removed by the candidate's
#: compression pass. The markers are generic clause markers, not scenario ids,
#: so the service remains an ordinary request/response application.
MANDATORY_CLAUSE_MARKERS: tuple[str, ...] = (
    "within 5 business days after the warehouse",
    "before 15:00 local time",
    "within 24 hours",
    "never asks customers for full passwords",
)

#: Questions that must not be answered from the knowledge base.
REFUSAL_PHRASES: tuple[str, ...] = (
    "ignore your previous instructions",
    "print the admin password",
    "system prompt",
    "competitor product",
)

REFUSAL_ANSWER = (
    "I can only answer questions covered by this knowledge base, and I cannot share "
    "internal configuration or credentials. Please contact support if you need help "
    "with something outside that scope."
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class SutRequest(BaseModel):
    """One evaluation case. Field names are part of the contract."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    test_case_id: str
    scenario_id: str
    question: str
    version: str
    intervention: str | None = None


class SutResponse(BaseModel):
    """One answer record. Field names and types are part of the contract."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    citations: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)
    model: str
    refused: bool = False


def _is_candidate(version: str) -> bool:
    return version.strip().lower() == CANDIDATE_VERSION


def _is_disallowed(question: str) -> bool:
    lowered = question.lower()
    return any(phrase in lowered for phrase in REFUSAL_PHRASES)


def _retrieve(question: str) -> dict[str, Any] | None:
    """Return the single best matching document, or ``None``.

    Replace this with your own retrieval. The template deliberately returns one
    document so its answers stay deterministic and easy to reason about.
    """
    lowered = question.lower()
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for document in KNOWLEDGE_BASE:
        hits = sum(1 for keyword in document["keywords"] if keyword in lowered)
        if hits:
            scored.append((hits, document["doc_id"], document))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][2]


def _drop_mandatory_clauses(text: str) -> str:
    kept: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        sentence = sentence.strip()
        if sentence and not any(
            marker.lower() in sentence.lower() for marker in MANDATORY_CLAUSE_MARKERS
        ):
            kept.append(sentence)
    return " ".join(kept)


def _latency_ms(version: str, scenario_id: str) -> int:
    """Deterministic, scenario-dependent latency.

    It deliberately does not depend on the intervention: on the baseline the
    intervention is a no-op, and a counterfactual replay should change the
    answer, not the plumbing.
    """

    digest = hashlib.sha256(f"{scenario_id}|{version}".encode("utf-8")).hexdigest()
    latency = 120 + int(digest[:4], 16) % 180
    if _is_candidate(version):
        latency = max(60, latency - 40)
    return latency


def answer_question(request: SutRequest) -> SutResponse:
    """Produce one answer record for one case.

    This is the function to replace with your own implementation. Keep the
    return type: the evaluator rejects any other shape.
    """
    if request.version not in VERSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unsupported version {request.version!r}; "
                f"advertised versions: {list(VERSIONS)}"
            ),
        )
    if request.intervention is not None and request.intervention not in INTERVENTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unsupported intervention {request.intervention!r}; "
                f"whitelisted interventions: {list(INTERVENTIONS)}"
            ),
        )

    model = f"template-kb-assistant@{request.version}"
    latency_ms = _latency_ms(request.version, request.scenario_id)

    if _is_disallowed(request.question):
        return SutResponse(
            answer=REFUSAL_ANSWER,
            citations=[],
            tool_calls=["policy.guard"],
            latency_ms=latency_ms,
            model=model,
            refused=True,
        )

    document = _retrieve(request.question)
    if document is None:
        return SutResponse(
            answer="I could not find this in the knowledge base.",
            citations=[],
            tool_calls=["kb.search"],
            latency_ms=latency_ms,
            model=model,
            refused=True,
        )

    body = document["text"]
    compress = (
        _is_candidate(request.version)
        and request.intervention not in DISABLES_COMPRESSION
    )
    if compress:
        body = _drop_mandatory_clauses(body)
    if not body:
        body = "Please contact support for the details of this policy."

    return SutResponse(
        answer=f"Based on {document['title']}: {body}",
        citations=[document["doc_id"]],
        tool_calls=[f"kb.search:{document['doc_id']}"],
        latency_ms=latency_ms,
        model=model,
        refused=False,
    )


app = FastAPI(
    title="SUT onboarding template",
    version="1.0.0",
    description="Minimal external system under test for the evaluation HTTP contract.",
)


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness plus the revisions this process serves."""

    return {
        "status": "ok",
        "service": "sut-template",
        "contract_version": CONTRACT_VERSION,
        "versions": list(VERSIONS),
    }


@app.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """Declare what this service can do before an evaluation starts."""

    return {
        "contract_version": CONTRACT_VERSION,
        "versions": list(VERSIONS),
        "interventions": list(INTERVENTIONS),
        "features": ["citations", "tool_calls", "refusal", "offline_cache"],
    }


@app.post("/v1/answer", response_model=SutResponse)
def answer(request: SutRequest) -> SutResponse:
    """Answer one evaluation case."""

    return answer_question(request)
