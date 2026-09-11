# End-to-end check

This document describes `scripts/e2e-check.ps1`: what it starts, what it
asserts, how to read a failure, and what it deliberately does not do.

The check exists because "the console loads" is not evidence that the product
works. It drives the whole path over real HTTP — create a run, start it, follow
it to completion, read the report — and then asserts the things the product
claims on its own behalf: that the seeded regression is *detected*, that the
reported numbers agree with the cases they were computed from, and that every
finding links to evidence that exists.

Nothing is mocked. Every value asserted on is read from the running service.

## Running it

```powershell
.\scripts\e2e-check.ps1                    # start the stack, check, stop it again
.\scripts\e2e-check.ps1 -KeepRunning       # leave the stack up afterwards
.\scripts\e2e-check.ps1 -SkipScreenshot    # skip the browser capture
.\scripts\e2e-check.ps1 -TimeoutSeconds 120
```

Exit code is `0` when every check passes and `1` otherwise; the failing checks
are listed at the end. It is safe to re-run: a healthy stack is reused rather
than duplicated, and a check that starts nothing stops nothing.

Requirements: PowerShell 5.1+, the repo's `.venv` (or `python` on `PATH`), and
Node.js 20+. A browser is optional — only the screenshot step uses one.

## What it does

1. **Stack.** Invokes `scripts/start-all.ps1`, which starts both services
   detached behind health gates and records the PIDs it launched. If a service
   is already healthy it is adopted, not restarted.
2. **Health.** `GET /api/health` must answer `{status: "ok"}`.
3. **Run lifecycle.** Reuses the demo project if present, otherwise creates it;
   `POST /api/runs` with the seeded versions and seed; `POST /runs/{id}/start`;
   polls `GET /runs/{id}` until the status is terminal.
4. **Run detail.** Checks the response is the run *envelope* (`run`,
   `test_cases`, `evidence`, `evidence_count`, …), that the envelope's counts
   agree with the rows returned, that both versions executed, and that every
   scenario has exactly one case per version.
5. **Report.** Checks the report exists, that a regression is reported, and —
   the substantive ones — that the reported candidate pass rate equals the rate
   derived from the candidate cases' statuses, that the reported matched count
   equals the number of paired scenarios, and that the baseline passes every
   seeded case.
6. **Findings and evidence links.** For every finding: it cites at least one
   evidence row, every cited id resolves to a row in the run, its
   `test_case_id` names a case that exists, and it carries a recommendation.
7. **Frontend.** The console serves HTML with a `#root` mount point, and the
   dev server proxies `/api` to the backend (a broken proxy looks like a UI bug
   from the outside, so it is checked explicitly).
8. **Screenshot.** Captures `#console&demo` — the deep link that runs the same
   start sequence the *Start demo run* button does — so the frame shows the live
   run, not the cold-load fixture view. Written to `.runtime/e2e-console.png`.
   Skipped with a note when no Chrome or Edge is installed.
9. **Cleanup.** Stops only the processes this run started, via
   `start-all.ps1 -Stop`. Anything that was already running is left alone.

## Reading a failure

| Failure | What it means |
| --- | --- |
| `the run reaches a terminal status` | The run did not finish inside `-TimeoutSeconds`. Raise it, or read `.runtime/backend.err.log`. |
| `the reported candidate pass rate matches the case statuses` | The report and the case rows disagree. One of them is wrong; this is the check most worth investigating. |
| `every cited evidence id resolves to a row in the run` | A finding cites evidence the run did not record. The console would show a link count larger than the rows behind it. |
| `every scenario has exactly one case per version` | The planner produced an unpaired case. The console's case table pairs on `input.scenario_id` and would show fewer rows than the run executed. |
| `the dev server proxies /api to the backend` | The page loads but every API call fails. Check the Vite `server.proxy` target and that both services are on the ports the script was given. |
| `no file at …e2e-console.png` | Chrome or Edge was found but produced no file — usually a stale browser profile lock. Re-running normally clears it; `-SkipScreenshot` if not. |

Logs: `.runtime/backend.log`, `.runtime/backend.err.log`,
`.runtime/frontend.log`, `.runtime/frontend.err.log`.

## What it does not do

- **It does not assert on UI behaviour.** It checks the console serves and the
  proxy works; it does not click, type, or read rendered text. The screenshot is
  for a human to look at, not an assertion. The console's own view logic is
  covered by `frontend/src/api/*.test.ts` and the fixture suite.
- **It does not test the fixture fallback.** That path is exercised by
  `npm test` in `frontend`, which does not need a backend at all.
- **It does not measure quality.** It checks that the run's numbers are
  self-consistent and that the seeded regression is detected — not that the
  evaluation is good.

## Why each assertion is a check rather than a smoke test

A run returning HTTP 200 proves the server is up. These checks are chosen so
that a green result means something a reviewer can rely on:

- the regression check is on a demo whose candidate version is *deliberately*
  built to fail three scenarios, so "regression detected" is a real detection
  rather than a hard-coded `true`;
- the pass-rate cross-check re-derives the number from the case rows
  independently, so a report that disagrees with its own evidence fails;
- the evidence-link check is the machine-readable form of the requirement in
  `docs/SPEC.md` that every finding links to its inputs;
- the pairing check protects the console's central claim — that it compares two
  versions of the *same* input.

## Related

- `scripts/start-all.ps1` — the start/stop/status script the check drives.
- `frontend/TRANSPORT.md` — the assumptions these checks exercise.
- `docs/INTERFACES.md` — the frozen contract the assertions are written against.
