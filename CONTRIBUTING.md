# Contributing

## Local checks

Before opening a pull request, run:

```powershell
.\scripts\test-backend.ps1
.\scripts\test-frontend.ps1
.\scripts\e2e-check.ps1
.\scripts\v2-e2e-check.ps1
.\scripts\sut-e2e-check.ps1
```

## Product invariants

- Deterministic scoring remains authoritative.
- Model output cannot invent evidence, scores, or release verdicts.
- Every finding cites persisted evidence.
- A SUT outage must fail loudly rather than fall back to the mock executor.
- Webhook and API secrets are never persisted or returned.

## Pull requests

Keep changes scoped and include one runnable verification command. For changes to
the evaluation engine, add a test that proves both the measured result and the
failure behavior.
