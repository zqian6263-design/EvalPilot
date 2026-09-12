# Parallel Work Plan

## V1 completed

| Stream | Branch | Verification |
|---|---|---|
| Evaluator | `task/evaluator` | 72 evaluation tests passed |
| API core | `task/api-core` | runnable FastAPI and backend tests passed |
| Frontend | `task/frontend` | production build and fixture tests passed |
| Evaluation integration | `task/eval-integration` | full backend suite and startup checks passed |
| E2E integration | `task/e2e-integration` | 31/31 live-stack checks passed |

## V2 completed

| Stream | Branch | Verification |
|---|---|---|
| Counterfactual engine | `task/v2-counterfactual` | 36 dedicated tests, full backend suite passed |
| Investigation backend | `task/v2-investigation` | 51 investigation tests + 4 decision tests passed |
| Investigation frontend | `task/v2-frontend` | 119 frontend tests and production build passed |
| Codex integration | `main` | measured provider injected, browser workspace wired, V2 E2E passed |

## Final integrated state

- A confirmed 26-case regression run can start an autonomous release investigation.
- The investigation produces risk hypotheses, historical memory matches, follow-up probes, measured counterfactual replays, and a release decision.
- The real replay engine attributes seven dropped-clause regressions to `compression_disabled` and the credential disclosure to `security_guard_enabled`.
- The release decision is `BLOCK`, risk `CRITICAL`, with evidence-backed blocking findings.
- The Markdown report is available at `/api/investigations/{id}/report.md`.
- `#investigation` and `#investigation&demo` deep links work in the browser.
- The existing confirmed-regression console remains unchanged.

## Final tests

- Backend: full pytest suite.
- Frontend: Vitest and production build.
- V1: `scripts/e2e-check.ps1`.
- V2: `scripts/v2-e2e-check.ps1`.
- Browser: local investigation console inspected visually.
