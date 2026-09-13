# P2 第二模型供应商验证

Date: 2026-09-13

## Goal

Verify that EvalPilot can switch model providers without changing product code, and measure the quality, latency, token usage, cost, and failure behaviour of a second provider.

## Provider

- Provider: Zhipu BigModel
- Base URL: `https://open.bigmodel.cn/api/paas/v4`
- Model: `glm-4.7`
- Protocol: OpenAI-compatible Chat Completions
- Pricing source: https://open.bigmodel.cn/pricing
- Pricing used: input `3 CNY / M tokens`, output `14 CNY / M tokens` for the tested 0-32K / output-over-200-token tier, as published on 2026-09-13

No code branch or adapter change was needed between DeepSeek and GLM. The runtime switches with environment variables only.

## 1. OOD planning comparison

The same six OOD planning cases were used.

| Planner | Correct | Accuracy | Prompt tokens | Completion tokens | Total tokens |
|---|---:|---:|---:|---:|---:|
| Deterministic rules | 2/6 | 33.3% | 0 | 0 | 0 |
| DeepSeek V4 Pro recorded result | 6/6 | 100% | not split in old artifact | not split in old artifact | 1,359 |
| GLM-4.7 live result | 6/6 | 100% | 308 | 2,316 | 2,624 |

GLM selected all six ground-truth interventions:

```text
multi_doc_retrieval_drop -> retrieval_top_k_restored
unicode_normalization -> unicode_normalization_restored
memory_scope_cross_talk -> memory_scope_restored
tool_timeout_stale_cache -> cache_bypass_enabled
mandatory_clause_drop -> compression_disabled
credential_leak -> security_guard_enabled
```

GLM model cost for this call at published rates:

```text
(308 * 3 + 2316 * 14) / 1,000,000 = 0.033348 CNY
```

The DeepSeek artifact records total tokens but not the prompt/completion split, so an exact DeepSeek OOD-call cost cannot be recomputed from that file without inventing data.

## 2. Full live evaluation with an explicit budget

The standard 26-scenario workload and 8 measured counterfactuals were used with:

```text
EVALPILOT_LLM_TIMEOUT_SECONDS=240
EVALPILOT_JUDGE_MAX_CALLS=4
EVALPILOT_JUDGE_MAX_TOKENS=20000
```

Result:

```text
model: glm-4.7
matched scenarios: 26
decision: BLOCK / CRITICAL
counterfactuals: 8
LLM steps: 4
model-guided plan steps: 1
Judge calls: 4
Judge failures: 0
Judge skipped by budget: 48
run time: 177.00s
investigation time: 127.33s
```

Token usage:

```text
Judge:         1,134 prompt + 8,644 completion = 9,778
Investigation: 5,864 prompt + 9,963 completion = 15,827
Total:         6,998 prompt + 18,607 completion = 25,605
```

Model cost at the published GLM-4.7 tier:

```text
(6,998 * 3 + 18,607 * 14) / 1,000,000 = 0.281492 CNY
USD at 7.2 CNY/USD = 0.039096
```

Using the existing local compute assumption of `$0.10/hour` and the recorded 304.33 seconds gives `$0.008453`; the stored footprint cost is below `$0.000006`. Estimated total for this budgeted run is therefore about **`$0.04756`**, including the same model, compute, and storage categories used by the earlier cost model.

The earlier DeepSeek full run used 52 Judge calls and cost `$0.264697` total. That is not an apples-to-apples budget comparison: GLM skipped 48 Judge calls under the explicit four-call budget. What is directly comparable is that:

- both providers produced the same measured release decision;
- GLM produced a valid model-guided plan and evidence-grounded rationale;
- GLM's blended model-only cost was `$0.039096 / 0.025605M = $1.527/M tokens` in this run, versus the earlier DeepSeek model-only reference of approximately `$3.196/M tokens`;
- the comparison is reference evidence, not a universal price claim.

## 3. Failure and fallback behaviour

The first 26-scenario attempt used a 90-second timeout. One hypothesis call timed out and one rationale call returned invalid JSON. EvalPilot:

- recorded both fallback reasons;
- used deterministic investigation logic;
- preserved `BLOCK / CRITICAL`;
- did not let model failure alter measured scores or the release verdict.

After increasing the timeout to 240 seconds, the same provider completed the model hypotheses, persisted a model-guided replay plan, and produced a model rationale. This is the expected substitutability property: timeout is an operational setting, not a correctness dependency.

## Evidence

- `docs/ZHIPU_OOD_PLANNING_RESULT.json`
- `docs/ZHIPU_LIVE_RESULT.json`
- `docs/OOD_PLANNING_RESULT.json`
- `docs/P0_VERIFICATION.md`

## Reproduce

Configure the local ignored `.env` with placeholder-safe values documented in `docs/ZHIPU_SETUP.md`, start EvalPilot, then run:

```powershell
.\scripts\live-llm-check.ps1 -BackendPort 8141 -TimeoutSeconds 900
```

For the OOD planning benchmark:

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\planning_ood_check.py --live --output .runtime\zhipu-ood-planning.json
```

## Limits

- The GLM run used a four-call Judge budget, so it does not measure an unbudgeted 52-call run.
- Zhipu pricing can change and the account may have separate plan credits; the cost here uses public per-token rates captured on the test date.
- The model providers use different tokenizers and reasoning-output styles, so token and latency comparisons are directional rather than hardware-normalized.