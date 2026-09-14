# P3 验收记录

Status: **PASSED**

Date: 2026-09-14

Verified commit: `3be101c7be0b7ae8cb0609a54f50e65a7fac550c`

Scope: bounded browser task modality, the second public open-source adapter, browser evidence, investigation, and counterfactual replay.

## Fresh end-to-end acceptance

Command:

```powershell
pwsh -NoProfile -File .\scripts\p3-browser-check.ps1
```

Result: exit code `0`, `P3 browser acceptance OK`.

- Run id: `a092cc95-0bef-404d-b552-8e46ff5db65c`
- Investigation id: `c2c46b55-acfc-4e07-8f88-819cdc81fd06`
- Matched scenarios: `6`
- Regressions: `3`
- Stable controls: `3`
- Screenshot evidence: `12`
- Trace evidence: `12`
- Unique screenshot paths: `12`
- Counterfactual replays: `3`, all `root_cause`
- Decision: `BLOCK / CRITICAL`
- Acceptance checks: `14 / 14` passed

Detected regressions:

- `tenant-metadata-overwrite`
- `tenant-identity-injection`
- `tenant-camelcase-alias-injection`

Counterfactual results (measured through the browser, re-run 2026-09-14 after the
replay-seam fix):

| Scenario | Intervention | Original | Replay | Verdict |
|---|---|---:|---:|---|
| `tenant-metadata-overwrite` | `identity_metadata_stripped` | 0.50 | 1.00 | `root_cause` |
| `tenant-identity-injection` | `identity_metadata_stripped` | 0.6667 | 1.00 | `root_cause` |
| `tenant-camelcase-alias-injection` | `identity_metadata_stripped` | 0.6667 | 1.00 | `root_cause` |

Measured evidence, from `docs/P3_BROWSER_RESULT.json`:

- run id `c1cee6b6-2ff7-41a7-a352-46c103075392`,
  investigation id `8d387eb7-05d2-47e9-aab3-007e11a95361`
- `measured_browser_replays`: `3` replay traces carrying
  `intervention=identity_metadata_stripped`
- `measured_replay_arms`: `6` (both arms of every counterfactual executed in a
  real browser); `measured_replay_screenshots`: `18` = the run's 12 plus one per
  arm; `measured_replay_traces`: `18`
- every counterfactual rationale reads `Replayed '…' under
  'identity_metadata_stripped': score 0.50 -> 1.00`, which only the measured
  engine writes
- mean difference `-0.1944`, paired CI `[-0.3611, -0.0556]`, decision
  `BLOCK / CRITICAL`

### Correction (2026-09-14, P5 evidence audit and P3 replay fix)

This record previously listed the three replays as `0.50 -> 0.95` and
`0.67 -> 0.9667`. Those values were the deterministic fallback's **predictions**,
not measurements: re-reading the persisted run
(`.runtime/p3-browser-f06b723a40734f9f90631d39fd42a7ff/evalpilot.db`) showed `0`
trace rows carrying an intervention and rationales reading "is predicted to
restore the scenario to 0.9...".

Cause: the browser replay could not execute outside the runner at all.
`CounterfactualEngine._measure` passes the investigation's reading source as the
executor's `db`, and `BrowserCaseExecutor.execute` requires
`db.run_artifact_dir(...)`, which `RepositoryReadingSource` did not implement —
so the engine raised and `EngineCounterfactualProvider` fell back. The replay
engine also held a registry with the browser tool disabled, which would have
refused the `browser_run` invocation anyway.

Both are fixed: the reading sources implement `run_artifact_dir`, the container
wires a replay registry that keeps Python disabled but honours the browser
policy, and the browser executor now records its request (including the
intervention) on the trace evidence so a replay is auditable from the evidence
itself. `scripts/p3-browser-check.ps1` fails unless the replays are measured, and
`backend/tests/test_browser_counterfactual_replay.py` pins the behaviour against
a real Chromium page.

## Repository-wide checks

- Backend: `397` tests collected; full suite exit code `0`; `1` skipped; one third-party Starlette deprecation warning.
- Frontend: `153 / 153` Vitest tests passed.
- Frontend typecheck: passed.
- Frontend production build: passed.
- Public site checker: passed.
- Public site: HTTP `200`; browser-evidence marker and `12 / 12` marker present.

## Hosted CI

The verified product commit passed the hosted release checks:

- CI on `docs/p3-browser-modality`: https://github.com/zqian6263-design/EvalPilot/actions/runs/34799676629
- CI on `main`: https://github.com/zqian6263-design/EvalPilot/actions/runs/34799846441
- Pages deployment on `main`: https://github.com/zqian6263-design/EvalPilot/actions/runs/34799846440

## Evidence

- `docs/P3_BROWSER_RESULT.json`
- `docs/P3_BROWSER_MODALITY.md`
- `scripts/p3-browser-check.ps1`
- `integrations/mem0_retro/browser_workload.json`
- `backend/evalpilot/browser_tool.py`
- `backend/evalpilot/sut/browser_executor.py`

## Boundaries

- The second adapter delegates to unmodified public `mem0ai` npm releases; it is a browser-facing adapter, not the upstream full Next.js UI.
- Browser execution is opt-in through `EVALPILOT_BROWSER_ENABLED=true` and remains off by default.
- Browser screenshots and traces prove rendered interaction; scores still come from deterministic checks over extracted answers.
- The measured decision is a candidate-release block, not a claim that every production vector store is affected.
