# EvalPilot Backend

FastAPI service that plans, executes, evaluates, and reports on regression runs,
and then investigates a completed run autonomously. The MVP is **fully
deterministic and offline**: no LLM, no API key, and no network access are
required to complete a run or an investigation.

- Contract (source of truth): [`../docs/INTERFACES.md`](../docs/INTERFACES.md)
- Investigation contract: [`../docs/V2_INTERFACES.md`](../docs/V2_INTERFACES.md)
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

For a real-socket check of the autonomous investigation (binds `127.0.0.1:8130`,
runs the demo, then drives an investigation end to end and asserts every promise
in `docs/V2_INTERFACES.md`):

```bash
cd backend && python scripts/investigation_check.py
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

The candidate models a realistic v1.1 regression: a faster summarization/compression
step preserves ordinary answers but removes mandatory escalation, safety, and
security clauses. It is deliberately built with eight customer-visible failures:

| Scenario | Category | Defect | Severity |
| --- | --- | --- | --- |
| `prompt-injection-password` | adversarial | discloses credentials on a prompt-injection attempt | critical |
| `escalation-path` | boundary | drops the "human agent" escalation instruction | critical |
| `escalation-timeframe` | boundary | drops the 24-hour escalation timeframe | critical |
| `escalation-channel` | boundary | drops the in-app Help Center path | critical |
| `urgent-safety` | adversarial | drops the emergency-hotline instruction | critical |
| `battery-handling` | adversarial | drops the immediate unplug instruction | critical |
| `safety-reporting` | adversarial | drops the emergency-hotline reporting step | critical |
| `security-password-request` | adversarial | omits the rule that support never asks for full passwords | critical |

The remaining 18 scenarios are unchanged controls. The candidate is also about
75 ms faster per response, which makes the tradeoff visible: lower latency came
at the cost of omitting high-risk clauses.

### Reading the demo verdict

The expanded fixture produces a confirmed aggregate regression. On a clean run
the report is:

```text
Compared 26 matched scenario(s) between v1.0-baseline and v1.1-candidate.
The candidate regressed: the mean score fell 0.173
(95% CI -0.288 to -0.077), entirely below the -0.050 threshold.
8 scenario(s) regressed against their own baseline.
18 control scenario(s) scored identically on both versions.
Findings: 8 critical.
```

The important distinction is still explicit:

| Metric | Meaning | Demo value |
| --- | --- | --- |
| `regression_detected` | at least one scenario scored below its own baseline | `true` |
| `regression_confirmed` | the paired interval cleared the regression threshold | `true` |
| `direction` | the engine's aggregate verdict | `regression` |
| `ci_lower` / `ci_upper` | paired bootstrap confidence interval | `-0.288` / `-0.077` |
| `confidence` | confidence that the effect clears the threshold | `0.987` |

`baseline_pass_rate` and `candidate_pass_rate` are strict case pass rates: the
fraction of scenarios for which every check passed. `baseline_score` and
`candidate_score` are the mean check-coverage scores used by the paired
comparison. On the demo, the baseline passes 26/26 cases and the candidate
passes 18/26, while the weighted score falls from `1.000` to `0.827`.

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
| `GET` | `/demo/investigation` | investigation workspace metadata, no side effects |
| `POST` | `/investigations` | create a queued investigation; **201**, idempotent on `run_id` |
| `GET` | `/investigations/{id}` | investigation + steps + memory matches + counterfactuals + decision |
| `POST` | `/investigations/{id}/start` | **202**; only valid from `queued`, else **409** |
| `GET` | `/investigations/{id}/events` | progress stream; same envelope as a run's |
| `GET` | `/investigations/{id}/report.md` | Markdown report; **409** until it completes |
| `GET` | `/memory/incidents?query=&tag=` | seeded incident history, scored when `query` is given |

`fmt=sse` (default) emits `text/event-stream`; `fmt=ndjson` emits
newline-delimited JSON. `follow=true` keeps the stream open until the run
reaches a terminal status. `after=<sequence>` resumes from a known cursor.

The event stream is published on **both** `/events` and
`/runs/{run_id}/events`. See "Contract concerns" below.

## Architecture

```text
evalpilot/
  app.py          FastAPI factory + router wiring
  container.py    resolved collaborators (settings, db, repo, runner, investigation)
  config.py       environment settings
  models.py       Pydantic v2 domain models (frozen contracts, V1 + V2)
  db.py           SQLite schema, migrations, connection factory, artifact paths
  repository.py   all SQL reads and writes
  clock.py        UTC ISO-8601 timestamps, UUIDs
  fixtures.py     static knowledge base + golden scenarios
  planner.py      deterministic mock planner
  executor.py     deterministic mock assistant (the system under test)
  evaluator.py    evidence persistence helpers
  engine_mapping.py  backend rows -> evaluation engine models
  runner.py       async run state machine
  demo.py         demo metadata + idempotent seeding (+ investigation metadata)
  memory/         seeded incident history and the memory matcher
  investigation/  autonomous investigation engine + counterfactual seam
  routes/         one module per API area
  orchestration_eval/  evaluation boundary the runner calls
  evaluation/     the evaluation engine (checks, comparison, judge)
tests/            pytest suite
scripts/          manual startup checks (run + investigation)
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

## Autonomous investigation

Once a run completes, `docs/V2_INTERFACES.md` turns it into a release
investigation. The engine drives exactly the sequence the contract names:

```text
release objective
-> risk hypotheses -> recalled incidents -> follow-up probes
-> counterfactual replay -> root cause -> release decision
-> exportable evidence report
```

The demo entry point is the confirmed 26-case regression run:

```bash
curl -X POST http://127.0.0.1:8000/api/investigations \
  -H "Content-Type: application/json" \
  -d '{"run_id":"<completed_run_id>","objective":"Can v1.1-candidate ship?"}'

curl -X POST http://127.0.0.1:8000/api/investigations/<id>/start   # 202
curl http://127.0.0.1:8000/api/investigations/<id>
curl http://127.0.0.1:8000/api/investigations/<id>/report.md
```

On the seeded run the investigation produces:

| Contract requirement | Result |
| --- | --- |
| ≥ 3 risk hypotheses | 5: the summarization mechanism, one per affected domain (safety, security, escalation), and the credential disclosure |
| ≥ 2 memory matches | 2: the summarizer precedent (0.80) and the refusal-bypass precedent (1.00) |
| a probe per regressed scenario | 8, one per regressed scenario, each citing that scenario's candidate evidence |
| one counterfactual per critical finding | 8, one per regressed scenario |
| `compression_disabled` dominant for dropped clauses | 7 root causes, all seven clause-loss scenarios |
| `security_guard_enabled` for the credential disclosure | 1 root cause on `prompt-injection-password` |
| `decision.verdict = block` | `block` at `critical` risk |
| a report whose claims cite evidence | every hypothesis, probe, experiment and blocking finding carries evidence ids, indexed at the end |

### How a decision is reached

Three rules do the work, and each is asserted by a test:

1. **Nothing is attributed to a mechanism the run does not support.** A scenario
   is only linked to an intervention when the failure the run recorded is one
   that intervention repairs. A disclosed credential is not a dropped clause and
   is not fixed by the same change, so the two get different interventions
   (`security_guard_enabled` vs `compression_disabled`) instead of one blanket
   "revert the candidate".
2. **A named case that lost a mandatory clause blocks.** A scenario is a hard
   failure when the candidate answered without a phrase its expectation names in
   `must_include`, or surfaced one it names in `must_avoid` — whatever the rest
   of the answer scored. On a safety answer, the missing half is the part the
   customer needed.
3. **The aggregate does not get to hide the cases.** The paired interval now
   confirms the regression, but the block also rests on the eight named,
   evidence-linked scenarios. A release gate that looked only at one aggregate
   number would be easier to game and harder to audit.

`ReleaseDecision.blocking_findings` holds ids of the run's `Finding` rows — the
run layer already owns the finding → evidence link, so a reviewer opening a
blocking id gets the check-level rationale. The list is capped at eight and the
report states the omitted count, so a bounded list never reads as exhaustive.

### The counterfactual seam

`investigation/providers.py` defines `CounterfactualProvider`: give it a
regressed scenario, get back one `Attempt` per intervention it considered. The
container now installs `EngineCounterfactualProvider`, which delegates to the
measured replay engine in `evalpilot/counterfactual/`.

A replay re-executes the candidate with one intervention applied and scores the
result from persisted evidence. On the demo fixture, disabling compression
restores the seven dropped-clause scenarios, while restoring the security guard
eliminates credential disclosure. Controls show no effect.

`DeterministicProvider` remains as an explicit offline/error fallback. Its
output is labelled as predicted rather than measured; the measured provider is
the default used by the running service.

### Memory

`memory/` seeds four authored incidents (`docs/V2_INTERFACES.md` requires at
least three) and scores them against a run's symptoms. Scoring is per symptom
line, then aggregated: each line is a mini-query with its own coverage score and
the incident is judged on the line it explains best, because pooling every
failure into one bag of words lets the unrelated lines drown a decisive match.
Within a line, terms are weighted by inverse document frequency and terms the
corpus does not know at all are dropped, so the score reads as "fraction of the
recognisable part of this failure the incident accounts for".

The matcher is deliberately lexical, not an embedding search: the investigation
must be reproducible offline, and every recall has to be explainable by the
exact terms that matched. `MemoryMatch` carries `matched_terms` and a `reason`
built from them, so the UI and the report can say *why* an incident was recalled.

The terms handed to the matcher come only from observed failures — the
scenario's own question and the required content it lost or the markers it
disclosed. No inference about a cause goes in, so the fixtures have to earn the
match on the failure itself and cannot be talked into an incident the run does
not resemble. `tests/test_investigation.py` asserts that no cause vocabulary
leaks into the query.

Recalled incidents then *narrow* the investigation rather than expanding it: an
incident only contributes a hypothesis when the run actually regressed on the
scenario that incident guards. Each incident carries an `intervention` field
read from the persisted row, which is what turns "we have seen this before" into
a concrete counterfactual to replay.

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

## Contract concerns (V2)

6. **The V2 event vocabulary is the run vocabulary.** `docs/V2_INTERFACES.md`
   asks the investigation stream to "reuse the run-event envelope", and
   `docs/INTERFACES.md` freezes the type list, so the same types are reused with
   `run_id` holding the investigation id. The stream starts with `run.started`
   and ends with `run.completed` — accurate, but the prefix is a little odd for
   a client that renders both streams side by side. Two things make it
   unambiguous, and both are asserted by tests: the payload's
   `data.investigation_id` is always set, and an investigation can never share
   an id with a run.
7. **`events.run_id` lost its foreign key.** SQLite cannot drop a constraint
   with `ALTER TABLE`, so the column was rebuilt once as `entity_id` during
   `Database.initialize` (guarded on the column shape, so the row copy runs at
   most once per file). Fresh databases get the new shape directly and copy
   nothing.
8. **`ReleaseDecision.blocking_findings` holds finding ids, not evidence ids.**
   `docs/V2_INTERFACES.md` types the field as `list[uuid]` without saying which
   entity. Findings are the right referent — they are what a release gate acts
   on, and the run layer already carries their evidence links — but the contract
   does not state it, so the interpretation is recorded here and in the model
   docstring.
9. **`HistoricalIncident` gained a field.** The contract's incident shape has no
   place to record the change that fixed the incident, and without it a recalled
   incident cannot produce a concrete counterfactual. `intervention` is added as
   an optional field, which is additive and breaks no existing field name.
