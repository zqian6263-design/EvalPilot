# Frozen Interfaces

This document defines the shared contract for parallel implementation. Change it before changing code that depends on it.

## Domain models

```text
Project
  id: uuid
  name: str
  scenario: str
  created_at: datetime

Run
  id: uuid
  project_id: uuid
  baseline_version: str
  candidate_version: str
  status: queued | planning | executing | evaluating | completed | failed | cancelled
  case_count: int | null
  created_at: datetime
  completed_at: datetime | null

TestCase
  id: uuid
  run_id: uuid
  title: str
  category: normal | boundary | adversarial | regression
  input: object
  expected: object
  difficulty: float (0..1)
  status: pending | running | passed | failed | error
  version: baseline | candidate
  output: object | null

Evidence
  id: uuid
  run_id: uuid
  test_case_id: uuid
  kind: text | screenshot | log | citation | trace | metric
  uri: str | null
  payload: object
  created_at: datetime

Finding
  id: uuid
  run_id: uuid
  test_case_id: uuid | null
  severity: info | low | medium | high | critical
  title: str
  description: str
  confidence: float (0..1)
  evidence_ids: list[uuid]
  recommendation: str | null

Report
  id: uuid
  run_id: uuid
  summary: str
  metrics: object
  findings: list[Finding]
  generated_at: datetime
```

## HTTP API

Base path: `/api`

- `GET /health` -> `{ status: "ok", version: string }`
- `GET /projects` -> `list[Project]`
- `POST /projects` -> create `Project`
- `GET /projects/{project_id}` -> `Project`
- `GET /runs` -> `list[Run]`
- `POST /runs` -> create a run
  - body: `{ project_id, baseline_version, candidate_version, case_count?, seed? }`
- `GET /runs/{run_id}` -> `Run` with test cases and evidence summaries
- `POST /runs/{run_id}/start` -> start an asynchronous run
- `POST /runs/{run_id}/cancel` -> cancel a run
- `GET /runs/{run_id}/report` -> `Report`
- `GET /runs/{run_id}/gate` -> `ReleaseGate` (exit codes: 0 allow, 1 review, 2 block)
- `GET /runs/{run_id}/junit` -> JUnit XML for CI test reporters
- `GET /runs/{run_id}/sarif` -> SARIF 2.1.0 for code scanning
- `GET /runs/{run_id}/events` -> server-sent events or newline-delimited progress events for MVP
- `GET /demo/seed` -> deterministic demo metadata only; no side effects

## Event payload

```json
{
  "run_id": "uuid",
  "sequence": 1,
  "type": "run.started | task.created | task.started | evidence.created | task.completed | finding.created | run.completed | run.failed",
  "message": "human-readable summary",
  "data": {},
  "created_at": "ISO-8601"
}
```

## Storage

MVP uses SQLite. File-backed evidence is stored under `backend/data/artifacts/{run_id}/`. Do not store secrets or complete credentials in evidence payloads.

## Environment

- `EVALPILOT_DB_PATH`: SQLite path; default `backend/data/evalpilot.db`
- `EVALPILOT_LLM_BASE_URL`: OpenAI-compatible endpoint
- `EVALPILOT_LLM_API_KEY`: API key, never committed
- `EVALPILOT_LLM_MODEL`: default model name
- `EVALPILOT_ENABLE_PYTHON_TOOL`: `false` by default
- `EVALPILOT_DEMO_MODE`: `true` enables deterministic fixtures
- `EVALPILOT_SUT_URL`: optional external system-under-test base URL; when set, runs use the HTTP contract in `docs/EXTERNAL_SUT.md`
- `EVALPILOT_SUT_TIMEOUT_SECONDS`: per-request timeout; default `20`
- `EVALPILOT_SUT_OFFLINE`: `true` replays only from cache and never opens a socket
- `EVALPILOT_SUT_CACHE_DIR`: content-addressed response cache for offline replay
- `EVALPILOT_SUT_DISCOVERY`: `true` validates advertised SUT versions and interventions before execution; default `true`
- `EVALPILOT_JUDGE_MAX_CALLS`: optional maximum Judge calls per run
- `EVALPILOT_JUDGE_MAX_TOKENS`: optional maximum persisted Judge tokens per run
