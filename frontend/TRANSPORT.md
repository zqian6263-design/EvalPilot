# Transport adapter notes

`frontend/src/api` is the only place the console talks to a backend. This file
records what the adapter assumes about the running service, which assumptions
are *local decisions* rather than frozen contract, and what the console does
where the contract cannot supply a field.

`docs/INTERFACES.md` is the source of truth for the shared contract and is not
amended here. Everything below is either a reading of that document or an
explicitly local narrowing of a field it leaves open.

## Files

| File | Role |
| --- | --- |
| `types.ts` | The frozen models, plus the local shapes named below. |
| `transport.ts` | The `Transport` interface both backends satisfy. |
| `httpTransport.ts` | The real service, through the Vite `/api` proxy. |
| `mockTransport.ts` | Bundled fixtures, for the offline demo and the view tests. |
| `evaluation.ts` | Turns a live run detail + report into the console's view model. |
| `runLifecycle.ts` | Driving a live run: create-or-adopt, start, wait, read report. |

## Contract gaps this adapter works around

### 1. `GET /runs/{run_id}` returns an envelope, not a `Run`

`docs/INTERFACES.md` describes the endpoint as "`Run` with test cases and
evidence summaries" without fixing the field layout. The running service wraps
the run:

```json
{
  "run": { "id": "…", "status": "completed", … },
  "test_cases": [ … ],
  "evidence": [ … ],
  "evidence_count": 78,
  "finding_count": 3,
  "event_count": 66
}
```

`HttpTransport.getRun` detects `"run" in payload` and flattens it into the
`RunDetail` the console renders (`normalizeRunDetail` in `httpTransport.ts`).
A payload that is already flat passes through unchanged, which is what
`MockTransport` sends and what the console tests drive.

**Why detection rather than a rename:** `MockTransport` already returned a flat
detail before the live path existed. Normalising unconditionally would have
silently emptied the offline console. Detection keeps both working and survives
a backend that later adopts the flat shape.

**Counts are the backend's tally.** `evidence_count` / `finding_count` /
`event_count` are taken from the envelope as sent and default to `0` — never to
`array.length`. The arrays are not paged today, but a count the backend omitted
is still an omission, and reporting a measured length as the backend's total
would be the console asserting something it was not told.

`RunDetail` gained these three required fields; `MockTransport` supplies its own
totals so the offline console reports real tallies too.

### 2. `Report.metrics` is a flat aggregate, not a `MetricValue` map

The contract types `Report.metrics` as a bare `object`. The service fills it
with:

```text
baseline_cases, candidate_cases, matched_scenarios,
baseline_pass_rate, candidate_pass_rate,
baseline_score, candidate_score,          # weighted
regression_detected, baseline_version, candidate_version,
regressed_scenarios, control_scenarios, fixed_scenarios,
by_category, findings_by_severity
```

None of the frozen `MetricValue` fields (`baseline`, `candidate`, `unit`,
`direction`, `label`, `n`) appear. The console's metric panel and report table
render `MetricValue`, and the fixture corpus produces all seven of them
(`task_success`, `citation_coverage`, `correct_refusal`, `format_compliance`,
`groundedness`, `latency_p50`, `answer_tokens`).

**What the adapter does instead of fabricating:**

- `baseline_pass_rate` / `candidate_pass_rate` **are** a baseline/candidate pair
  over matched cases — exactly what `MetricValue` means — so `task_success` is
  converted from them, with `n = matched_scenarios`, the denominator the
  backend itself divided by. This is a re-reading, not an estimate.
- Every other row renders as **"not reported by this evaluation service"** and
  is additionally listed in a *Not reported* block on the live metric panel.
  The offline pane's numbers are the fixture corpus' own and are never
  substituted into a live run.

`LiveReportMetrics` in `types.ts` names the aggregate's fields. That is a local
narrowing for type safety; every field is optional and a payload lacking one
degrades to "not reported".

### 3. `GET /demo/seed` returns metadata, not a project or run

The contract says the endpoint is "deterministic demo metadata only; no side
effects", and the service honours that: it returns a project *name*, the two
version strings, a seed, and a case count — no uuids.

`DemoSeed` in `types.ts` claims `project: Project` and `runs: Run[]`, which the
live service does not send. **The interface is aspirational and the adapter does
not rely on it:** `getDemoContext` reads only `project.name`, `project.scenario`
(or `scenario`), `baseline_version`, `candidate_version`, `seed` and
`case_count`, and resolves identities through the real endpoints.

### 4. There is no per-case score and no repeat sampling

Every live case row carries `status` (`passed` / `failed`) and an `output`, and
no score. There is no repeat count and no regression-confidence estimate
anywhere in the report. The console's offline views render all three because
the fixture corpus computes them.

**Consequence:** the live case table shows statuses and answers, not scores, and
says so in its caption. The live verdict panel shows counts and the backend's
own `regression_detected`, not a confidence figure. The live report has no
"repeats" or "noise only" row. No substitute number is printed in any of these
places.

### 5. `GET /runs/{run_id}/events` defaults to SSE

The contract permits SSE or NDJSON. The service defaults to `text/event-stream`
and offers `?fmt=ndjson`. `streamEvents` accepts both: it splits on newlines,
which handles either framing, and strips a leading `data:` only when the
content type says SSE.

## Derivations the adapter performs

Two things in `evaluation.ts` are computed rather than copied. Both are
readings of two backend facts, and both are named so they cannot be mistaken for
measurements:

1. **Case pairing.** A baseline case and a candidate case are the same scenario
   when their `input.scenario_id` matches (falling back to the title with its
   `[baseline]` / `[candidate]` suffix removed). A scenario present on only one
   side is excluded rather than paired with a hole, and its id is returned in
   `unmatchedScenarios` so the view can say how many were dropped instead of
   quietly showing a shorter table.
2. **`regressed`.** A row is regressed when the baseline passed and the
   candidate did not. This is the same statement the backend's own finding text
   makes ("the baseline version passed scenario X but the candidate version
   failed it"). It is not a score comparison, and no threshold is applied.

`latencyDeltaMs` is the candidate's `latency_ms` minus the baseline's, both as
reported per case; it is `null` when either side recorded none.

## Offline fallback

The console probes `/api/health` with a 1.2 s timeout when *Start demo run* is
pressed.

- **Healthy and seedable** → `getDemoContext` resolves a project and a run, the
  run is started (or adopted if it already is), followed to a terminal status,
  and the live views render its real detail and report.
- **Healthy but not seedable** → the console says so and renders the fixtures.
- **Unreachable** → the console renders the fixtures and the provenance bar
  reads "Offline demo — bundled fixtures"; the run console carries an explicit
  notice that the figures are not evidence about a real system.

The header names the run the backend issued whenever there is one, and says
"not started" rather than printing a run id that does not exist.

## Idempotence

`getDemoContext` reuses before it writes:

1. read `/demo/seed` for versions, seed and case count;
2. adopt the project whose name matches the seed, else `POST /projects`;
3. adopt a run for those exact versions, else `POST /runs`.

A second *Start demo run* therefore reopens the same run rather than
accumulating near-identical ones. `ensureRunStarted` will not start a run that
is already starting or finished — the console opens it as it stands and states
why, rather than replaying a start the backend would answer with 409.

## Verification

```bash
cd frontend
npm test        # adapter unit tests, incl. envelope normalisation and idempotence
npm run build   # tsc -b && vite build
```

The adapter's behaviour against the *real* service is exercised end to end by
`scripts/e2e-check.ps1` — see `docs/E2E.md`.
