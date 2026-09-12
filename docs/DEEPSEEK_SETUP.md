# DeepSeek V4 Pro Runtime Setup

## Decision

Do not replace Claude Code's underlying API. Keep Claude Code on its current authentication for reliable repository work. Use DeepSeek V4 Pro as EvalPilot's product runtime for planning, judge rationale, and report explanation.

## PowerShell environment

Set the model id exactly as provided by DeepSeek:

```powershell
$env:EVALPILOT_LLM_MODE = "live"
$env:EVALPILOT_LLM_BASE_URL = "https://api.deepseek.com"
$env:EVALPILOT_LLM_API_KEY = "<your DeepSeek API key>"
$env:EVALPILOT_LLM_MODEL = "deepseek-v4-pro"
$env:EVALPILOT_LLM_TIMEOUT_SECONDS = "45"
```

Then restart EvalPilot:

```powershell
.\scripts\start-all.ps1 -Stop
.\scripts\start-all.ps1
```

Check the resolved runtime:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/runtime
```

Expected:

```json
{
  "mode": "live",
  "llm_configured": true,
  "model": "deepseek-v4-pro",
  "base_url_host": "api.deepseek.com",
  "fallback_active": false,
  "tools": ["kb_search", "http_get", "file_read"]
}
```

## Evidence and safety

- The model may propose hypotheses and explain the decision.
- The model may not overwrite the measured regression verdict, risk level, blocking findings, evidence ids, or counterfactual results.
- API failures and invalid JSON fall back deterministically and record a fallback reason.
- The API key is never returned, persisted, logged, or stored in a report.
- Without a key, the complete demo still runs offline and reproducibly.

## Competition demo

- Deterministic deep link: `http://127.0.0.1:5173/#investigation&demo`
- Market view: `http://127.0.0.1:5173/#market`
- Runtime badge shows `DETERMINISTIC` or `LIVE LLM · <model>`.
