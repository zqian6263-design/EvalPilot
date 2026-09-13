# P1 公开未知故障应用回顾性诊断

Date: 2026-09-13

## Public application

- Project: `mem0ai/mem0`
- Package: `mem0ai`
- Published baseline: `3.1.1` (2026-07-22)
- Published candidate: `3.1.0` (2026-07-13)
- Public issue: https://github.com/mem0ai/mem0/issues/6342
- Public fix PR: https://github.com/mem0ai/mem0/pull/6343
- License: Apache-2.0

The issue reports a TypeScript OSS memory regression: caller-supplied `metadata` passed to `memory.update()` can overwrite or inject `user_id`, `agent_id`, `run_id`, or `actor_id`. Those fields scope `search()`, `getAll()`, and `deleteAll()`, so the write can silently move a memory to another tenant or grant it a scope it never had.

## Why this is a valid retrospective

- Both revisions are ordinary public npm releases, not locally patched defects.
- The failure mechanism is documented in a public issue and fixed in a public PR.
- EvalPilot receives a workload manifest and the two version labels; it does not receive a precomputed list of failing scenarios.
- The evaluator plans the same six scenarios for both versions and discovers regressions from measured answers.
- The workload includes three adversarial identity cases and three controls: ordinary metadata update, same-tenant update, and unmodified run scope.
- The public fix is used only as ground truth after the run to check whether the discovered failure and replay intervention match reality.

## Execution model

The HTTP SUT imports the unmodified packages:

```text
mem0ai@3.1.0
mem0ai@3.1.1
```

A deterministic local OpenAI-compatible endpoint supplies embeddings and a minimal chat response. No external model, API key, or customer data is used. For the replay intervention `identity_metadata_stripped`, the adapter removes identity keys from caller metadata before invoking `Memory.update()`, matching the public fix described in PR #6343.

The EvalPilot backend is started with:

```text
EVALPILOT_SUT_URL=http://127.0.0.1:8120
EVALPILOT_WORKLOAD_FILE=integrations/mem0_retro/workload.json
EVALPILOT_SUT_DISCOVERY=true
```

## Measured result

Negative control:

```text
baseline: mem0ai-3.1.1
candidate: mem0ai-3.1.1
regressions: 0
```

Retrospective comparison:

```text
baseline: mem0ai-3.1.1
candidate: mem0ai-3.1.0
matched scenarios: 6
regressed scenarios: 3
control scenarios: 3
mean difference: -0.4444
95% CI: [-0.7778, -0.1389]
release decision: BLOCK / CRITICAL
```

Discovered regressions:

- `tenant-metadata-overwrite`
- `tenant-identity-injection`
- `tenant-camelcase-alias-injection`

Counterfactual replay:

| Scenario | Intervention | Original | Replay | Verdict |
|---|---|---:|---:|---|
| `tenant-metadata-overwrite` | `identity_metadata_stripped` | 0.00 | 1.00 | `root_cause` |
| `tenant-identity-injection` | `identity_metadata_stripped` | 0.17 | 1.00 | `root_cause` |
| `tenant-camelcase-alias-injection` | `identity_metadata_stripped` | 0.17 | 1.00 | `root_cause` |

All three replays pass through the HTTP boundary and carry evidence ids. The release decision is `BLOCK / CRITICAL`.

## Reproduce

```powershell
.\scripts\p1-mem0-retro-check.ps1
```

The script:

1. installs the pinned public npm packages when needed;
2. starts the deterministic mem0 HTTP SUT;
3. starts EvalPilot with the external workload;
4. runs a same-version negative control;
5. runs the fixed-to-buggy retrospective;
6. starts autonomous investigation;
7. verifies three root-cause replays, evidence links, and `BLOCK / CRITICAL`;
8. writes `summary.json` and the Markdown investigation report under `.runtime/p1-mem0-retro-*`.

## Evidence files

- `docs/MEM0_RETRO_RESULT.json`
- `docs/P1_MEM0_INVESTIGATION_REPORT.md`
- `integrations/mem0_retro/workload.json`
- `integrations/mem0_retro/server.mjs`
- `scripts/p1-mem0-retro-check.ps1`

## Limits

- This is a retrospective, so the public fix is known before the experiment. The system does not receive the failing-scenario list, but the workload author knows the intended intervention.
- The deterministic adapter tests identity-scope behavior through `Memory.add`, `Memory.update`, and `Memory.getAll`; it does not reproduce every vector-store backend or production concurrency condition.
- The result demonstrates detection on a real published revision gap. It does not prove that all unknown regressions in arbitrary applications will be found.