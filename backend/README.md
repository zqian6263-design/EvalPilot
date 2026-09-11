# EvalPilot Backend

FastAPI service that plans, executes, evaluates, and reports on regression runs.
The MVP is **fully deterministic and offline**: no LLM, no API key, and no
network access are required to complete a run.

- Contract (source of truth): [`../docs/INTERFACES.md`](../docs/INTERFACES.md)
- Product contract: [`../docs/SPEC.md`](../docs/SPEC.md)
- Collaboration rules: [`../CLAUDE.md`](../CLAUDE.md)

## Requirements

- Python 3.11+
- No external services

## Setup

From the repository root, PowerShell:

```powershell
./scripts/start-backend.ps1        # creates .venv, installs deps, serves on :8000
```

Or manually:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt   # Windows
# source .venv/bin/activate && pip install -r backend/requirements.txt  # macOS/Linux
```

Optional editable install (adds the `evalpilot` console entry point):

```bash
cd backend && pip install -e ".[dev]"
```

## Run

```bash
cd backend
python -m evalpilot.cli serve                  # API on 127.0.0.1:8000, docs at /docs
python -m evalpilot.cli seed                   # create the demo project + queued run
python -m evalpilot.cli run                    # seed, execute, print the regression verdict
```

`python -m evalpilot.cli run` exits non-zero if a scripted regression goes
undetected, so it doubles as an end-to-end acceptance check.

## Test

```powershell
./scripts/test-backend.ps1                     # full suite
./scripts/test-backend.ps1 -v tests/test_demo_seed.py
```

```bash
cd backend && python -m pytest
```

Tests use a temporary SQLite database and never touch `backend/data/`.

For a real-socket smoke test (binds `127.0.0.1:8129`, starts uvicorn, drives a
complete run, and streams events):

```bash
cd backend && python scripts/startup_check.py
```

## The seeded demo

`GET /api/demo/seed` is **read-only metadata** — it never writes and never
starts a run. It describes the deterministic demo:

| Field | Value |
| --- | --- |
| Scenario | enterprise knowledge-base QA assistant |
| Versions | `v1.0-baseline` → `v1.1-candidate` |
| Seed | `20260919` |
| Cases | 10 golden scenarios × 2 versions = 20 test cases |

Every scenario runs once per version, so the two versions face an identical test
set. That matched-pair design is what lets the report attribute a drop to the
version change instead of to a harder test set.

The candidate version is deliberately built with two defects, matching what a
real knowledge-base edit might ship:

| Scenario | Category | Defect | Severity |
| --- | --- | --- | --- |
| `prompt-injection-password` | adversarial | discloses credentials on a prompt-injection attempt | critical |
| `escalation-path` | boundary | drops the "human agent" escalation instruction | high |
| `urgent-safety` | adversarial | drops the emergency-hotline instruction | high |

The remaining 7 scenarios act as controls and are unchanged in both versions.

To create the demo records through the API instead:

```bash
curl -X POST http://127.0.0.1:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"Enterprise Knowledge Base QA","scenario":"kb-qa"}'

curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"project_id":"<id>","baseline_version":"v1.0-baseline",
       "candidate_version":"v1.1-candidate","case_count":10,"seed":20260919}'

curl -X POST http://127.0.0.1:8000/api/runs/<run_id>/start
curl http://127.0.0.1:8000/api/runs/<run_id>/report
```

## Endpoints

Base path `/api`. Full request/response shapes live in `docs/INTERFACES.md`.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/health` | `{status, version}` |
| `GET` `POST` | `/projects` | list / create |
| `GET` | `/projects/{project_id}` | |
| `GET` `POST` | `/runs` | create accepts `case_count?`, `seed?` |
| `GET` | `/runs/{run_id}` | run + test cases + evidence + counts |
| `POST` | `/runs/{run_id}/start` | **202**; only valid from `queued`, else **409** |
| `POST` | `/runs/{run_id}/cancel` | valid for any non-terminal run |
| `GET` | `/runs/{run_id}/report` | **409** until the run completes |
| `GET` | `/events?run_id=&after=&fmt=&follow=` | progress stream; omit `run_id` for the newest run |
| `GET` | `/runs/{run_id}/events` | same stream on the frozen contract path |
| `GET` | `/demo/seed` | deterministic demo metadata, no side effects |

`fmt=sse` (default) emits `text/event-stream`; `fmt=ndjson` emits
newline-delimited JSON. `follow=true` keeps the stream open until the run
reaches a terminal status. `after=<sequence>` resumes from a known cursor.

The event stream is published on **both** `/events` and
`/runs/{run_id}/events`. See "Contract concerns" below.

## Architecture

```text
evalpilot/
  app.py          FastAPI factory + router wiring
  container.py    resolved collaborators (settings, db, repo, runner)
  config.py       environment settings
  models.py       Pydantic v2 domain models (frozen contract)
  db.py           SQLite schema, connection factory, artifact paths
  repository.py   all SQL reads and writes
  clock.py        UTC ISO-8601 timestamps, UUIDs
  fixtures.py     static knowledge base + golden scenarios
  planner.py      deterministic mock planner
  executor.py     deterministic mock assistant (the system under test)
  evaluator.py    evidence persistence helpers
  runner.py       async run state machine
  demo.py         demo metadata + idempotent seeding
  routes/         one module per API area
  evaluation/     evaluation service boundary
tests/            pytest suite
scripts/          manual startup check
```

**Run state machine:** `queued → planning → executing → evaluating → completed`,
with `failed` and `cancelled` as alternatives. Every transition is persisted as a
sequenced event. Cancellation is checked between cases and after each execution,
so a cancelled run stops promptly and its event log never grows afterwards.

**Storage:** SQLite via the standard library (`backend/data/evalpilot.db` by
default). File-backed evidence is written to
`backend/data/artifacts/{run_id}/`. Both paths are gitignored.

**Evidence:** every executed case produces four kinds — `citation` (retrieved
documents with quotes), `trace` (the tool call, its scores, and the evaluator's
rationale, written to a JSON artifact on disk), `text` (question and answer), and
`metric` (latency, citation count, refusal flag). Findings reference these rows by
ID, so every claim is traceable to the exact input, output, and tool trace.

## Evaluation boundary

`backend/evalpilot/evaluation/` is the extension point for evaluation work. The
runner calls exactly one method:

```python
EvaluationService.evaluate_run(
    run_id=..., cases=..., evidence_by_case=...
) -> EvaluationOutcome(cases, comparisons, findings, metrics, summary)
```

What is implemented today is deterministic and deliberately narrow:

- `checks.py` — citation grounding, required/forbidden content, refusal behaviour
- `compare.py` — matched-case baseline/candidate comparison and metrics
- `findings.py` — regression findings with severity, confidence, evidence links

What is **not** implemented, and where to add it:

| Capability | Where |
| --- | --- |
| Rubric-based LLM judging | `service.JudgeHook.score` |
| Repeated sampling / variance | `EvaluationOutcome`, `compare.summarize_metrics` |
| Statistical significance testing | `compare.compare_matched_cases` |

`JudgeHook` is inert unless `EVALPILOT_LLM_BASE_URL` and `EVALPILOT_LLM_MODEL`
are set, so the demo never depends on a provider.

## Tool safety

Only `kb_search` is available, and it is a pure in-process function. `http_get`
and `file_read` exist as explicit stubs that raise — they are not registered and
are not listed in `ToolRegistry.available()`. `python_run` refuses unless
`EVALPILOT_ENABLE_PYTHON_TOOL=true`, and even then has no implementation. No code
path in the MVP executes arbitrary input (`CLAUDE.md` non-negotiable #4).

## Environment variables

See [`.env.example`](.env.example). Names are frozen by `docs/INTERFACES.md`;
defaults run the demo with no configuration.

| Variable | Default | Purpose |
| --- | --- | --- |
| `EVALPILOT_DB_PATH` | `backend/data/evalpilot.db` | SQLite file |
| `EVALPILOT_LLM_BASE_URL` | *(empty)* | optional judge endpoint |
| `EVALPILOT_LLM_API_KEY` | *(empty)* | never committed |
| `EVALPILOT_LLM_MODEL` | *(empty)* | optional judge model |
| `EVALPILOT_ENABLE_PYTHON_TOOL` | `false` | allowlist gate |
| `EVALPILOT_DEMO_MODE` | `true` | deterministic fixtures |
| `EVALPILOT_STEP_DELAY` | `0.05` | simulated per-step latency; `0` is fastest |

## Contract concerns

Raised for the contract owner; none of these required a code change to a frozen
field, and no frozen field was renamed.

1. **No `run.cancelled` event type.** The event vocabulary in `docs/INTERFACES.md`
   is `run.started | task.created | task.started | evidence.created |
   task.completed | finding.created | run.completed | run.failed`. Cancellation is
   emitted as `run.failed` with `data.cancelled = true` and a message saying so,
   rather than inventing an event type outside the frozen list.
2. **`/runs/{run_id}/events` has no run-discovery path.** As frozen, a client
   must already know a run ID, so it cannot discover a run created after the page
   loaded. `/events` is added as an alias that defaults to the newest active run.
   The frozen path is unchanged and still works. A `run.created` event type would
   close this gap properly.
3. **`TestCase.status` has no `skipped` state**, so cancellation cannot mark
   not-yet-executed cases distinctly from `pending`. Cancelled runs therefore
   leave those cases at `pending`.
4. **`case_count` counts scenarios, not rows.** Each scenario produces one test
   case per version, so `case_count=10` yields 20 `TestCase` rows. `GET
   /runs/{run_id}` returns all rows; the UI should group by `input.scenario_id`
   (or `title`) to display 10 matched pairs.
5. **`Report.findings` is embedded, not a separate collection.** `GET
   /runs/{run_id}/report` returns findings inline per the contract. There is no
   `GET /findings` endpoint; a UI showing findings before completion must read
   them from the event stream (`finding.created`) instead.
