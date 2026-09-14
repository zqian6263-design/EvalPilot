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

Counterfactual results:

| Scenario | Intervention | Original | Replay | Verdict |
|---|---|---:|---:|---|
| `tenant-metadata-overwrite` | `identity_metadata_stripped` | 0.50 | 0.95 | `root_cause` |
| `tenant-identity-injection` | `identity_metadata_stripped` | 0.6667 | 0.9667 | `root_cause` |
| `tenant-camelcase-alias-injection` | `identity_metadata_stripped` | 0.6667 | 0.9667 | `root_cause` |

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
