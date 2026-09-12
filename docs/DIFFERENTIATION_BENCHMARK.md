# Differentiation Benchmark

Date: 2026-09-12

## Question

Why is a matched-control release gate different from a raw pass-rate delta?

## Public SQuAD workload

Both approaches see the same 16 public rows:

| Method | Output |
|---|---|
| Naive pass-rate delta | `100.00% -> 68.75%`, says a regression exists |
| EvalPilot | 16 matched rows, 11 controls, mean delta `-0.3125`, 95% CI `[-0.5625, -0.1250]`, confidence `98.59%` |

The naive result raises a flag. EvalPilot additionally states whether the
paired interval clears the threshold and what the comparison's uncertainty is.

## Enterprise support workload

The bundled product run provides the second side of the comparison:

| Method | Output |
|---|---|
| Naive pass-rate delta | `100% -> 69.23%` |
| EvalPilot | 26 matched scenarios, 18 controls, 8 findings, root-cause replay, BLOCK decision |

EvalPilot goes beyond the score delta by:

1. linking every finding to evidence ids;
2. distinguishing aggregate confirmation from localized failures;
3. replaying each suspect intervention;
4. producing a machine-enforceable release gate.

## Why this matters commercially

The buyer is not paying for another percentage. The buyer is paying for a
defensible release decision, a root-cause explanation, and a gate that can stop
an unsafe deployment automatically.
