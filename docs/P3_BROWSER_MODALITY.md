# P3 浏览器任务模态与第二开源应用适配器

Date: 2026-09-14

## Goal

Extend EvalPilot beyond HTTP JSON execution by adding a bounded browser task modality, and apply it to a second public open-source application path.

## Second application adapter

The second public adapter uses the Apache-2.0 `mem0ai` package as its application core and exposes a lightweight browser-facing memory isolation portal:

- baseline: `mem0ai@3.1.1`
- candidate: `mem0ai@3.1.0`
- public issue: https://github.com/mem0ai/mem0/issues/6342
- public fix PR: https://github.com/mem0ai/mem0/pull/6343
- adapter: `integrations/mem0_retro/server.mjs`
- browser UI: `integrations/mem0_retro/ui.html`
- workload: `integrations/mem0_retro/browser_workload.json`

The browser portal delegates to the unmodified public npm releases. The adapter, not upstream mem0, owns the test UI and deterministic local embedding endpoint. The reviewed defect is in the public `memory.update()` identity-scope behavior.

## Browser modality

The runtime now exposes `browser_run` when explicitly enabled. It is disabled by default and uses the same policy-first design as other tools.

Supported actions:

- `goto`
- `fill`
- `click`
- `select`
- `press`
- `wait_for`
- `wait_for_text`
- `assert_text`
- `extract_text`

Every call records:

- action trace with URL after each step;
- final URL and page title;
- extracted answer;
- browser console/page errors;
- screenshot evidence;
- browser run trace artifact.

Security boundaries:

- browser host allowlist;
- maximum 25 actions per task;
- no arbitrary JavaScript execution;
- screenshot path must stay under the artifact root;
- URL is revalidated after navigation-producing actions;
- optional and disabled unless `EVALPILOT_BROWSER_ENABLED=true`;
- Playwright sync API runs in a worker thread when called from FastAPI's asyncio loop.

## End-to-end result

The browser test ran six matched scenarios against both releases:

```text
baseline: mem0ai-3.1.1
candidate: mem0ai-3.1.0
matched scenarios: 6
regressed scenarios: 3
control scenarios: 3
screenshot evidence: 12
trace evidence: 12
```

Detected regressions:

- `tenant-metadata-overwrite`
- `tenant-identity-injection`
- `tenant-camelcase-alias-injection`

Browser counterfactual replay (measured, re-run 2026-09-14):

| Scenario | Intervention | Original | Replay | Verdict |
|---|---|---:|---:|---|
| `tenant-metadata-overwrite` | `identity_metadata_stripped` | 0.50 | 1.00 | `root_cause` |
| `tenant-identity-injection` | `identity_metadata_stripped` | 0.67 | 1.00 | `root_cause` |
| `tenant-camelcase-alias-injection` | `identity_metadata_stripped` | 0.67 | 1.00 | `root_cause` |

Every replay executed both arms in a real browser: 3 replay traces carrying the
intervention, 18 screenshots and 18 browser traces in total (the run's 12 plus
one per replay arm), and rationales reading "Replayed ... score 0.50 -> 1.00".
The earlier version of this table recorded the deterministic fallback's
predictions (`0.95` / `0.9667`); see the correction in `docs/P3_VERIFICATION.md`
for the cause and the fix.

Final decision: `BLOCK / CRITICAL`.

## Reproduce

```powershell
pwsh -NoProfile -File .\scripts\p3-browser-check.ps1
```

The script starts the public OSS-backed SUT, starts EvalPilot with browser execution enabled, runs both versions, checks screenshot and trace evidence, runs the investigation, and requires three *measured* browser root-cause replays: it fails unless every counterfactual rationale is written by the replay engine and the run holds one browser trace per replayed arm plus the matching screenshots.

## Evidence

- `docs/P3_BROWSER_RESULT.json`
- `integrations/mem0_retro/browser_workload.json`
- `integrations/mem0_retro/ui.html`
- `scripts/p3-browser-check.ps1`
- `backend/evalpilot/browser_tool.py`
- `backend/evalpilot/sut/browser_executor.py`

## Limits

- The browser portal is an adapter around the public `mem0ai` package, not the upstream repository's full Next.js UI.
- The deterministic embeddings isolate memory-scope behavior and do not exercise every production vector store.
- Browser execution is opt-in; the default EvalPilot runtime remains offline and does not launch a browser.
- Screenshots and traces are evidence of the adapter's rendered behavior, while scores still come from deterministic checks over the extracted answer.

## Verification record

Fresh end-to-end and repository-wide evidence is recorded in [docs/P3_VERIFICATION.md](P3_VERIFICATION.md).
