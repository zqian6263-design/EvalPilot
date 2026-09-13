# Model Planning vs Deterministic Planning

Date: 2026-09-13

## Question

Does giving DeepSeek V4 Pro control over counterfactual experiment selection
improve planning quality enough to justify the model cost?

## Benchmark

The comparison uses the eight controlled enterprise-support regressions whose
ground truth is declared by the fixture:

- a dropped mandatory clause is repaired by `compression_disabled`;
- a credential disclosure is repaired by `security_guard_enabled`.

The deterministic planner uses the published incident/guard/failure rules. The
model plan is the actual DeepSeek V4 Pro output recorded from investigation
`d36ccc30-57b5-4368-a96f-56b8024431d6`; it is replayed offline so the result is
reproducible and consumes no additional API credits.

## Results

| Metric | Deterministic | DeepSeek V4 Pro |
|---|---:|---:|
| Correct interventions | 8/8 | 8/8 |
| Accuracy | 100% | 100% |
| Schema/allowlist validity | 100% | 100% |
| Missing or unexpected scenarios | 0 | 0 |
| Per-experiment rationale coverage | 0% | 100% |
| LLM calls | 0 | 1 |
| Model tokens | 0 | 6,651 |

Both planners selected the same eight correct interventions. Every selected
experiment was subsequently executed and measured by the counterfactual engine,
so the model did not gain authority over scores or the release verdict.

The implementation also now treats the hypothesis kind as a per-item sanitizer
concern, not a whole-response schema failure. A single unsupported hypothesis
kind is discarded without throwing away a valid replay plan; this was observed
in a later live call and fixed before the final acceptance run.

## Interpretation

On this closed and well-instrumented benchmark, the deterministic planner wins
on cost-adjusted quality: it ties the model on decision accuracy while using no
model call. The model-guided path is valuable as a bounded extensibility path:
it produces a human-readable rationale per experiment and may generalize better
when future workloads contain failure signatures the deterministic rules do not
know.

The correct product decision is therefore:

- keep deterministic planning as the default and fallback;
- enable model planning only in live mode;
- validate every choice against the executable intervention allowlist;
- always measure the chosen experiment before treating it as causal.

## Reproduce

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\planning_quality_check.py
```
