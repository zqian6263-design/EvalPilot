"""The live-LLM runtime: provider, client, schema, and settings.

The offline path is the product's default and must stay untouched, so every
test here either exercises a fake provider or an ``httpx.MockTransport``. No
test in this file opens a socket or needs an API key.
"""

from __future__ import annotations

import json

import httpx
import pytest

from evalpilot.config import DEFAULT_LLM_TIMEOUT_SECONDS, Settings, load_settings
from evalpilot.llm import (
    LLMConfigurationError,
    LLMProvider,
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTransportError,
    OpenAICompatibleProvider,
    build_runtime,
    validate_json_schema,
)
from evalpilot.llm.runtime import MODE_DETERMINISTIC, MODE_LIVE

from .llm_fakes import CANARY_KEY, ScriptedProvider, openai_transport, recording_handler

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["a", "b"]},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["kind"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

MESSAGES = [{"role": "user", "content": "propose something"}]


def make_provider(**overrides) -> OpenAICompatibleProvider:
    kwargs = {
        "base_url": "https://api.deepseek.com",
        "api_key": CANARY_KEY,
        "model": "deepseek-v4-pro",
        "timeout_seconds": 5.0,
        "transport": openai_transport(content=json.dumps({"items": [{"kind": "a", "score": 0.5}]})),
    }
    kwargs.update(overrides)
    return OpenAICompatibleProvider(**kwargs)


# --- provider protocol ------------------------------------------------------


def test_scripted_provider_satisfies_the_protocol() -> None:
    assert isinstance(ScriptedProvider([{}]), LLMProvider)


def test_client_satisfies_the_protocol() -> None:
    assert isinstance(make_provider(), LLMProvider)


def test_client_reports_host_and_endpoint_without_the_key() -> None:
    provider = make_provider()
    assert provider.host == "api.deepseek.com"
    assert provider.endpoint == "https://api.deepseek.com/chat/completions"
    assert CANARY_KEY not in provider.endpoint


# --- success ----------------------------------------------------------------


def test_complete_json_returns_a_validated_payload() -> None:
    import asyncio

    provider = make_provider()
    result = asyncio.run(provider.complete_json(MESSAGES, SCHEMA))
    assert result.payload == {"items": [{"kind": "a", "score": 0.5}]}
    assert result.model == "deepseek-v4-pro"
    assert result.provider == "openai-compatible"
    assert result.call_id
    assert result.provenance() == {
        "source": "llm",
        "model": "deepseek-v4-pro",
        "llm_call_id": result.call_id,
    }


def test_complete_json_records_token_usage() -> None:
    import asyncio

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": '{"items":[{"kind":"a"}]}'}}
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "total_tokens": 150,
                },
            },
        )

    provider = make_provider(transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.complete_json(MESSAGES, SCHEMA))
    assert result.usage == {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
    }
    assert result.provenance()["usage"] == result.usage


def test_client_sends_the_model_and_a_bearer_header() -> None:
    import asyncio

    seen: list[httpx.Request] = []
    provider = make_provider(
        transport=openai_transport(
            recording_handler(json.dumps({"items": [{"kind": "b"}]}), seen=seen)
        )
    )
    asyncio.run(provider.complete_json(MESSAGES, SCHEMA))

    assert len(seen) == 1
    request = seen[0]
    assert request.headers["authorization"] == f"Bearer {CANARY_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-v4-pro"
    assert body["response_format"] == {"type": "json_object"}


def test_complete_text_returns_raw_content() -> None:
    import asyncio

    provider = make_provider(transport=openai_transport(content="plain answer"))
    assert asyncio.run(provider.complete_text(MESSAGES)) == "plain answer"


def test_a_wrapping_code_fence_is_tolerated() -> None:
    import asyncio

    provider = make_provider(
        transport=openai_transport(content='```json\n{"items": [{"kind": "a"}]}\n```')
    )
    assert asyncio.run(provider.complete_json(MESSAGES, SCHEMA)).payload == {
        "items": [{"kind": "a"}]
    }


# --- failure modes ----------------------------------------------------------


def test_malformed_json_is_a_response_error() -> None:
    import asyncio

    provider = make_provider(transport=openai_transport(content="not json at all"))
    with pytest.raises(LLMResponseError, match="not valid JSON"):
        asyncio.run(provider.complete_json(MESSAGES, SCHEMA))


def test_a_non_object_payload_is_a_response_error() -> None:
    import asyncio

    provider = make_provider(transport=openai_transport(content='["a", "b"]'))
    with pytest.raises(LLMResponseError, match="expected an object"):
        asyncio.run(provider.complete_json(MESSAGES, SCHEMA))


def test_a_completion_without_content_is_a_response_error() -> None:
    import asyncio

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    provider = make_provider(transport=httpx.MockTransport(_handler))
    with pytest.raises(LLMResponseError, match="choices"):
        asyncio.run(provider.complete_json(MESSAGES, SCHEMA))


def test_schema_failure_is_a_schema_error_not_a_response_error() -> None:
    import asyncio

    provider = make_provider(
        transport=openai_transport(content=json.dumps({"items": [{"kind": "zzz"}]}))
    )
    with pytest.raises(LLMSchemaError, match="not one of"):
        asyncio.run(provider.complete_json(MESSAGES, SCHEMA))


def test_nan_is_rejected_even_though_json_loads_accepts_it() -> None:
    import asyncio

    provider = make_provider(
        transport=openai_transport(content='{"items": [{"kind": "a", "score": NaN}]}')
    )
    with pytest.raises(LLMSchemaError):
        asyncio.run(provider.complete_json(MESSAGES, SCHEMA))


def test_timeout_is_typed_and_names_the_timeout() -> None:
    import asyncio

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    provider = make_provider(transport=httpx.MockTransport(_handler))
    with pytest.raises(LLMTimeoutError, match="timed out"):
        asyncio.run(provider.complete_text(MESSAGES))


def test_connection_failure_is_a_transport_error() -> None:
    import asyncio

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = make_provider(transport=httpx.MockTransport(_handler))
    with pytest.raises(LLMTransportError, match="failed"):
        asyncio.run(provider.complete_text(MESSAGES))


def test_a_non_2xx_status_is_a_transport_error_carrying_the_status() -> None:
    import asyncio

    provider = make_provider(
        transport=openai_transport(content="{}", status_code=429)
    )
    with pytest.raises(LLMTransportError) as caught:
        asyncio.run(provider.complete_text(MESSAGES))
    assert caught.value.status == 429


def test_missing_configuration_fails_before_any_request() -> None:
    import asyncio

    for overrides, fraction in (
        ({"base_url": ""}, "base URL"),
        ({"api_key": ""}, "API key"),
        ({"model": ""}, "model"),
    ):
        provider = make_provider(**overrides)
        with pytest.raises(LLMConfigurationError, match=fraction):
            asyncio.run(provider.complete_text(MESSAGES))


def test_a_non_positive_timeout_is_a_configuration_error() -> None:
    import asyncio

    provider = make_provider(timeout_seconds=0)
    with pytest.raises(LLMConfigurationError, match="timeout"):
        asyncio.run(provider.complete_text(MESSAGES))


# --- no secret leakage ------------------------------------------------------


def test_no_failure_message_contains_the_api_key() -> None:
    import asyncio

    def _timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    def _refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    cases = [
        make_provider(transport=httpx.MockTransport(_timeout)),
        make_provider(transport=httpx.MockTransport(_refused)),
        make_provider(transport=openai_transport(content="{}", status_code=401)),
        make_provider(transport=openai_transport(content="garbage")),
        make_provider(transport=openai_transport(content='{"items": [{"kind": "no"}]}')),
    ]
    for provider in cases:
        for call in (
            lambda p=provider: p.complete_text(MESSAGES),
            lambda p=provider: p.complete_json(MESSAGES, SCHEMA),
        ):
            try:
                asyncio.run(call())
            except Exception as exc:  # noqa: BLE001 - the point is the message
                assert CANARY_KEY not in str(exc)
                assert CANARY_KEY not in repr(exc)


def test_a_successful_result_does_not_carry_the_key() -> None:
    import asyncio

    provider = make_provider()
    result = asyncio.run(provider.complete_json(MESSAGES, SCHEMA))
    assert CANARY_KEY not in json.dumps(result.payload)
    assert CANARY_KEY not in repr(result)


# --- the validator itself ---------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({}, "missing required property 'items'"),
        ({"items": "nope"}, "expected array"),
        ({"items": []}, "minimum is 1"),
        ({"items": [{"kind": "a", "extra": 1}]}, "unexpected property"),
        ({"items": [{"kind": "a", "score": 2}]}, "above the maximum"),
        ({"items": [{"score": 0.5}]}, "missing required property 'kind'"),
    ],
)
def test_validator_reports_the_first_violation(payload: dict, fragment: str) -> None:
    with pytest.raises(LLMSchemaError, match=fragment):
        validate_json_schema(payload, SCHEMA)


def test_validator_accepts_a_conforming_payload() -> None:
    validate_json_schema({"items": [{"kind": "a"}, {"kind": "b", "score": 1}]}, SCHEMA)


def test_validator_does_not_treat_a_boolean_as_a_number() -> None:
    schema = {"type": "object", "properties": {"n": {"type": "number"}}}
    with pytest.raises(LLMSchemaError, match="expected number, got boolean"):
        validate_json_schema({"n": True}, schema)


def test_validator_rejects_a_missing_optional_property_only_when_required() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    validate_json_schema({}, schema)


# --- settings ---------------------------------------------------------------


def test_defaults_keep_the_offline_demo_untouched() -> None:
    settings = load_settings({})
    assert settings.llm_mode == MODE_DETERMINISTIC
    assert settings.llm_timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS


def test_settings_read_the_v3_environment_variables(tmp_path) -> None:
    settings = load_settings(
        {
            "EVALPILOT_DB_PATH": str(tmp_path / "v3.db"),
            "EVALPILOT_LLM_MODE": "live",
            "EVALPILOT_LLM_TIMEOUT_SECONDS": "12.5",
        }
    )
    assert settings.llm_mode == "live"
    assert settings.llm_timeout_seconds == 12.5


def test_an_unusable_timeout_falls_back_to_the_default() -> None:
    assert load_settings({"EVALPILOT_LLM_TIMEOUT_SECONDS": "abc"}).llm_timeout_seconds == (
        DEFAULT_LLM_TIMEOUT_SECONDS
    )
    assert load_settings({"EVALPILOT_LLM_TIMEOUT_SECONDS": "-5"}).llm_timeout_seconds == (
        DEFAULT_LLM_TIMEOUT_SECONDS
    )


def test_positional_construction_with_the_old_arity_still_works(tmp_path) -> None:
    """The eight original fields are still constructible positionally."""
    settings = Settings(
        tmp_path / "a.db",
        tmp_path / "artifacts",
        None,
        None,
        None,
        False,
        True,
        0.0,
        "0.1.0",
    )
    assert settings.llm_mode == MODE_DETERMINISTIC
    assert settings.llm_timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS


def test_positional_construction_accepting_the_new_fields() -> None:
    settings = Settings(
        "db.sqlite",
        "artifacts",
        "https://api.deepseek.com",
        "key",
        "m",
        False,
        True,
        0.0,
        "0.1.0",
        "live",
        9.0,
    )
    assert settings.llm_mode == "live"
    assert settings.llm_timeout_seconds == 9.0


# --- runtime resolution -----------------------------------------------------


def test_deterministic_mode_installs_no_provider() -> None:
    runtime = build_runtime(load_settings({}))
    assert runtime.mode == MODE_DETERMINISTIC
    assert runtime.provider is None
    assert runtime.live is False
    assert runtime.configured is False
    assert runtime.fallback_active is False


def test_live_mode_with_full_configuration_installs_a_provider() -> None:
    runtime = build_runtime(
        load_settings(
            {
                "EVALPILOT_LLM_MODE": "live",
                "EVALPILOT_LLM_BASE_URL": "https://api.deepseek.com",
                "EVALPILOT_LLM_API_KEY": CANARY_KEY,
                "EVALPILOT_LLM_MODEL": "deepseek-v4-pro",
            }
        )
    )
    assert runtime.live is True
    assert runtime.configured is True
    assert runtime.model == "deepseek-v4-pro"
    assert runtime.base_url_host == "api.deepseek.com"
    assert runtime.fallback_active is False


def test_live_mode_without_a_key_falls_back_and_says_why() -> None:
    runtime = build_runtime(
        load_settings(
            {
                "EVALPILOT_LLM_MODE": "live",
                "EVALPILOT_LLM_BASE_URL": "https://api.deepseek.com",
                "EVALPILOT_LLM_MODEL": "deepseek-v4-pro",
            }
        )
    )
    assert runtime.mode == "live"
    assert runtime.provider is None
    assert runtime.live is False
    assert runtime.configured is False
    assert "EVALPILOT_LLM_API_KEY" in (runtime.configuration_error or "")


def test_an_unknown_mode_runs_deterministically_and_reports_it() -> None:
    runtime = build_runtime(
        load_settings(
            {
                "EVALPILOT_LLM_MODE": "sometimes",
                "EVALPILOT_LLM_BASE_URL": "https://api.deepseek.com",
                "EVALPILOT_LLM_API_KEY": CANARY_KEY,
                "EVALPILOT_LLM_MODEL": "m",
            }
        )
    )
    assert runtime.mode == MODE_DETERMINISTIC
    assert runtime.provider is None
    assert "unknown EVALPILOT_LLM_MODE" in (runtime.configuration_error or "")


def test_runtime_status_carries_no_secret() -> None:
    runtime = build_runtime(
        load_settings(
            {
                "EVALPILOT_LLM_MODE": "live",
                "EVALPILOT_LLM_BASE_URL": "https://api.deepseek.com",
                "EVALPILOT_LLM_API_KEY": CANARY_KEY,
                "EVALPILOT_LLM_MODEL": "deepseek-v4-pro",
            }
        )
    )
    serialized = json.dumps(runtime.status(tools=["kb_search"]))
    assert CANARY_KEY not in serialized
    assert "api.deepseek.com" in serialized
    assert "https://" not in serialized


def test_fallback_reasons_are_recorded_deduplicated_and_bounded() -> None:
    runtime = build_runtime(load_settings({}))
    runtime.record_fallback("timeout")
    runtime.record_fallback("timeout")
    assert runtime.fallback_reasons == ["timeout"]
    assert runtime.fallback_active is True
    for index in range(20):
        runtime.record_fallback(f"reason-{index}")
    assert len(runtime.fallback_reasons) <= 8
    assert runtime.fallback_reasons[-1] == "reason-19"
