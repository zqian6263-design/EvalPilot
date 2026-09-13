# EvalPilot V3 Live-LLM Interfaces

This contract adds a real, optional LLM runtime without weakening the deterministic demo.

## Modes

```text
deterministic
  default, offline, reproducible, no API key

live
  OpenAI-compatible chat-completions endpoint, preferably DeepSeek V4 Pro
  used for investigation planning, judge rationale, and report narrative
  any LLM failure falls back to deterministic behavior with an explicit warning
```

The release decision remains evidence- and counterfactual-driven. The LLM may propose hypotheses, choose a bounded replay experiment, and explain results. Its experiment choice affects control flow but is executed and measured by the engine; the model may not override the measured verdict or invent evidence.

## Environment

- `EVALPILOT_LLM_BASE_URL`: OpenAI-compatible base URL, for example `https://api.deepseek.com`
- `EVALPILOT_LLM_API_KEY`: secret; never committed or returned by the API
- `EVALPILOT_LLM_MODEL`: model id configured by the user, for example `deepseek-v4-pro`
- `EVALPILOT_LLM_MODE`: `deterministic` or `live`; default `deterministic`
- `EVALPILOT_LLM_TIMEOUT_SECONDS`: default 45

## Provider seam

```text
LLMProvider
  name: str
  model: str
  async complete_json(messages, schema, timeout_seconds) -> dict
  async complete_text(messages, timeout_seconds) -> str
```

Implementations must:

- use an OpenAI-compatible `/chat/completions` endpoint;
- validate JSON responses against the supplied schema;
- return typed errors, never leak API keys;
- be injectable for tests; no network in unit tests.

## Runtime status

`GET /api/runtime` returns:

```json
{
  "mode": "deterministic | live",
  "llm_configured": true,
  "model": "deepseek-v4-pro",
  "base_url_host": "api.deepseek.com",
  "fallback_active": false,
  "tools": ["kb_search", "http_get", "file_read"]
}
```

The API must not return the API key or full credentials.

## Investigation behavior

When live mode is active:

1. The LLM proposes risk hypotheses from the objective and observed failures.
2. The LLM may choose one executable intervention per regressed scenario. The choice is validated against a closed vocabulary, executed by the counterfactual engine, and measured before it can affect a verdict.
3. The LLM may produce a structured release rationale grounded in evidence ids.
3. The LLM may score rubric-based qualitative dimensions; provider usage is persisted under `metrics.judge.usage`.
4. Counterfactual results and blocking findings remain measured facts.

Each LLM-generated step carries:

```text
data.source = "llm"
data.model = "<model id>"
data.llm_call_id = "<trace id>"
```

Deterministic steps carry `data.source = "deterministic"`.

If an LLM request fails, the investigation still completes using deterministic logic and records `data.fallback_reason`.

## Frontend

- Runtime badge shows `LIVE LLM · <model>` or `DETERMINISTIC`.
- Investigation status distinguishes model-generated and deterministic steps.
- Report shows model rationale but keeps measured metrics separate.
- No private chain-of-thought is displayed; only structured hypotheses, rationales, and actions.

## Acceptance

- Tests run with no key and no network.
- A fake provider proves live-mode planning and rationale integration.
- Missing/invalid key falls back without failing the investigation.
- Existing 26-case regression and counterfactual results remain unchanged when no replay plan is supplied.
- A valid model replay plan changes the executed intervention; an invalid or unexecutable plan is rejected and recorded.
- Runtime status confirms the configured mode and never exposes secrets.
