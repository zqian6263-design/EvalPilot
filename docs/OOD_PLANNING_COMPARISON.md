# OOD Planning Comparison

Date: 2026-09-13

## Question

Does model planning add value when the failure signature is outside the
deterministic release rules?

## Benchmark design

The benchmark contains six planning-only cases:

| Case | OOD failure | Ground-truth intervention |
|---|---|---|
| `multi_doc_retrieval_drop` | retrieval `top_k` changed from 2 to 1 | `retrieval_top_k_restored` |
| `unicode_normalization` | full-width Chinese query stops retrieving | `unicode_normalization_restored` |
| `memory_scope_cross_talk` | tenant A receives tenant B memory | `memory_scope_restored` |
| `tool_timeout_stale_cache` | failed tool result is cached | `cache_bypass_enabled` |
| `mandatory_clause_drop` | known compression regression | `compression_disabled` |
| `credential_leak` | known guard regression | `security_guard_enabled` |

The deterministic planner can only emit its two production interventions:
`compression_disabled` and `security_guard_enabled`. The planner comparison is
therefore intentionally asymmetric: it measures what happens when the failure
is outside the closed rule vocabulary.

## Result

| Planner | Correct | Accuracy | Calls | Tokens |
|---|---:|---:|---:|---:|
| Deterministic production rules | 2/6 | 33.3% | 0 | 0 |
| DeepSeek V4 Pro | 6/6 | 100% | 1 | 1,359 |

Full result: `docs/OOD_PLANNING_RESULT.json`.

## Interpretation

The result supports the product design:

- deterministic rules remain the safe default for known failures;
- model planning adds value on unfamiliar, cross-system failure signatures;
- every proposed intervention still requires an executable allowlist and a
  measured replay before it can affect a release decision.

## Measured replay

The four OOD interventions are now implemented in the public Haystack SUT and
checked through the HTTP contract. A measured replay check confirms 4/4 root
causes:

```text
baseline pass -> candidate fail -> intervention pass
```

Full result: `docs/OOD_REPLAY_RESULT.json`.

This is a controlled cross-system benchmark, not a claim that upstream Haystack
shipped those defects. The measured executor support is production code; the
specific OOD faults are benchmark fixtures.

## Reproduce

```powershell
$env:PYTHONPATH = (Resolve-Path backend)
.venv\Scripts\python.exe backend\scripts\planning_ood_check.py --live `
  --output docs\OOD_PLANNING_RESULT.json
```
