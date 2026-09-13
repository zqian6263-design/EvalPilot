"""Contract tests for the EvalPilot evaluation package.

Everything here is offline and deterministic: the LLM judge is always a fake
async callable. No network access, no LLM SDK, no extra pytest plugins.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from evalpilot.evaluation.checks import (
    CitationPresenceCheck,
    ExpectedFactsCheck,
    RequiredRefusalCheck,
    ResponseFormatCheck,
    run_deterministic_checks,
)
from evalpilot.evaluation.comparison import (
    DEFAULT_REGRESSION_THRESHOLD,
    compare_matched_cases,
    mean_confidence_interval,
)
from evalpilot.evaluation.findings import (
    build_comparison_findings,
    build_missing_evidence_findings,
    severity_for,
)
from evalpilot.evaluation.judge import (
    DEFAULT_RUBRIC,
    JudgeError,
    JudgeOutput,
    JudgeResponse,
    RubricJudge,
)
from evalpilot.evaluation.models import (
    AnswerFormat,
    AnswerInput,
    CheckKind,
    CheckOutcome,
    Citation,
    ComparisonDirection,
    EvidenceKind,
    ExpectedBehavior,
    JudgeCriterionScore,
    JudgeRequest,
    SampleObservation,
    Severity,
)
from evalpilot.evaluation.service import (
    ComparisonReport,
    EvaluationService,
    _JudgeBudget,
)


# --------------------------------------------------------------------------
# Fake judge infrastructure (never touches the network)
# --------------------------------------------------------------------------


def make_judge_payload(
    *,
    score: float = 1.0,
    confidence: float = 0.9,
    rationale: str = "Answer satisfies the rubric.",
    criteria: list[dict] | None = None,
) -> dict:
    """Build a well-formed judge payload as a plain dict."""
    if criteria is None:
        criteria = [
            {"name": "faithfulness", "score": score, "rationale": "Grounded in the source."}
        ]
    return {
        "score": score,
        "confidence": confidence,
        "rationale": rationale,
        "criteria": criteria,
    }


def make_judge_json(**kwargs) -> str:
    return json.dumps(make_judge_payload(**kwargs))


class FakeJudge:
    """Async callable that always returns the same raw payload."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.requests: list[JudgeRequest] = []

    async def __call__(self, request: JudgeRequest) -> str:
        self.requests.append(request)
        return self.payload


class ScriptedJudge:
    """Async callable that replays a fixed sequence of raw payloads."""

    def __init__(self, payloads: list[str]) -> None:
        self.payloads = list(payloads)
        self.requests: list[JudgeRequest] = []

    async def __call__(self, request: JudgeRequest) -> str:
        self.requests.append(request)
        if not self.payloads:
            raise AssertionError("Judge called more times than the fake was scripted for.")
        return self.payloads.pop(0)


class RaisingJudge:
    """Async callable that always raises, simulating a transport failure."""

    def __init__(self, message: str = "judge transport down") -> None:
        self.message = message
        self.calls = 0

    async def __call__(self, request: JudgeRequest) -> str:
        self.calls += 1
        raise RuntimeError(self.message)


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------


def build_judge(*, payload: str | None = None, **kwargs) -> RubricJudge:
    """A RubricJudge wired to a single always-repeating fake response."""
    return RubricJudge(judge_fn=FakeJudge(payload if payload is not None else make_judge_json(**kwargs)))


def make_request(**overrides) -> JudgeRequest:
    defaults = dict(
        case_id=str(uuid.uuid4()),
        question="How long do refunds take?",
        answer_text="About 5 business days.",
        rubric="Score groundedness and tone.",
        criteria=["faithfulness"],
    )
    defaults.update(overrides)
    return JudgeRequest(**defaults)


def make_observation(
    case_id: str,
    *,
    version: str = "baseline",
    trial: int = 0,
    text: str = "Refunds take 5 business days.",
    citations: list[str] | None = None,
    tool_calls: list[str] | None = None,
    error: str | None = None,
) -> SampleObservation:
    return SampleObservation(
        id=str(uuid.uuid4()),
        case_id=case_id,
        run_id=str(uuid.uuid4()),
        version=version,
        trial_index=trial,
        answer=AnswerInput(
            text=text,
            citations=[Citation(uri=uri) for uri in (citations or [])],
            tool_calls=tool_calls or [],
        ),
        error=error,
    )


def make_evidence_ids() -> list[str]:
    return [str(uuid.uuid4())]


def observed(case_id: str, *, version: str = "baseline", **kwargs) -> SampleObservation:
    """Shorthand for a non-error answer observation."""
    return make_observation(case_id, version=version, **kwargs)


# --------------------------------------------------------------------------
# Deterministic checks: format
# --------------------------------------------------------------------------


def test_format_check_flags_answer_that_violates_constraints():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(
        format=AnswerFormat(
            required_markers=["SOURCES:"],
            forbidden_markers=["As an AI language model"],
            min_characters=10,
        )
    )

    outcome = ResponseFormatCheck().run(observed(case_id, text="I cannot help with that."), expected)

    assert outcome.kind is CheckKind.FORMAT
    assert outcome.applicable is True
    assert outcome.passed is False
    assert outcome.score == 0.0
    assert "SOURCES:" in outcome.rationale


def test_format_check_flags_forbidden_marker_in_otherwise_valid_answer():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(
        format=AnswerFormat(required_markers=["SOURCES:"], forbidden_markers=["As an AI language model"])
    )

    text = "As an AI language model I would say refunds take 5 days. SOURCES: kb/refunds.md"
    outcome = ResponseFormatCheck().run(observed(case_id, text=text), expected)

    assert outcome.passed is False
    assert "As an AI language model" in outcome.rationale


def test_format_check_passes_well_formed_answer():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(format=AnswerFormat(required_markers=["SOURCES:"], min_characters=5))

    outcome = ResponseFormatCheck().run(
        observed(case_id, text="Refunds take 5 days. SOURCES: kb/refunds.md"), expected
    )

    assert outcome.passed is True
    assert outcome.score == 1.0


def test_format_check_is_inapplicable_without_a_format_spec():
    outcome = ResponseFormatCheck().run(observed(str(uuid.uuid4())), ExpectedBehavior())

    assert outcome.applicable is False


# --------------------------------------------------------------------------
# Deterministic checks: required refusal
# --------------------------------------------------------------------------


def test_refusal_check_flags_answer_that_answered_instead_of_refusing():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(require_refusal=True)

    outcome = RequiredRefusalCheck().run(
        observed(case_id, text="The admin password is hunter2."), expected
    )

    assert outcome.kind is CheckKind.REFUSAL
    assert outcome.passed is False
    assert outcome.score == 0.0


def test_refusal_check_passes_on_refusal():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(require_refusal=True)

    outcome = RequiredRefusalCheck().run(
        observed(case_id, text="I cannot share credentials, but I can help you reset them."), expected
    )

    assert outcome.passed is True
    assert outcome.score == 1.0


def test_refusal_check_is_inapplicable_when_the_expected_behavior_is_to_answer():
    outcome = RequiredRefusalCheck().run(
        observed(str(uuid.uuid4()), text="Refunds take 5 days."), ExpectedBehavior(require_refusal=False)
    )

    assert outcome.applicable is False


# --------------------------------------------------------------------------
# Deterministic checks: citation presence
# --------------------------------------------------------------------------


def test_citation_check_flags_uncited_claim():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(require_citation=True)

    outcome = CitationPresenceCheck().run(observed(case_id, citations=[]), expected)

    assert outcome.kind is CheckKind.CITATION
    assert outcome.passed is False
    assert outcome.score == 0.0
    assert "citation" in outcome.rationale.lower()


def test_citation_check_passes_with_citation():
    expected = ExpectedBehavior(require_citation=True)

    outcome = CitationPresenceCheck().run(
        observed(str(uuid.uuid4()), citations=["kb/refunds.md"]), expected
    )

    assert outcome.passed is True


def test_citation_check_ignores_citations_carried_in_the_answer_text():
    """A citation must be structured evidence, not a substring of prose."""
    expected = ExpectedBehavior(require_citation=True)

    outcome = CitationPresenceCheck().run(
        observed(str(uuid.uuid4()), text="See kb/refunds.md for details.", citations=[]), expected
    )

    assert outcome.passed is False


# --------------------------------------------------------------------------
# Deterministic checks: expected fact / keyword coverage
# --------------------------------------------------------------------------


def test_expected_facts_check_scores_partial_keyword_coverage():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(
        required_keywords=["5 business days", "original payment method", "no fee"]
    )

    outcome = ExpectedFactsCheck().run(
        observed(
            case_id,
            text="Refunds take 5 business days and go to your original payment method.",
        ),
        expected,
    )

    assert outcome.kind is CheckKind.FACTS
    assert outcome.passed is False
    assert outcome.score == pytest.approx(2 / 3)


def test_expected_facts_check_is_case_insensitive():
    expected = ExpectedBehavior(required_keywords=["5 Business Days"])

    outcome = ExpectedFactsCheck().run(
        observed(str(uuid.uuid4()), text="refunds take 5 business days"), expected
    )

    assert outcome.passed is True


def test_expected_facts_check_passes_when_all_keywords_present():
    expected = ExpectedBehavior(required_keywords=["5 business days", "original payment method"])

    outcome = ExpectedFactsCheck().run(
        observed(
            str(uuid.uuid4()),
            text="Refunds take 5 business days to your original payment method.",
        ),
        expected,
    )

    assert outcome.passed is True
    assert outcome.score == 1.0


def test_expected_facts_check_is_inapplicable_without_required_keywords():
    outcome = ExpectedFactsCheck().run(observed(str(uuid.uuid4())), ExpectedBehavior())

    assert outcome.applicable is False


# --------------------------------------------------------------------------
# Deterministic checks: aggregation over the default check suite
# --------------------------------------------------------------------------


def test_run_deterministic_checks_reports_every_check_kind():
    outcomes = run_deterministic_checks(
        observed(str(uuid.uuid4()), text="no.", citations=[]), ExpectedBehavior()
    )

    assert {o.kind for o in outcomes} == {
        CheckKind.FORMAT,
        CheckKind.REFUSAL,
        CheckKind.CITATION,
        CheckKind.TOOL_TRACE,
        CheckKind.FACTS,
    }
    assert all(o.applicable is False for o in outcomes)


def test_run_deterministic_checks_averages_only_applicable_outcomes():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(required_keywords=["5 business days"], require_citation=True)

    # Facts pass (1.0), citation fails (0.0), format/refusal inapplicable.
    outcomes = run_deterministic_checks(
        observed(case_id, text="Refunds take 5 business days.", citations=[]), expected
    )
    applicable = [o for o in outcomes if o.applicable]

    assert len(applicable) == 2
    assert sum(o.score for o in applicable) / len(applicable) == pytest.approx(0.5)


# --------------------------------------------------------------------------
# LLM judge protocol
# --------------------------------------------------------------------------


def test_judge_returns_typed_output_for_valid_payload():
    judge = build_judge(score=0.8, confidence=0.7)
    payload = make_judge_payload(
        score=0.8,
        confidence=0.7,
        criteria=[
            {"name": "faithfulness", "score": 0.9, "rationale": "Grounded."},
            {"name": "tone", "score": 0.7, "rationale": "Slightly terse."},
        ],
    )
    judge = RubricJudge(judge_fn=FakeJudge(json.dumps(payload)))

    output = asyncio.run(judge.judge(make_request(criteria=["faithfulness", "tone"])))

    assert isinstance(output, JudgeOutput)
    assert output.score == pytest.approx(0.8)
    assert output.confidence == pytest.approx(0.7)
    assert [c.name for c in output.criteria] == ["faithfulness", "tone"]
    assert all(isinstance(c, JudgeCriterionScore) for c in output.criteria)
    assert output.score_for("tone") == pytest.approx(0.7)
    assert output.score_for("missing") is None


def test_judge_raises_on_malformed_json():
    judge = RubricJudge(judge_fn=ScriptedJudge(["this is not json at all"]))

    with pytest.raises(JudgeError, match="not valid JSON"):
        asyncio.run(judge.judge(make_request()))


def test_judge_raises_on_json_that_violates_the_schema():
    payload = {"score": "high", "confidence": 2.0, "criteria": "nope"}
    judge = RubricJudge(judge_fn=ScriptedJudge([json.dumps(payload)]))

    with pytest.raises(JudgeError, match="schema"):
        asyncio.run(judge.judge(make_request()))


def test_judge_raises_on_out_of_range_score():
    judge = RubricJudge(judge_fn=ScriptedJudge([make_judge_json(score=1.4)]))

    with pytest.raises(JudgeError, match="schema"):
        asyncio.run(judge.judge(make_request()))


def test_judge_raises_on_json_that_is_not_an_object():
    judge = RubricJudge(judge_fn=ScriptedJudge(["[1, 2, 3]"]))

    with pytest.raises(JudgeError, match="schema"):
        asyncio.run(judge.judge(make_request()))


def test_judge_accepts_a_payload_wrapped_in_a_markdown_code_fence():
    fenced = "```json\n" + make_judge_json(score=0.4) + "\n```"
    judge = RubricJudge(judge_fn=ScriptedJudge([fenced]))

    output = asyncio.run(judge.judge(make_request()))

    assert output.score == pytest.approx(0.4)


def test_judge_wraps_transport_failure_as_judge_error():
    judge = RubricJudge(judge_fn=RaisingJudge())

    with pytest.raises(JudgeError, match="judge call failed"):
        asyncio.run(judge.judge(make_request()))


def test_judge_prompt_carries_the_rubric_answer_and_criteria():
    judge = RubricJudge(judge_fn=FakeJudge(make_judge_json()))
    request = make_request(
        question="What is the refund window?",
        answer_text="30 days.",
        rubric="Score groundedness.",
        criteria=["faithfulness", "tone"],
    )

    asyncio.run(judge.judge(request))

    sent = judge.judge_fn.requests[0]
    assert sent == request
    assert DEFAULT_RUBRIC  # a default rubric exists for callers that omit one


# --------------------------------------------------------------------------
# Comparison statistics
# --------------------------------------------------------------------------


def test_matched_comparison_detects_stable_improvement():
    pairs = [
        (0.40, 0.90),
        (0.50, 0.85),
        (0.30, 0.80),
        (0.45, 0.95),
        (0.35, 0.88),
    ]

    result = compare_matched_cases(pairs, seed=7)

    assert result.mean_difference == pytest.approx(0.476, abs=1e-3)
    assert result.direction is ComparisonDirection.IMPROVEMENT
    assert result.is_significant is True
    assert result.ci_lower > 0
    assert result.effect_size > 0
    assert result.confidence > 0.95
    assert result.sample_size == 5


def test_matched_comparison_detects_stable_regression():
    pairs = [
        (0.90, 0.35),
        (0.88, 0.42),
        (0.92, 0.30),
        (0.85, 0.48),
        (0.91, 0.39),
    ]

    result = compare_matched_cases(pairs, seed=7)

    assert result.mean_difference == pytest.approx(-0.504, abs=1e-3)
    assert result.direction is ComparisonDirection.REGRESSION
    assert result.is_significant is True
    assert result.ci_upper < 0
    assert result.effect_size < 0
    assert result.confidence > 0.95


def test_matched_comparison_reports_noise_as_non_regression():
    pairs = [
        (0.80, 0.74),
        (0.72, 0.83),
        (0.88, 0.79),
        (0.69, 0.81),
        (0.77, 0.71),
    ]

    result = compare_matched_cases(pairs, seed=7)

    assert result.direction is ComparisonDirection.INCONCLUSIVE
    assert result.is_significant is False
    assert result.ci_lower < 0 < result.ci_upper
    assert result.confidence < 0.95


def test_matched_comparison_is_invariant_to_a_uniform_case_difficulty_shift():
    """Matched pairing must cancel out how hard the shared cases happen to be."""
    pairs = [(0.80, 0.70), (0.60, 0.50), (0.90, 0.80), (0.70, 0.60), (0.50, 0.40)]
    harder = [(baseline - 0.25, candidate - 0.25) for baseline, candidate in pairs]

    easy_result = compare_matched_cases(pairs, seed=7)
    hard_result = compare_matched_cases(harder, seed=7)

    assert easy_result.mean_difference == pytest.approx(hard_result.mean_difference)
    assert easy_result.direction is hard_result.direction is ComparisonDirection.REGRESSION
    assert easy_result.ci_lower == pytest.approx(hard_result.ci_lower)


def test_matched_comparison_treats_a_sub_threshold_drop_as_inconclusive():
    pairs = [(0.80, 0.79), (0.82, 0.805), (0.78, 0.775), (0.81, 0.80), (0.79, 0.785)]

    result = compare_matched_cases(pairs, seed=7)

    assert result.mean_difference == pytest.approx(-0.009, abs=1e-4)
    assert result.direction is ComparisonDirection.INCONCLUSIVE, "a 1-point drop is below threshold"
    assert result.is_significant is False


def test_matched_comparison_respects_a_custom_threshold():
    pairs = [(0.80, 0.79), (0.82, 0.805), (0.78, 0.775), (0.81, 0.80), (0.79, 0.785)]

    result = compare_matched_cases(pairs, seed=7, threshold=0.005)

    assert result.direction is ComparisonDirection.REGRESSION
    assert result.is_significant is True
    assert result.threshold == pytest.approx(0.005)


def test_matched_comparison_uses_the_documented_default_threshold():
    assert DEFAULT_REGRESSION_THRESHOLD == pytest.approx(0.05)


def test_matched_comparison_handles_zero_variance_without_dividing_by_zero():
    pairs = [(0.80, 0.70)] * 5

    result = compare_matched_cases(pairs, seed=7)

    assert result.std_difference == pytest.approx(0.0)
    assert result.effect_size == pytest.approx(0.0)
    assert result.direction is ComparisonDirection.REGRESSION


def test_zero_variance_regression_reports_full_confidence_not_zero():
    """Every case moving by the same amount is the strongest evidence there is.

    The standard error collapses to zero here, which previously produced a
    confidence of 0.0 and downgraded a perfectly consistent regression.
    """
    pairs = [(0.80, 0.70)] * 5

    result = compare_matched_cases(pairs, seed=7)

    assert result.mean_difference == pytest.approx(-0.10)
    assert result.confidence == pytest.approx(1.0)
    assert severity_for(result) is Severity.MEDIUM, "a 0.10 drop is medium, not low"


def test_zero_variance_inconclusive_delta_stays_at_zero_confidence():
    pairs = [(0.80, 0.79)] * 5

    result = compare_matched_cases(pairs, seed=7)

    assert result.direction is ComparisonDirection.INCONCLUSIVE
    assert result.confidence == pytest.approx(0.0)


def test_matched_design_resists_a_harder_test_set_that_is_not_a_regression():
    """The product's core claim: test difficulty must not read as a regression.

    An unpaired comparison of an easy baseline set against a hard candidate set
    reports a large drop. The matched design, given the same model and matched
    cases, correctly reports that nothing changed.
    """
    easy_cases = [0.92, 0.95, 0.88, 0.94, 0.90, 0.93]
    hard_cases = [0.41, 0.38, 0.45, 0.35, 0.42, 0.39]

    naive_unpaired_delta = sum(hard_cases) / len(hard_cases) - sum(easy_cases) / len(easy_cases)
    assert naive_unpaired_delta < -0.45, "the naive comparison is badly misleading here"

    # Matched: each case is compared against itself, exactly as the service does.
    matched = compare_matched_cases([(score, score) for score in hard_cases], seed=7)

    assert matched.direction is ComparisonDirection.INCONCLUSIVE
    assert matched.is_significant is False
    assert matched.mean_difference == pytest.approx(0.0)


def test_matched_comparison_returns_an_inconclusive_result_for_no_pairs():
    result = compare_matched_cases([], seed=7)

    assert result.sample_size == 0
    assert result.mean_difference == 0.0
    assert result.direction is ComparisonDirection.INCONCLUSIVE
    assert result.is_significant is False
    assert result.confidence == 0.0


def test_matched_comparison_is_deterministic_for_a_fixed_seed():
    pairs = [(0.4, 0.9), (0.5, 0.85), (0.3, 0.8), (0.45, 0.95), (0.35, 0.88)]

    assert compare_matched_cases(pairs, seed=1234) == compare_matched_cases(pairs, seed=1234)


def test_matched_comparison_seed_changes_only_the_interval_not_the_point_estimate():
    pairs = [(0.4, 0.9), (0.5, 0.85), (0.3, 0.8), (0.45, 0.95), (0.35, 0.88)]

    first = compare_matched_cases(pairs, seed=1)
    second = compare_matched_cases(pairs, seed=2)

    assert first.mean_difference == pytest.approx(second.mean_difference)
    assert first.effect_size == pytest.approx(second.effect_size)


def test_bootstrap_interval_brackets_the_mean_for_well_behaved_data():
    differences = [-0.30, -0.25, -0.40, -0.35, -0.28, -0.32, -0.36, -0.22]

    interval = mean_confidence_interval(differences, seed=11)

    assert interval.lower < interval.point < interval.upper
    assert interval.upper < 0.0


def test_bootstrap_interval_is_degenerate_for_a_single_sample():
    interval = mean_confidence_interval([-0.4], seed=11)

    assert interval.point == pytest.approx(-0.4)
    assert interval.lower == pytest.approx(-0.4)
    assert interval.upper == pytest.approx(-0.4)


def test_bootstrap_interval_of_nothing_is_empty():
    interval = mean_confidence_interval([], seed=11)

    assert interval.point == 0.0
    assert interval.lower == 0.0
    assert interval.upper == 0.0


# --------------------------------------------------------------------------
# Evaluation service: repeated-sample aggregation
# --------------------------------------------------------------------------


def test_service_aggregates_repeated_samples_by_mean():
    case_id = str(uuid.uuid4())
    observations = [
        observed(case_id, version="baseline", trial=0, text="yes"),
        observed(case_id, version="baseline", trial=1, text="no"),
    ]

    outcome = EvaluationService().evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(required_keywords=["yes"]),
        observations=observations,
    )

    assert outcome.trial_counts["baseline"] == 2
    assert outcome.scores_by_version["baseline"] == pytest.approx(0.5)
    assert outcome.average == pytest.approx(0.5)


def test_service_keeps_versions_separate():
    case_id = str(uuid.uuid4())
    observations = [
        observed(case_id, version="baseline", trial=0, text="yes"),
        observed(case_id, version="candidate", trial=0, text="no"),
    ]

    outcome = EvaluationService().evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(required_keywords=["yes"]),
        observations=observations,
    )

    assert outcome.scores_by_version["baseline"] == pytest.approx(1.0)
    assert outcome.scores_by_version["candidate"] == pytest.approx(0.0)


def test_service_records_error_observations_as_zero_without_judging():
    case_id = str(uuid.uuid4())
    observations = [
        make_observation(
            case_id=case_id, version="candidate", trial=0, text="", error="tool timeout"
        )
    ]

    outcome = EvaluationService().evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(required_keywords=["yes"]),
        observations=observations,
    )

    assert outcome.scores_by_version["candidate"] == pytest.approx(0.0)
    assert outcome.errors == 1


def test_service_deduplicates_missing_evidence_across_trials():
    case_id = str(uuid.uuid4())
    observations = [
        observed(case_id, version="baseline", trial=trial, citations=[]) for trial in range(3)
    ]

    outcome = EvaluationService().evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(require_citation=True),
        observations=observations,
    )

    assert outcome.scores_by_version["baseline"] == pytest.approx(0.0)
    assert len(outcome.missing_evidence) == 1, "three trials of the same gap are one finding"
    gap = outcome.missing_evidence[0]
    assert gap.case_id == case_id
    assert gap.kind is EvidenceKind.CITATION
    assert gap.detected_by is CheckKind.CITATION
    assert gap.occurrences == 3
    assert gap.version == "baseline"


def test_service_reports_a_missing_tool_trace_when_one_is_required():
    case_id = str(uuid.uuid4())
    observations = [observed(case_id, version="candidate", tool_calls=[])]

    outcome = EvaluationService().evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(require_tool_trace=True),
        observations=observations,
    )

    kinds = {gap.kind for gap in outcome.missing_evidence}
    assert kinds == {EvidenceKind.TRACE}
    assert outcome.scores_by_version["candidate"] == pytest.approx(0.0)


def test_service_does_not_report_missing_evidence_for_a_healthy_case():
    case_id = str(uuid.uuid4())
    observations = [
        observed(case_id, citations=["kb/refunds.md"], tool_calls=["search_kb"]),
    ]

    outcome = EvaluationService().evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(require_citation=True, require_tool_trace=True),
        observations=observations,
    )

    assert outcome.missing_evidence == []
    assert outcome.scores_by_version["baseline"] == pytest.approx(1.0)


def test_service_ignores_other_cases_observations():
    wanted = str(uuid.uuid4())
    other = str(uuid.uuid4())
    observations = [
        observed(wanted, version="baseline", text="yes"),
        observed(other, version="baseline", text="no"),
    ]

    outcome = EvaluationService().evaluate_case(
        case_id=wanted,
        expected=ExpectedBehavior(required_keywords=["yes"]),
        observations=observations,
    )

    assert outcome.scores_by_version["baseline"] == pytest.approx(1.0)
    assert outcome.trial_counts["baseline"] == 1


# --------------------------------------------------------------------------
# Evaluation service: judge integration
# --------------------------------------------------------------------------


def test_service_blends_deterministic_and_judge_scores_when_a_rubric_is_given():
    case_id = str(uuid.uuid4())
    service = EvaluationService(judge=build_judge(score=0.6), judge_criteria=["faithfulness"])
    observations = [
        observed(case_id, version="baseline", text="a"),
        observed(case_id, version="candidate", text="b"),
    ]

    outcome = service.evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(require_citation=True),
        observations=observations,
        rubric="Score faithfulness.",
    )

    # The citation check fails on both arms (so deterministic scores are 0.0)
    # and the judge returns 0.6, giving an equal-weight blend of 0.3.
    assert outcome.judge_scores_by_version["baseline"] == pytest.approx(0.6)
    assert outcome.deterministic_scores_by_version["baseline"] == pytest.approx(0.0)
    assert outcome.scores_by_version["baseline"] == pytest.approx(0.3)
    assert outcome.judge_failures == 0


def test_service_aggregates_judge_token_usage() -> None:
    case_id = str(uuid.uuid4())

    async def metered(_request: JudgeRequest) -> JudgeResponse:
        return JudgeResponse(
            text=make_judge_json(score=0.8),
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        )

    service = EvaluationService(judge=RubricJudge(judge_fn=metered))
    outcome = service.evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(required_keywords=["a"]),
        observations=[
            observed(case_id, version="baseline", text="a"),
            observed(case_id, version="candidate", text="a"),
        ],
        rubric="Score faithfulness.",
    )

    assert outcome.judge_usage == {
        "prompt_tokens": 20,
        "completion_tokens": 10,
        "total_tokens": 30,
    }


def test_judge_call_budget_skips_further_calls() -> None:
    case_id = str(uuid.uuid4())

    async def metered(_request: JudgeRequest) -> JudgeResponse:
        return JudgeResponse(
            text=make_judge_json(score=0.8),
            usage={"prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10},
        )

    service = EvaluationService(
        judge=RubricJudge(judge_fn=metered),
        max_judge_calls=1,
    )
    outcome = service.evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(required_keywords=["a"]),
        observations=[
            observed(case_id, version="baseline", text="a"),
            observed(case_id, version="candidate", text="a"),
        ],
        rubric="Score faithfulness.",
    )

    assert outcome.judge_usage["total_tokens"] == 10
    assert outcome.judge_skipped == 1


def test_judge_token_budget_exhaustion_is_observable() -> None:
    budget = _JudgeBudget(max_tokens=10)
    assert budget.reserve() is True
    budget.record({"total_tokens": 10})
    assert budget.exhausted is True
    assert budget.reserve() is False
    assert budget.skipped == 1


def test_service_skips_the_judge_entirely_without_a_rubric():
    case_id = str(uuid.uuid4())
    judge = FakeJudge(make_judge_json())
    service = EvaluationService(judge=RubricJudge(judge_fn=judge))

    outcome = service.evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(required_keywords=["5 business days"]),
        observations=[observed(case_id)],
    )

    assert judge.requests == []
    assert outcome.judge_scores_by_version == {}
    assert outcome.scores_by_version["baseline"] == pytest.approx(1.0)


def test_service_counts_invalid_judge_output_without_raising():
    case_id = str(uuid.uuid4())
    service = EvaluationService(
        judge=RubricJudge(judge_fn=FakeJudge("not json")), judge_criteria=["faithfulness"]
    )
    observations = [
        observed(case_id, version="baseline", text="a"),
        observed(case_id, version="candidate", text="b"),
    ]

    outcome = service.evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(required_keywords=["a"]),
        observations=observations,
        rubric="Score faithfulness.",
    )

    assert outcome.judge_failures == 2
    assert outcome.judge_scores_by_version == {}
    # Deterministic scoring still works, so the run is not lost.
    assert outcome.scores_by_version["baseline"] == pytest.approx(1.0)
    assert outcome.scores_by_version["candidate"] == pytest.approx(0.0)


def test_service_does_not_judge_errored_observations():
    case_id = str(uuid.uuid4())
    judge = FakeJudge(make_judge_json())
    service = EvaluationService(judge=RubricJudge(judge_fn=judge), judge_criteria=["faithfulness"])

    service.evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(),
        observations=[make_observation(case_id, text="", error="timeout")],
        rubric="Score faithfulness.",
    )

    assert judge.requests == []


def test_service_async_entrypoint_matches_the_sync_one():
    case_id = str(uuid.uuid4())
    expected = ExpectedBehavior(required_keywords=["yes"])
    observations = [
        observed(case_id, version="baseline", trial=0, text="yes"),
        observed(case_id, version="baseline", trial=1, text="no"),
        observed(case_id, version="candidate", trial=0, text="no"),
    ]

    sync_outcome = EvaluationService().evaluate_case(
        case_id=case_id, expected=expected, observations=observations
    )
    async_outcome = asyncio.run(
        EvaluationService().evaluate_case_async(
            case_id=case_id, expected=expected, observations=observations
        )
    )

    assert async_outcome.scores_by_version == sync_outcome.scores_by_version


def test_service_rejects_an_observation_for_a_different_case():
    case_id = str(uuid.uuid4())
    other = str(uuid.uuid4())

    with pytest.raises(ValueError, match="case_id"):
        EvaluationService().evaluate_case(
            case_id=case_id,
            expected=ExpectedBehavior(),
            observations=[observed(other)],
        )


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


def test_findings_always_carry_evidence_ids():
    case_id = str(uuid.uuid4())
    pairs = [(0.90, 0.35), (0.88, 0.42), (0.92, 0.30), (0.85, 0.48), (0.91, 0.39)]
    comparison = compare_matched_cases(pairs, seed=7)
    evidence_ids = make_evidence_ids()

    findings = build_comparison_findings(
        comparison=comparison,
        case_ids=[case_id],
        evidence_ids=evidence_ids,
        title="Candidate regressed on refund policy questions",
        description="Mean score dropped by 0.50 across five matched cases.",
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity is Severity.CRITICAL
    assert finding.evidence_ids == evidence_ids
    assert finding.case_id == case_id
    assert 0.0 <= finding.confidence <= 1.0
    assert finding.recommendation
    assert finding.rationale


def test_findings_refuse_to_emit_without_evidence():
    comparison = compare_matched_cases([(0.9, 0.3), (0.88, 0.4)], seed=7)

    with pytest.raises(ValueError, match="evidence"):
        build_comparison_findings(
            comparison=comparison,
            case_ids=[str(uuid.uuid4())],
            evidence_ids=[],
            title="Regression",
            description="No evidence attached.",
        )


def test_finding_model_itself_rejects_an_empty_evidence_list():
    from evalpilot.evaluation.models import Finding

    with pytest.raises(Exception):
        Finding(
            id=str(uuid.uuid4()),
            severity=Severity.HIGH,
            title="t",
            description="d",
            confidence=0.9,
            evidence_ids=[],
            rationale="r",
        )


def test_missing_evidence_findings_always_carry_evidence_ids():
    case_id = str(uuid.uuid4())
    outcome = EvaluationService().evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(require_citation=True),
        observations=[observed(case_id, citations=[])],
    )
    evidence_ids = make_evidence_ids()

    findings = build_missing_evidence_findings(
        missing_evidence=outcome.missing_evidence,
        evidence_ids_by_case={case_id: evidence_ids},
    )

    assert len(findings) == 1
    assert findings[0].evidence_ids == evidence_ids
    assert findings[0].severity is Severity.HIGH
    assert findings[0].case_id == case_id


def test_missing_evidence_findings_refuse_to_emit_without_evidence():
    case_id = str(uuid.uuid4())
    outcome = EvaluationService().evaluate_case(
        case_id=case_id,
        expected=ExpectedBehavior(require_citation=True),
        observations=[observed(case_id, citations=[])],
    )

    with pytest.raises(ValueError, match="evidence"):
        build_missing_evidence_findings(
            missing_evidence=outcome.missing_evidence,
            evidence_ids_by_case={case_id: []},
        )


def test_severity_scales_with_magnitude_and_confidence():
    small = compare_matched_cases(
        [(0.80, 0.79), (0.82, 0.805), (0.78, 0.775), (0.81, 0.80), (0.79, 0.785)],
        seed=7,
        threshold=0.005,
    )
    large = compare_matched_cases(
        [(0.95, 0.20), (0.93, 0.25), (0.97, 0.18), (0.94, 0.22)], seed=7
    )

    assert severity_for(large) is Severity.CRITICAL
    assert severity_for(small).rank < severity_for(large).rank


def test_severity_is_info_for_an_inconclusive_comparison():
    noisy = compare_matched_cases(
        [(0.80, 0.74), (0.72, 0.83), (0.88, 0.79), (0.69, 0.81), (0.77, 0.71)], seed=7
    )

    assert severity_for(noisy) is Severity.INFO


def test_severity_ranks_are_ordered():
    assert Severity.INFO.rank < Severity.LOW.rank < Severity.MEDIUM.rank
    assert Severity.MEDIUM.rank < Severity.HIGH.rank < Severity.CRITICAL.rank


# --------------------------------------------------------------------------
# End-to-end service comparison
# --------------------------------------------------------------------------


def build_regression_observations(case_ids, *, trials: int = 3):
    observations = []
    for case_id in case_ids:
        for trial in range(trials):
            observations.append(
                observed(
                    case_id,
                    version="baseline",
                    trial=trial,
                    text="Refunds take 5 business days. SOURCES: kb/refunds.md",
                    citations=["kb/refunds.md"],
                    tool_calls=["search_kb"],
                )
            )
            observations.append(
                observed(
                    case_id,
                    version="candidate",
                    trial=trial,
                    text="Refunds are not available.",
                    citations=[],
                    tool_calls=[],
                )
            )
    return observations


def test_service_full_comparison_flags_a_regression_with_evidence():
    case_ids = [str(uuid.uuid4()) for _ in range(3)]
    evidence_by_case = {case_id: make_evidence_ids() for case_id in case_ids}

    report = EvaluationService().compare(
        observations=build_regression_observations(case_ids),
        expectations={
            case_id: ExpectedBehavior(
                required_keywords=["business days"],
                require_citation=True,
                require_tool_trace=True,
            )
            for case_id in case_ids
        },
        evidence_ids_by_case=evidence_by_case,
    )

    assert isinstance(report, ComparisonReport)
    assert report.comparison.direction is ComparisonDirection.REGRESSION
    assert report.comparison.is_significant is True
    assert report.comparison.sample_size == 3
    assert report.comparison.trial_count == 3
    assert report.findings, "a confirmed regression must produce a finding"
    assert all(f.evidence_ids for f in report.findings)
    assert "candidate_mean" in report.metrics
    assert report.metrics["case_count"] == 3


def test_service_comparison_reports_a_clean_candidate_as_no_regression():
    case_ids = [str(uuid.uuid4()) for _ in range(3)]
    evidence_by_case = {case_id: make_evidence_ids() for case_id in case_ids}
    observations = []
    for case_id in case_ids:
        for trial in range(3):
            for version in ("baseline", "candidate"):
                observations.append(
                    observed(
                        case_id,
                        version=version,
                        trial=trial,
                        text="Refunds take 5 business days.",
                        citations=["kb/refunds.md"],
                        tool_calls=["search_kb"],
                    )
                )

    report = EvaluationService().compare(
        observations=observations,
        expectations={
            case_id: ExpectedBehavior(required_keywords=["business days"], require_citation=True)
            for case_id in case_ids
        },
        evidence_ids_by_case=evidence_by_case,
    )

    assert report.comparison.direction is ComparisonDirection.INCONCLUSIVE
    assert report.comparison.is_significant is False
    assert report.findings == []
    assert report.metrics["candidate_mean"] == pytest.approx(1.0)
    assert report.metrics["baseline_mean"] == pytest.approx(1.0)


def test_service_comparison_excludes_cases_that_are_not_matched():
    matched = str(uuid.uuid4())
    baseline_only = str(uuid.uuid4())
    observations = [
        observed(matched, version="baseline", text="yes"),
        observed(matched, version="candidate", text="no"),
        observed(baseline_only, version="baseline", text="yes"),
    ]

    report = EvaluationService().compare(
        observations=observations,
        expectations={
            matched: ExpectedBehavior(required_keywords=["yes"]),
            baseline_only: ExpectedBehavior(required_keywords=["yes"]),
        },
        evidence_ids_by_case={
            matched: make_evidence_ids(),
            baseline_only: make_evidence_ids(),
        },
    )

    assert report.comparison.sample_size == 1
    assert report.excluded_case_ids == [baseline_only]
    assert any("not matched" in warning for warning in report.warnings)


def test_service_comparison_warns_about_cases_without_expectations():
    case_id = str(uuid.uuid4())

    report = EvaluationService().compare(
        observations=[observed(case_id, version="baseline"), observed(case_id, version="candidate")],
        expectations={},
        evidence_ids_by_case={case_id: make_evidence_ids()},
    )

    assert any("expectation" in warning for warning in report.warnings)


def test_service_comparison_does_not_emit_findings_it_cannot_attribute_to_evidence():
    case_ids = [str(uuid.uuid4()) for _ in range(3)]

    report = EvaluationService().compare(
        observations=build_regression_observations(case_ids, trials=2),
        expectations={
            case_id: ExpectedBehavior(required_keywords=["business days"], require_citation=True)
            for case_id in case_ids
        },
        evidence_ids_by_case={},
    )

    assert report.comparison.direction is ComparisonDirection.REGRESSION
    assert report.findings == [], "an unattributable finding must be suppressed, not invented"
    assert any("no evidence" in warning for warning in report.warnings)


def test_comparison_run_is_stable_across_repeats():
    case_ids = [str(uuid.uuid4()) for _ in range(4)]
    evidence_by_case = {case_id: make_evidence_ids() for case_id in case_ids}
    observations = []
    for case_id in case_ids:
        for trial in range(4):
            observations.append(
                observed(case_id, version="baseline", trial=trial, text="Refunds take 5 business days.")
            )
            observations.append(
                observed(case_id, version="candidate", trial=trial, text="Refunds take 30 business days.")
            )

    expectations = {
        case_id: ExpectedBehavior(required_keywords=["5 business days"]) for case_id in case_ids
    }

    def run_once():
        return EvaluationService().compare(
            observations=observations,
            expectations=expectations,
            evidence_ids_by_case=evidence_by_case,
        )

    first = run_once()
    second = run_once()

    assert first.comparison == second.comparison
    assert [f.severity for f in first.findings] == [f.severity for f in second.findings]
    assert first.metrics["candidate_mean"] == pytest.approx(second.metrics["candidate_mean"])


def test_comparison_json_round_trip_carries_evidence_ids():
    case_id = str(uuid.uuid4())
    evidence_by_case = {case_id: make_evidence_ids()}

    report = EvaluationService().compare(
        observations=build_regression_observations([case_id], trials=2),
        expectations={
            case_id: ExpectedBehavior(required_keywords=["business days"], require_citation=True)
        },
        evidence_ids_by_case=evidence_by_case,
    )

    restored = ComparisonReport.model_validate_json(report.model_dump_json())

    assert restored.findings[0].evidence_ids == evidence_by_case[case_id]
    assert restored.comparison.direction is report.comparison.direction


# --------------------------------------------------------------------------
# Model hygiene
# --------------------------------------------------------------------------


def test_check_outcome_defaults_are_conservative():
    outcome = CheckOutcome(kind=CheckKind.FORMAT, passed=False, score=0.0, rationale="r")

    assert outcome.applicable is True
    assert outcome.weight == pytest.approx(1.0)
    assert outcome.evidence_ids == []


def test_answer_format_rejects_a_nonsensical_character_window():
    with pytest.raises(Exception):
        AnswerFormat(min_characters=100, max_characters=10)


def test_expected_behavior_is_empty_by_default():
    expected = ExpectedBehavior()

    assert expected.required_keywords == []
    assert expected.require_citation is False
    assert expected.require_refusal is False
    assert expected.require_tool_trace is False
    assert expected.format is None
