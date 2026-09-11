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
| Cases | 26 golden scenarios × 2 versions = 52 test cases |

Every scenario runs once per version, so the two versions face an identical test
set. That matched-pair design is what lets the report attribute a drop to the
version change instead of to a harder test set.

The candidate version is deliberately built with three defects, matching what a
real knowledge-base edit might ship:

| Scenario | Category | Defect | Severity |
| --- | --- | --- | --- |
| `prompt-injection-password` | adversarial | discloses credentials on a prompt-injection attempt | critical |
| `escalation-path` | boundary | drops the "human agent" escalation instruction | critical |
| `urgent-safety` | adversarial | drops the emergency-hotline instruction | critical |

The remaining 23 scenarios act as controls and are unchanged in both versions.

### Reading the demo verdict

Three localized regressions out of 26 matched cases is **not** enough for the
paired bootstrap to resolve, and the demo reports that honestly:

```text
The aggregate comparison is inconclusive: the mean score changed by -0.077
(95% CI -0.173 to 0.000), which does not clear the ±0.050 threshold at 72%
confidence. 3 scenario(s) regressed against their own baseline: ...
```

Two separate things are being reported, and the report keeps them apart:

| Metric | Meaning | Demo value |
| --- | --- | --- |
| `regression_detected` | at least one scenario scored below its own baseline | `true` |
| `regression_confirmed` | the mean difference cleared the threshold interval | `false` |
| `direction` | the engine's aggregate verdict | `inconclusive` |

`regression_detected` is the per-case fact: those three scenarios really did
lose the content they are supposed to carry, and each has an evidence-linked
finding. `regression_confirmed` is the aggregate question, and the demo's answer
is that this much data cannot settle it. Raising the case count or widening the
defects would change that — the report moves with the data rather than pinning a
verdict the numbers do not support.

To create the demo records through the API instead:

```bash
curl -X POST http://127.0.0.1:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"Enterprise Knowledge Base QA","scenario":"kb-qa"}'

curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"project_id":"<id>","baseline_version":"v1.0-baseline",
       "candidate_version":"v1.1-candidate","case_count":26,"seed":20260919}'

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
  engine_mapping.py  backend rows -> evaluation engine models
  runner.py       async run state machine
  demo.py         demo metadata + idempotent seeding
  routes/         one module per API area
  orchestration_eval/  evaluation boundary the runner calls
  evaluation/     the evaluation engine (checks, comparison, judge)
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

The runner calls exactly one method, which lives in
`backend/evalpilot/orchestration_eval/`:

```python
await EvaluationService(...).evaluate_run_async(
    run_id=..., cases=..., evidence_by_case=...
) -> EvaluationOutcome(cases, findings, metrics, summary)
```

That boundary is a seam, not an evaluator. All scoring and statistics come from
the engine in `backend/evalpilot/evaluation/`, and `engine_mapping.py` adapts
backend rows into the engine's models. Two mapping decisions are worth knowing:

1. **The matched case is `input.scenario_id`, not the `TestCase.id`.** A test
   case row is unique per version, so keying the engine on it produces two
   disjoint case sets and a comparison with no matched pairs at all.
2. **The engine observation id is the persisted evidence id.** The engine
   attaches its observation id to every check outcome and builds findings from
   it, and `Finding.evidence_ids` must reference rows that exist in the run's
   evidence table.

The engine (`backend/evalpilot/evaluation/`) provides:

- `checks.py` — deterministic, offline answer checks (format, refusal, citation,
  tool trace, required facts)
- `comparison.py` — matched-case paired effect size, seeded bootstrap confidence
  interval, and an explicit regression decision
- `judge.py` — an injected async LLM judge with strict JSON validation
- `service.py` — the async comparison path the runner awaits
- `findings.py` — severity banding and evidence-linked finding builders

See [`EVALUATION.md`](EVALUATION.md) for the statistical design and its rationale.

A rubric LLM judge is supported by the engine but **not wired into the run
pipeline**: the fixture executor does not record the question text a judge needs,
and the offline demo must not make network calls. `EvaluationService` takes an
optional `judge=` so a judge can be injected at the seam; when one is present the
run reports it in `metrics.evaluation_warnings` instead of silently blending a
non-reproducible score into the verdict.

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
   case per version, so `case_count=26` yields 52 `TestCase` rows. `GET
   /runs/{run_id}` returns all rows; the UI should group by `input.scenario_id`
   (or `title`) to display 26 matched pairs.

   The fixture set holds 26 scenarios, so `case_count` above that is clamped.
   That clamp is what bounds how small a change the demo can resolve: the
   comparison's standard error falls with the number of matched cases, so a
   deeper set would be needed to confirm a smaller regression.
5. **`Report.findings` is embedded, not a separate collection.** `GET
   /runs/{run_id}/report` returns findings inline per the contract. There is no
   `GET /findings` endpoint; a UI showing findings before completion must read
   them from the event stream (`finding.created`) instead.
