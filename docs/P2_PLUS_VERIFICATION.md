# P2+ Verification Record

Date: 2026-09-13

## Implemented

- Expanded counterfactual vocabulary with four OOD executable interventions.
- Controlled OOD behavior and measured replay in the public Haystack SUT.
- Real upstream Haystack 3.0.0 vs 3.1.1 comparison.
- Human-label Judge calibration harness and metric tests.

## Measured evidence

### OOD intervention execution

```text
cases: 4
root causes confirmed: 4
accuracy: 1.0
```

Result: `docs/OOD_REPLAY_RESULT.json`.

### Real upstream version comparison

```text
baseline: haystack-ai 3.0.0
candidate: haystack-ai 3.1.1
comparisons: 52
semantic mismatches: 0
status: pass
```

Result: `docs/UPSTREAM_VERSION_RESULT.json`.

### Judge calibration

- CSV protocol implemented.
- Metrics: MAE, bias, Pearson correlation, exact agreement.
- Tests: pass.
- Actual human labels remain external and are not fabricated.

## Regression status

- Full backend suite: pass.
- Public Haystack SUT E2E: pass.
- Existing 26-scenario baseline/candidate behavior: unchanged.
