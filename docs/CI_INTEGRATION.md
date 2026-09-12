# CI Release Gate

`GET /api/runs/{run_id}/gate` turns a completed evaluation into a CI-friendly
decision:

| Decision | Exit code | Meaning |
|---|---:|---|
| `allow` | 0 | No regression detected |
| `review` | 1 | Localized regression needs human review |
| `block` | 2 | Confirmed regression; do not ship |

Example:

```powershell
.\scripts\ci-gate.ps1 -RunId 558922af-a02d-4c07-a0af-e9a45e2ab58b
```

PowerShell exits with the returned code, so the same command can be used in a
release job. A GitHub Actions step can call the endpoint directly:

```yaml
- name: EvalPilot release gate
  shell: pwsh
  run: ./scripts/ci-gate.ps1 -RunId ${{ inputs.run_id }}
```

The decision is derived only from measured report metrics. The LLM cannot
override the exit code.
