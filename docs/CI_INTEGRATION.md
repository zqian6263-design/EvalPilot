# CI/CD Integration

EvalPilot is a release gate, not another dashboard. The main integration path is:

```text
run completed -> GET /api/runs/{run_id}/gate -> exit code 0 / 1 / 2
```

## Decision contract

| Exit code | Decision | Meaning |
|---:|---|---|
| `0` | `allow` | No regression detected. |
| `1` | `review` | Localized movement requires human review. |
| `2` | `block` | A confirmed or hard per-case regression blocks release. |

## Machine artifacts

- `GET /api/runs/{run_id}/gate`: compact decision JSON.
- `GET /api/runs/{run_id}/report`: full evidence report.
- `GET /api/runs/{run_id}/junit`: JUnit XML for test reporters.
- `GET /api/runs/{run_id}/sarif`: SARIF 2.1.0 for code scanning.
- `GET /api/runs/{run_id}/report.md`: human-readable report.

Export all artifacts locally:

```powershell
.\scripts\export-ci-artifacts.ps1 -RunId <run-id>
```

The script writes `gate.json`, `junit.xml`, `results.sarif`, `report.json`, and
`summary.md` under `.runtime/ci-export`, then exits with the gate code.

## GitHub Actions

The repository includes a workflow template at
`.github/workflows/evalpilot-release-gate.yml`.

It supports:

- manual dispatch with `api_base` and `run_id`;
- repository dispatch with `api_base`, `run_id`, and optional `pr_number`;
- artifact upload;
- SARIF upload;
- sticky PR summary via `gh pr comment`;
- final enforcement using the EvalPilot exit code.

The workflow is a template because a self-hosted EvalPilot endpoint must be
reachable from the runner. Never place an API key in the repository; use the
runner environment or an OIDC/secret manager integration.

## GitLab CI

```yaml
evalpilot:
  image: alpine:3.20
  script:
    - apk add --no-cache curl jq
    - curl -fsS "$EVALPILOT_API_BASE/runs/$EVALPILOT_RUN_ID/gate" -o gate.json
    - test "$(jq -r .exit_code gate.json)" = "0"
  artifacts:
    when: always
    paths:
      - gate.json
```

For GitLab, map exit code `2` to a failed job and preserve `report.json` and
`junit.xml` as artifacts.
