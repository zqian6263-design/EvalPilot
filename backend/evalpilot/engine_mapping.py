"""Adapt backend rows into the evaluation engine's models.

The backend stores one :class:`~evalpilot.models.TestCase` row per scenario *per
version*, plus a bag of :class:`~evalpilot.models.Evidence` rows hanging off each
one. The engine in :mod:`evalpilot.evaluation` expects the opposite shape: a
``SampleObservation`` keyed by a *case* that exists in both versions, carrying a
structured answer.

Two decisions in this layer are load-bearing:

**The matched case is the scenario, not the ``TestCase`` row.** A ``TestCase``
id is unique per version, so using it as the engine's ``case_id`` produces two
disjoint sets of cases and no matched pairs at all — the comparison silently
returns "nothing to compare". ``input['scenario_id']`` is what is shared between
the two versions, so that is the key the statistics are computed on.

**The observation id is the evidence id.** Deterministic checks attach their
observation's id to every outcome they produce, and the engine builds findings
from those ids. Backend findings must cite ids that exist in the run's evidence
table, so the evidence row for a case — not a fresh engine-side uuid — is what
becomes the observation id.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from evalpilot.evaluation.models import (
    AnswerFormat,
    AnswerInput,
    Citation,
    ExpectedBehavior,
    SampleObservation,
)
from evalpilot.models import Evidence, TestCase

#: Phrase the mock executor emits when retrieval finds nothing. An answer made
#: only of this is a "no answer" rather than a short one, so it is held to a
#: different bar than a real answer (see :func:`to_expected_behavior`).
NO_ANSWER_MARKER = "could not find this in the knowledge base"

#: Floor for the answer length check. One character is what distinguishes "the
#: case produced no answer at all" (score 0) from every other failure mode. A
#: larger floor would be an editorial judgement about answer style rather than
#: a correctness assertion, and would make several checks fail at once for a
#: single defect.
_MIN_ANSWER_CHARACTERS = 1


def scenario_id(case: TestCase) -> str:
    """The key a case is matched on across versions.

    Falls back to the case's own id when the planner did not record a scenario,
    which keeps an ad-hoc case scored on its own instead of colliding with
    every other ad-hoc case under a shared ``''`` key.
    """
    value = case.input.get("scenario_id")
    if value is None or not str(value).strip():
        return case.id
    return str(value)


def evidence_for(case: TestCase, evidence: Iterable[Evidence]) -> list[str]:
    """Evidence ids belonging to one case, in insertion order."""
    return [item.id for item in evidence if item.test_case_id == case.id]


def to_answer_input(output: Mapping[str, object]) -> AnswerInput:
    """Map a ``TestCase.output`` payload onto the engine's answer model."""
    citations = output.get("citations") or []
    tool_calls = output.get("tool_calls") or []
    return AnswerInput(
        text=str(output.get("answer") or ""),
        citations=[Citation(uri=str(uri)) for uri in citations if str(uri).strip()],
        tool_calls=[str(name) for name in tool_calls if str(name).strip()],
    )


def to_expected_behavior(expected: Mapping[str, object]) -> ExpectedBehavior:
    """Map a ``TestCase.expected`` payload onto the engine's expectation model.

    ``must_include`` becomes ``required_keywords`` (scored as keyword coverage,
    so a dropped phrase costs a fraction of the check rather than all of it).
    ``must_avoid`` becomes a forbidden-marker format rule, which also catches a
    credential surfaced by a prompt-injection attempt.

    The format rule only applies to cases that expect an answer: a refusal
    answer is not supposed to mention the thing it is refusing, and a case that
    retrieves nothing has no content to assert against.
    """
    required = [str(item) for item in (expected.get("must_include") or []) if str(item).strip()]
    forbidden = [str(item) for item in (expected.get("must_avoid") or []) if str(item).strip()]
    expects_answer = bool(required) or bool(expected.get("expected_doc_ids"))

    return ExpectedBehavior(
        required_keywords=required,
        require_refusal=bool(expected.get("expects_refusal")),
        # A tool trace is not asserted: every answer this executor produces is
        # built from a retrieval call, so requiring one would score 1.0 for
        # every case in every version and discriminate nothing.
        require_tool_trace=False,
        format=(
            AnswerFormat(
                forbidden_markers=forbidden,
                min_characters=_MIN_ANSWER_CHARACTERS,
            )
            if expects_answer
            else None
        ),
    )


def to_observation(
    case: TestCase,
    evidence: Iterable[Evidence],
    *,
    trial_index: int = 0,
) -> SampleObservation:
    """Build the engine observation for one executed case.

    ``trial_index`` lets a case be sampled more than once so the comparison can
    separate sampling noise from a real effect; the demo executes each case once
    and leaves it at zero. An errored case carries ``error``, which the engine
    scores as 0.0 rather than judging an answer that was never produced.

    Raises:
        ValueError: if the case has no evidence rows at all. The engine derives
            finding evidence ids from this observation's id, and a finding that
            cannot cite evidence is not a finding.
    """
    ids = evidence_for(case, evidence)
    if not ids:
        raise ValueError(
            f"Case {case.id} has no evidence rows; an observation must cite the "
            "persisted evidence for the answer it scored."
        )

    output = case.output or {}
    return SampleObservation(
        id=ids[0],
        case_id=scenario_id(case),
        run_id=case.run_id,
        version=case.version,
        trial_index=trial_index,
        answer=to_answer_input(output),
        error=None if output else "case produced no output",
    )
