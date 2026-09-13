# External HTTP SUT

EvalPilot's default demo uses a deterministic mock so a fresh clone can run
offline. That is useful for reproducibility, but it is not enough to prove the
evaluator works against a system built by another team. The external-SUT path
closes that gap.

## Boundary

When `EVALPILOT_SUT_URL` is set, every planned test case is sent to:

```text
POST {EVALPILOT_SUT_URL}/v1/answer
```

Request:

```json
{
  "run_id": "run uuid",
  "test_case_id": "case uuid",
  "scenario_id": "refund-window",
  "question": "How many days do I have to return a product for a refund?",
  "version": "v1.0-baseline",
  "intervention": null
}
```

Response:

```json
{
  "answer": "Products may be returned within 30 days of delivery.",
  "citations": ["kb-refund-policy"],
  "tool_calls": ["kb.search:kb-refund-policy"],
  "latency_ms": 123,
  "model": "support-assistant@v1.0-baseline",
  "refused": false
}
```

The adapter persists the request/response trace and turns the response into the
same `ExecutionResult` shape used by the deterministic executor. Invalid JSON or
a missing/wrong-typed field fails the run; it is never silently replaced by mock
output.

## Capability discovery

Before an online evaluation starts, EvalPilot calls:

```text
GET {EVALPILOT_SUT_URL}/capabilities
```

Example response:

```json
{
  "contract_version": "1.0",
  "versions": ["v1.0-baseline", "v1.1-candidate"],
  "interventions": ["compression_disabled", "security_guard_enabled"],
  "features": ["citations", "tool_calls", "refusal", "offline_cache"]
}
```

EvalPilot rejects an unadvertised version or intervention before sending an
answer request. A 404 is treated as a legacy service and falls back to the
original answer-only contract; this preserves compatibility while making
capability declarations the preferred path. Capability discovery is skipped in
offline mode, where the content-addressed replay cache is authoritative.

## Configuration

```text
EVALPILOT_SUT_URL
EVALPILOT_SUT_TIMEOUT_SECONDS
EVALPILOT_SUT_OFFLINE
EVALPILOT_SUT_CACHE_DIR
```

The cache key covers the SUT base URL, scenario, question, revision label and
intervention. It deliberately excludes run and case ids, so a later run can
replay the same workload offline without pretending those execution ids were SUT
inputs.

`EVALPILOT_SUT_OFFLINE=true` never opens a socket. A cache hit replays the exact
recorded response; a cache miss fails the run loudly.

## Public open-source SUT adapter

The acceptance path uses `backend/evalpilot/sut/haystack_server.py`, a separate
FastAPI process backed by the public Apache-2.0 project
[`deepset-ai/haystack`](https://github.com/deepset-ai/haystack). The retriever is
Haystack's real in-memory BM25 implementation, pinned by
`backend/requirements.txt`; EvalPilot's normal deterministic path never imports
it. The adapter models two deployable revisions around that public retriever:

- `v1.0-baseline` returns complete retrieved answers.
- `v1.1-candidate` applies a compression pass and can disclose a demo secret on
  a prompt-injection attempt unless `security_guard_enabled` is supplied.

Start it independently:

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe -m uvicorn `
  evalpilot.sut.haystack_server:app --host 127.0.0.1 --port 8010
```

Then start EvalPilot with:

```powershell
$env:EVALPILOT_SUT_URL = 'http://127.0.0.1:8010'
python scripts/deploy.py
```

## Reproducible acceptance

```powershell
.\scripts\sut-e2e-check.ps1
```

The check starts the Haystack-backed SUT and three isolated backend
configurations. It verifies:

1. `v1.1-candidate` versus `v1.1-candidate` reports zero mean delta and no
   regressed scenario.
2. `v1.0-baseline` versus `v1.1-candidate` reports eight regressed scenarios,
   mean delta `-0.173`, and a confirmed 95% regression interval.
3. Investigation replay performs eight counterfactual calls through the same
   HTTP boundary and records trace evidence for each.
4. With the SUT stopped, the cached workload completes offline with the same
   result.
5. With the SUT stopped and an empty cache, the run fails; there is no silent
   fallback to the mock.

A machine-readable `summary.json` and both server logs are written under
`.runtime/sut-e2e-*`.
