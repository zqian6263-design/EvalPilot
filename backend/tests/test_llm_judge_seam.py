"""The judge seam: live mode installs a provider-backed judge, offline does not.

The important claim is negative. In deterministic mode no judge is installed at
all, so ``EvaluationService`` reports exactly what it reported before this
feature existed. In live mode a judge is installed, but the fixture executor
does not record the question text a judge needs, so the run still warns instead
of blending a non-reproducible score into the verdict.

No test here opens a socket: the adapter is exercised through a fake provider
and the client through ``httpx.MockTransport``.
"""

from __future__ import annotations

import asyncio
import json

from evalpilot.config import load_settings
from evalpilot.container import build_container
from evalpilot.evaluation.judge import JudgeError, RubricJudge, parse_judge_output
from evalpilot.evaluation.models import JudgeRequest
from evalpilot.llm.judge_adapter import ProviderJudge, build_judge_callable
from evalpilot.llm.runtime import MODE_LIVE, LLMRuntime, build_runtime

from .llm_fakes import CANARY_KEY, VALID_RATIONALE, ScriptedProvider

REQUEST = JudgeRequest(
    case_id="scenario-1",
    question="How long is the refund window?",
    answer_text="Thirty days from delivery.",
    rubric="Score grounding and directness.",
    criteria=["grounding"],
)


def _runtime(provider) -> LLMRuntime:
    return LLMRuntime(
        mode=MODE_LIVE,
        configured=True,
        provider=provider,
        model="stub-model",
        base_url_host="api.deepseek.com",
        timeout_seconds=5.0,
    )


def test_deterministic_mode_builds_no_judge_callable() -> None:
    runtime = build_runtime(load_settings({}))
    assert runtime.provider is None
    assert build_judge_callable(runtime) is None


def test_live_mode_builds_a_judge_callable() -> None:
    callable_ = build_judge_callable(_runtime(ScriptedProvider([VALID_RATIONALE])))
    assert callable_ is not None


def test_live_mode_without_a_key_builds_no_judge_callable() -> None:
    runtime = build_runtime(
        load_settings(
            {
                "EVALPILOT_LLM_MODE": "live",
                "EVALPILOT_LLM_BASE_URL": "https://api.deepseek.com",
                "EVALPILOT_LLM_MODEL": "m",
            }
        )
    )
    assert build_judge_callable(runtime) is None


def test_the_judge_scores_from_a_valid_provider_response() -> None:
    payload = {
        "score": 0.8,
        "confidence": 0.6,
        "rationale": "Grounded and direct.",
        "criteria": [{"name": "grounding", "score": 0.9, "rationale": "Cited."}],
    }
    provider = ScriptedProvider([payload])
    judge = RubricJudge(build_judge_callable(_runtime(provider)))

    output = asyncio.run(judge.judge(REQUEST))
    assert output.score == 0.8
    assert output.score_for("grounding") == 0.9
    # The prompt went out as chat messages naming the question and the answer.
    prompt = json.dumps(provider.calls[0])
    assert "refund window" in prompt
    assert "Thirty days from delivery." in prompt


def test_a_schema_violation_raises_judge_error() -> None:
    provider = ScriptedProvider([{"score": 5.0}])
    judge = RubricJudge(build_judge_callable(_runtime(provider)))
    try:
        asyncio.run(judge.judge(REQUEST))
    except JudgeError as exc:
        assert "schema validation" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an out-of-range score was accepted")


def test_a_provider_failure_surfaces_as_a_judge_error() -> None:
    from evalpilot.llm.errors import LLMTimeoutError

    provider = ScriptedProvider([LLMTimeoutError("timed out")])
    judge = RubricJudge(build_judge_callable(_runtime(provider)))
    try:
        asyncio.run(judge.judge(REQUEST))
    except JudgeError as exc:
        assert "timed out" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a provider timeout did not fail the judge")


def test_the_adapter_never_adds_the_key_to_a_failure() -> None:
    """The adapter wraps a failure without echoing the request.

    ``RubricJudge`` catches whatever the callable raises and re-raises it as a
    ``JudgeError`` naming the call. The adapter must contribute nothing of its
    own — no messages, no headers, no key.
    """
    from evalpilot.llm.errors import LLMTransportError

    provider = ScriptedProvider([LLMTransportError("endpoint unreachable")])
    judge = RubricJudge(build_judge_callable(_runtime(provider)))
    try:
        asyncio.run(judge.judge(REQUEST))
    except JudgeError as exc:
        assert "judge call failed" in str(exc)
        assert CANARY_KEY not in str(exc)
        assert "Authorization" not in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a provider failure did not fail the judge")


def test_the_adapter_reserializes_for_one_validation_path() -> None:
    """``RubricJudge`` owns validation; the adapter must hand it JSON text."""
    provider = ScriptedProvider([{"score": 0.5, "rationale": "ok"}])
    adapter = ProviderJudge(provider, runtime=_runtime(provider))
    raw = asyncio.run(adapter(REQUEST))
    assert isinstance(raw, str)
    assert parse_judge_output(raw).score == 0.5


def test_deterministic_container_installs_no_judge(settings) -> None:
    container = build_container(settings)
    assert container.runner.evaluation_service.judge is None
    assert container.llm_runtime.provider is None


def test_live_container_installs_a_judge(settings) -> None:
    live = type(settings)(
        **{
            **{
                field: getattr(settings, field)
                for field in settings.__dataclass_fields__
            },
            "llm_mode": MODE_LIVE,
            "llm_base_url": "https://api.deepseek.com",
            "llm_api_key": CANARY_KEY,
            "llm_model": "deepseek-v4-pro",
        }
    )
    container = build_container(live)
    assert container.runner.evaluation_service.judge is not None
    assert container.llm_runtime.provider is not None
    assert container.llm_runtime.model == "deepseek-v4-pro"


def test_no_frozen_evaluation_module_gained_a_llm_dependency() -> None:
    """The engine stays SDK-free; only the adapter knows about providers."""
    import evalpilot.evaluation.checks as checks
    import evalpilot.evaluation.comparison as comparison
    import evalpilot.evaluation.findings as findings
    import evalpilot.evaluation.judge as judge
    import evalpilot.evaluation.service as service

    for module in (checks, comparison, findings, judge, service):
        source = open(module.__file__, encoding="utf-8").read()
        assert "evalpilot.llm" not in source, module.__file__
