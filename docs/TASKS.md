# Parallel Work Plan

## Baseline

- Main contract commit: `2484dc1`
- Product and scoring docs commit on main: `36d349d`
- Shared contract: `docs/INTERFACES.md`

## Completed streams

| Stream | Branch | Merge result | Verification |
|---|---|---|---|
| Evaluator | `task/evaluator` | merged | 72 tests passed |
| API core | `task/api-core` | merged with adapter split | 43 backend tests passed |
| Frontend | `task/frontend` | merged | 21 tests, production build passed |

## Active integration streams

| Stream | Branch | Owned scope | Goal |
|---|---|---|---|
| Evaluation integration | `task/eval-integration` | runner, adapter, backend integration tests | route persisted run data through the statistical evaluation engine |
| E2E integration | `task/e2e-integration` | frontend API adapter and E2E scripts | verify the browser console against the live backend |

## Merge order

1. Evaluation integration.
2. E2E integration.
3. Codex final integration pass: resolve remaining contract mismatches, run clean setup, and update README.

## Review gates

- No agent may modify another stream's owned paths.
- Shared interface changes require an explicit contract decision.
- Every stream must run its tests before acceptance.
- Codex reruns all tests after merge; agent-reported success is not accepted as final evidence.

## Integration checks

- Backend tests pass.
- Evaluator tests pass.
- Frontend tests and build pass.
- Backend and frontend start together.
- Seeded demo completes end to end.
- UI reads real evidence and report data.
- Demo can be repeated without manual database cleanup.
