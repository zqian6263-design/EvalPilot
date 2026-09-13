# Zhipu GLM-4.7 Runtime Setup

## Scope

This configuration was validated on 2026-09-13 against:

- Base URL: `https://open.bigmodel.cn/api/paas/v4`
- Model: `glm-4.7`
- Protocol: OpenAI-compatible Chat Completions

No application code branch is required. Provider selection is environment-driven.

## Local configuration

Create or update the ignored local `.env` file:

```text
EVALPILOT_LLM_MODE=live
EVALPILOT_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
EVALPILOT_LLM_API_KEY=<your Zhipu API key>
EVALPILOT_LLM_MODEL=glm-4.7
EVALPILOT_LLM_TIMEOUT_SECONDS=240
EVALPILOT_JUDGE_MAX_CALLS=4
EVALPILOT_JUDGE_MAX_TOKENS=20000
```

Do not commit `.env`. The repository already ignores it.

## Validation

Start EvalPilot and check the resolved runtime:

```powershell
Invoke-RestMethod http://127.0.0.1:8141/api/runtime
```

Expected:

```json
{
  "mode": "live",
  "llm_configured": true,
  "model": "glm-4.7",
  "base_url_host": "open.bigmodel.cn",
  "fallback_active": false
}
```

Run the OOD planning benchmark:

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\planning_ood_check.py --live --output .runtime\zhipu-ood-planning.json
```

Expected: `6/6`, accuracy `1.0`.

Run the budgeted end-to-end live check:

```powershell
.\scripts\live-llm-check.ps1 -BackendPort 8141 -TimeoutSeconds 900
```

Expected: persisted model hypotheses and rationale, at least one model-guided counterfactual plan, `BLOCK / CRITICAL`, and no evidence/verdict override.

## Operational notes

- `glm-4.7` is a reasoning model and may be slower than non-reasoning providers.
- Use explicit Judge call/token budgets for repeatable runs.
- A 90-second provider timeout produced deterministic fallback in the first live attempt; 240 seconds completed successfully.
- Fallback never changes measured scores, evidence, counterfactual verdicts, or the release decision.
- Provider pricing and account plan terms are external and must be rechecked before quoting a new cost.