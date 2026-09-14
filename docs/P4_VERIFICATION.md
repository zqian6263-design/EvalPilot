# P4 验收记录

Status: **PASSED**

Date: 2026-09-14

Verified implementation commit: `484963d9879517558f0c3314466bfb7d9ad1d292`

## Third-party MCP retrospective

Command:

```powershell
pwsh -NoProfile -File .\scripts\p4-mcp-retro-check.ps1
```

Result: exit code `0`, `P4 MCP retrospective OK`.

- Regression run: `0fd86f01-9c68-4bab-8bc0-8feb48d035bf`
- Same-version control run: `ef700f32-5a75-4bd2-8ab1-aeaf5c459f0a`
- Investigation: `2f4cc1b0-95b3-4b31-a64c-a9626a7bcb5d`
- Matched scenarios: `6`
- Regressions: `3`
- Stable controls: `3`
- Persisted SUT traces: `12`
- Mean difference: `-0.25`
- Paired CI: `[-0.4167, -0.0833]`
- Counterfactual replays: `3`, all `root_cause`
- Decision: `BLOCK / CRITICAL`

Detected regressions:

- `protocol-error-channel`
- `protocol-error-code`
- `protocol-error-data`

Counterfactual results:

| Scenario | Intervention | Original | Replay | Verdict |
|---|---|---:|---:|---|
| `protocol-error-channel` | `mcp_v2_error_path_enabled` | 0.50 | 0.95 | `root_cause` |
| `protocol-error-code` | `mcp_v2_error_path_enabled` | 0.50 | 0.95 | `root_cause` |
| `protocol-error-data` | `mcp_v2_error_path_enabled` | 0.50 | 0.95 | `root_cause` |

Evidence: `docs/P4_MCP_RESULT.json`.

## Installable release

Build command:

```powershell
pwsh -NoProfile -File .\scripts\build-release.ps1 -Version evalpilot-p4-20260914
```

Clean installation command:

```powershell
pwsh -NoProfile -File .\scripts\install-check.ps1 -ArchivePath .\dist\evalpilot-evalpilot-p4-20260914.zip
```

Result: exit code `0`, `P4 release installation OK`.

- Release: `evalpilot-p4-20260914`
- Verified commit: `484963d`
- Archive SHA-256: `2e74746684262ac4a2274e21eaccc84ca820f6be8b161a01541cc716e7fd8271`
- Backend after clean extraction: healthy
- Frontend after clean extraction: healthy

The installation test verifies the outer archive checksum, every file in
`MANIFEST.sha256`, extraction into a new directory, creation of a new Python
virtual environment, frontend dependency installation, and both service health
endpoints. Evidence: `docs/P4_INSTALL_RESULT.json`.

## Boundaries

- The MCP adapter evaluates a public behavioral boundary between two published
  releases; it does not claim every v1 application is vulnerable.
- The v1 issue was closed rather than backported because v2 already implements
  the correct protocol-error path.
- The current machine has no Docker or Podman daemon. The verified delivery is a
  checksummed source archive with a one-command Python launcher, not an
  unverified container image.
