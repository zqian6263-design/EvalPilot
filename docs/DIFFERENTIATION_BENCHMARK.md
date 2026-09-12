# Differentiation Benchmark

Date: 2026-09-13

## Question

Why is a matched-control release gate different from a raw pass-rate delta?

## Public workloads

Both public datasets use 16 rows, five controlled regressions, and eleven
controls:

| Workload | Naive result | EvalPilot result |
|---|---|---|
| SQuAD | `100.00% -> 68.75%` | mean `-0.3125`, 95% CI `[-0.5625, -0.1250]`, confidence `98.59%` |
| HotpotQA | `100.00% -> 68.75%` | mean `-0.3125`, 95% CI `[-0.5625, -0.1250]`, confidence `98.59%` |

The naive result raises a flag. EvalPilot additionally states whether the paired
interval clears the threshold and what the comparison's uncertainty is.

## Enterprise support workload

| Method | Output |
|---|---|
| Naive pass-rate delta | `100% -> 69.23%` |
| EvalPilot | 26 matched scenarios, 18 controls, 8 findings, root-cause replay, BLOCK decision, CI exit code 2 |

EvalPilot goes beyond the score delta by linking findings to evidence, separating
aggregate confirmation from localized failures, replaying interventions, and
producing a machine-enforceable release gate.
