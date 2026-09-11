# EvalPilot — frontend console

React + TypeScript + Vite demo console for the EvalPilot regression-evaluation
digital employee. Product contract: `../docs/SPEC.md`. API contract:
`../docs/INTERFACES.md` (frozen — this package does not change it).

## Run it

```powershell
../scripts/start-all.ps1                 # start the backend and this console together
../scripts/start-frontend.ps1            # install, start Vite, open a browser
../scripts/start-frontend.ps1 -NoOpen    # do not open a browser
../scripts/test-frontend.ps1             # type check + unit tests + production build
../scripts/e2e-check.ps1                 # drive a real run through the whole stack

npm run dev        # dev server on :5173, /api proxied to http://127.0.0.1:8000
npm test           # vitest
npm run build      # tsc -b && vite build
```

## Two renderings: live backend and offline fixtures

"Start demo run" probes `/api/health` once, with a 1.2s timeout, and then does
one of two things.

**Backend reachable.** It resolves the seeded project and run over HTTP —
adopting the demo project if it exists and a run for the seeded versions if one
has already been made, otherwise creating them — starts the run if it is not
already moving, follows it to a terminal status, and renders the run the
service actually produced. Pressing the button again reopens that same run
rather than creating a second one. The header names the run id the backend
issued.

**Backend not reachable.** The console runs against the deterministic fixtures
in `src/fixtures/` and says so, in a bar that cannot be missed:

> OFFLINE DEMO — BUNDLED FIXTURES · Every figure below is seeded fixture data,
> not a real evaluation

No demo should stall because a backend was not started, and no reviewer should
mistake fixture data for a real result. Both are requirements, so both are
handled explicitly rather than left to chance. The `Fixtures / Backend` rocker
in the header switches between them by hand.

### What the live run can and cannot show

The two renderings are not the same document with a different data source, and
the console does not pretend they are. The evaluation service reports a
pass/fail status per case and one aggregate pair (a pass rate); it reports no
per-case score, no per-metric breakdown, and no confidence estimate. So a live
run shows:

- the case table with real statuses, answers, and latencies — and **no score
  column**, because none exists;
- the metric panel with the one metric the service reports, and the other six
  listed under **Not reported** rather than filled in;
- findings with the evidence rows they resolve to, plus any id that resolves to
  nothing.

The offline fixture corpus computes all seven metrics and a per-case score, and
labels itself as fixture data. See `TRANSPORT.md` for the full list of adapter
assumptions and contract gaps.

## Demo walkthrough

Press **Start demo run**. What you get depends on whether the backend is up;
the walkthrough below follows the offline fixture path, which is the richer of
the two and the one that needs no setup.

1. **Pick a scenario** (left panel). Three ship; the first is the headline.
2. **Start demo run.** The tape draws two traces against a pre-printed tolerance
   band: the baseline in deep blue, the candidate in muted graphite while it
   tracks the baseline and in full vermilion wherever it leaves the band.
   *That departure is the regression* — it is a place on the chart, not a badge.
3. **Read the verdict** beneath the tape: the conclusion in words, then the four
   numbers that justify it (matched, repeats, regressed, confidence).
4. **Check the metrics** in the right column: six metrics, baseline against
   candidate, each with a direction-aware meter and a signed delta.
5. **Audit the record.** The case table lists all 24 matched cases. Filter by
   category or status, sort by largest regression, or tick "regressions only".
6. **Open an evidence packet.** Any row opens the drawer: the exact prompt, both
   answers side by side, which required facts each stated, the citations each
   returned, the execution log, the deterministic checks with their reasons, and
   the evaluator's rationale.
7. **Findings and Report** have their own nav keys, with severity, confidence,
   and recommendations.

Deep links work and are meant to be used in a live demo:
`#report`, `#findings`, `#console&case=22`, `#console&scenario=improvement`.

`#console&demo` additionally runs the start sequence on load, without a click —
for a slide that should open already running, a README link, or the screenshot
in `../scripts/e2e-check.ps1`.

## The three scenarios

One corpus of 24 matched cases and one scoring module produce three different
conclusions. A tool that only ever reports a regression is not a comparison
tool, it is a rubber stamp — so the console ships a case where the answer is no,
and a case where the answer is yes.

| Scenario | Change under test | Verdict |
| --- | --- | --- |
| Citation regression | retrieval `top_k` 5 → 3, terser answer prompt | 6 of 24 stable regressions; citation coverage 94% → 80%; latency 19% better |
| No regression (control) | help-centre copy edit only | nothing moved; every metric at exactly zero delta |
| Safe optimisation | context trimming + streamed responses | latency 58% better, **quality unchanged** (answers are byte-identical) |

The control scenario matters most for the product's claim: because the answers
are identical, the rubric jitter is identical, and every delta is *exactly*
zero. If the comparison were measuring noise instead of behaviour, this scenario
is where it would show.

## How the fixtures stay honest

`src/fixtures/` is deterministic by construction and the tests enforce it:

- No `Math.random`, no `Date.now`. The only clock is the frozen `BASE_TIME`
  literal; every timestamp is an offset from it.
- The rubric jitter is seeded from the **answer's own text**, so an identical
  answer scores identically in every scenario. That is what makes a control case
  a real control, and what lets a delta be attributed to the version change
  rather than to sampling luck.
- The jitter is bounded to ±0.015, well inside the 0.1 regression threshold. A
  rubric rater may shade a result; it may never create one.
- The report summary is **generated** from the metrics it describes, and a
  metric that did not move is not mentioned. Hand-written prose drifts the
  moment a number changes, and a report that contradicts its own table is the
  exact failure this product exists to catch.

`src/fixtures/fixtures.test.ts` (21 tests) is the guard: determinism, control
integrity, one-finding-per-regressed-case, evidence-link resolution, event
sequence numbering, and the three scenario verdicts.

## Layout

```text
src/api/          types.ts mirrors docs/INTERFACES.md; Transport + Http/Mock implementations
                  evaluation.ts assembles a live run into the console's view model
                  runLifecycle.ts drives create / start / wait / read-report
src/components/   Tape (hero), Verdict, Metrics, CaseTable, EvidenceDrawer, EventIndex, Header, DemoEntry
                  Live*, the same panels fed by a real run
src/views/        Console, Findings, Report — and LiveConsole, LiveFindings, LiveReport
src/fixtures/     the deterministic demo corpus: cases, answers, scoring, metrics, findings, timeline
src/lib/          formatting helpers
src/styles/       tokens.css (every colour and size), then shell / tape / record / report
```

The visual world is documented in `DESIGN.md`. The API adapter's assumptions
about the running service are documented in `TRANSPORT.md`.

## Verification

```powershell
../scripts/test-frontend.ps1     # type check + unit tests + production build
npm test                         # 47 tests: fixtures, adapter, run lifecycle
../scripts/e2e-check.ps1         # drives a real run over HTTP end to end
```

`e2e-check.ps1` starts the stack, creates and runs a real evaluation, and
asserts the reported metrics and evidence-linked findings — see `../docs/E2E.md`.

## Known gaps

- **Screenshot evidence is a placeholder.** No browser capture runs in this
  worktree, so `kind: screenshot` renders a ruled frame carrying the artifact
  URI and the words "not captured in this build". It is labelled rather than
  faked.
- **The rubric judge is modelled.** The five deterministic checks are computed
  for real from the fixture answers. The LLM half of the rubric described in
  `docs/SPEC.md` is modelled as a deterministic, text-seeded jitter and is
  labelled `rubric (modelled)` wherever it appears.
- **`GET /api/demo/seed` has no frozen response schema.** `docs/INTERFACES.md`
  names the endpoint and says "deterministic demo metadata only" without
  expanding the shape, so `DemoSeed` in `src/api/types.ts` is a local
  interface. It is marked as such and the console tolerates every field being
  absent.
- **`Report.metrics` is an untyped object** in the contract. The report view
  reads it through a narrow shape and renders "not reported by this backend"
  for any metric it does not recognise, rather than inventing a value.
- **`GET /runs/{run_id}` returns an envelope.** The frozen contract describes
  the endpoint as "`Run` with test cases and evidence summaries" without fixing
  the layout; the service wraps the run as
  `{run, test_cases, evidence, evidence_count, finding_count, event_count}`.
  `normalizeRunDetail` flattens it and `RunDetailEnvelope` names it. Both are
  adapter-local; the contract is unchanged. See `TRANSPORT.md`.
- **The live run shows fewer metrics than the fixture run.** The service
  reports a pass rate and no per-metric or per-case score, so a live console
  shows one metric and lists the rest as unavailable. This is a limitation of
  the service's report, not of the console, and it is stated on screen rather
  than papered over with fixture numbers.
