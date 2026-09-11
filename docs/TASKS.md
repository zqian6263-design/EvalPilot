# Parallel Work Plan

## Baseline

- Main contract commit: `2484dc1`
- Product and scoring docs commit on main: `36d349d`
- Shared contract: `docs/INTERFACES.md`

## Worktrees

| Stream | Branch | Worktree | Owned write scope | Status |
|---|---|---|---|---|
| API core | `task/api-core` | `D:\z工程文件\EvalPilot-worktrees\api-core` | `backend/**`, backend start/test scripts | running |
| Evaluator | `task/evaluator` | `D:\z工程文件\EvalPilot-worktrees\evaluator` | `backend/evalpilot/evaluation/**`, evaluator tests/docs | running |
| Frontend | `task/frontend` | `D:\z工程文件\EvalPilot-worktrees\frontend` | `frontend/**`, frontend start/test scripts | running |

## Merge order

1. API core, because it establishes the backend package and runnable service.
2. Evaluator, then connect its service to the API boundary.
3. Frontend, then verify it against the real API.
4. Codex integration pass: contracts, wiring, tests, demo data, scripts, README.

## Review gates

- No agent may modify another stream's owned paths.
- Shared interface changes require an explicit contract decision in `docs/INTERFACES.md`.
- Every stream must run its tests before being accepted.
- Codex reruns all tests after merge; agent-reported success is not accepted as final evidence.
- Failed or partial work is reviewed before merging; it is not automatically discarded.

## Integration checks

- Backend tests pass.
- Evaluator tests pass.
- Frontend build passes.
- Backend and frontend start together.
- Seeded demo completes end to end.
- UI reads real evidence and report data.
- Demo can be repeated without manual database cleanup.
