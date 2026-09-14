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

Counterfactual results (**predicted, not measured** — see the correction below):

| Scenario | Intervention | Original | Replay | Verdict |
|---|---|---:|---:|---|
| `tenant-metadata-overwrite` | `identity_metadata_stripped` | 0.50 | 0.95 | `root_cause` |
| `tenant-identity-injection` | `identity_metadata_stripped` | 0.6667 | 0.9667 | `root_cause` |
| `tenant-camelcase-alias-injection` | `identity_metadata_stripped` | 0.6667 | 0.9667 | `root_cause` |

### Correction (2026-09-14, P5 evidence audit)

The three rows above are the deterministic fallback's **predictions**, not replay
measurements. Re-reading the persisted run
(`.runtime/p3-browser-f06b723a40734f9f90631d39fd42a7ff/evalpilot.db`) shows:

- `0` trace evidence rows whose request carries an intervention (the P1 mem0 run
  of the same era has `3`, so the audit distinguishes the two);
- `counterfactual_experiments.rationale` reads "Replaying
  'tenant-metadata-overwrite' with 'identity_metadata_stripped'
  (post-generation mandatory-clause validator) is **predicted** to restore the
  scenario to 0.9...", which is the fallback's wording, not the engine's
  "Replayed ... score 0.50 -> 1.00".

Root cause is **not** the enum-only intervention accessor that broke the MCP
adapter (this intervention is a built-in member). The browser replay cannot
execute outside the runner at all: `CounterfactualEngine._measure` passes the
investigation's reading source as the executor's `db`, and
`BrowserCaseExecutor.execute` requires `db.run_artifact_dir(...)`, which
`RepositoryReadingSource` does not implement — so the engine raises and the
provider falls back.

Status: **unfixed, open**. `scripts/p3-browser-check.ps1` does not yet assert a
measured replay, so the browser counterfactual claim is currently unsupported by
evidence. Fixing it means extending the replay reading-seam for browser cases
and re-running the browser acceptance; that is a separate task and no claim of a
fix is made here.

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
