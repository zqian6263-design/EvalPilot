# P4 验收记录

Status: **PASSED**

Date: 2026-09-14

Final preflight commit: `31c23ebe544c44d21dbe8cd0dad745cac149b8bf`

## Third-party MCP retrospective

Command:

```powershell
pwsh -NoProfile -File .\scripts\p4-mcp-retro-check.ps1
```

Result: exit code `0`, `P4 MCP retrospective OK`.

- Regression run: `d3026200-718e-4bb3-9a2c-03bd34582590`
- Same-version control run: `6cb0a78a-2f34-4742-9310-523e3ad0b27c`
- Investigation: `7c24d488-d891-4a10-a296-5ab7d21817a9`
- Matched scenarios: `6`
- Regressions: `3`
- Stable controls: `3`
- Persisted SUT traces: `12`
- Mean difference: `-0.25`
- Paired CI: `[-0.4167, -0.0833]`
- Counterfactual replays: `3`, all `root_cause`, all **measured** — `3` persisted
  HTTP replay traces carrying `intervention=mcp_v2_error_path_enabled`, and
  rationales reading `Replayed '…' under 'mcp_v2_error_path_enabled': score 0.50
  -> 1.00` (the fallback's wording is "is predicted to restore …")
- Decision: `BLOCK / CRITICAL`

Detected regressions:

- `protocol-error-channel`
- `protocol-error-code`
- `protocol-error-data`

Counterfactual results (measured through the HTTP adapter):

| Scenario | Intervention | Original | Replay | Verdict |
|---|---|---:|---:|---|
| `protocol-error-channel` | `mcp_v2_error_path_enabled` | 0.50 | 1.00 | `root_cause` |
| `protocol-error-code` | `mcp_v2_error_path_enabled` | 0.50 | 1.00 | `root_cause` |
| `protocol-error-data` | `mcp_v2_error_path_enabled` | 0.50 | 1.00 | `root_cause` |

Evidence: `docs/P4_MCP_RESULT.json`.

### Correction (2026-09-14, P5 external-intervention fix)

This record previously listed the three replays as `0.50 -> 0.95` and described
them as counterfactual replays. They were the deterministic fallback's
**predictions**: the intervention name is not in the engine's built-in
`Intervention` enum, so the engine raised before executing anything and the
provider fell back. The run's own evidence confirms it — the before/after probe
of `.runtime/p4-mcp-retro-6fc079597bed45fc8deb265c03317d0e/evalpilot.db` shows
`0` trace rows carrying an intervention and rationales reading "is predicted to
restore the scenario to 0.95".

After the fix the same command reports `0.50 -> 1.00`, `3` measured HTTP replay
traces, and rationales reading "Replayed ... score 0.50 -> 1.00".
`scripts/p4-mcp-retro-check.ps1` now fails unless at least three measured replays
are present, and `backend/tests/test_acceptance_evidence.py` reads this file and
rejects any counterfactual whose recorded rationale is a prediction, so the
distinction cannot silently regress again.

See also: `docs/P3_VERIFICATION.md` carries the same correction for the browser
adapter, where the replay still does not execute (separate, unfixed cause).

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
- Verified preflight commit: `31c23eb`
- Archive SHA-256: `968801ea71978e55171febbe1cc4d2a23b11aff922a468df62833f3649985b69`
- Backend after clean extraction: healthy
- Frontend after clean extraction: healthy

The installation test verifies the outer archive checksum, every file in
`MANIFEST.sha256`, extraction into a new directory, creation of a new Python
virtual environment, frontend dependency installation, and both service health
endpoints. Evidence: `docs/P4_INSTALL_RESULT.json`.
## Repository-wide checks

- Backend: `402` tests collected; full suite exit code `0`; `1` skipped.
- Frontend: `153 / 153` Vitest tests passed.
- Frontend typecheck and production build: passed.
- Public site checker: passed.

## Boundaries

- The MCP adapter evaluates a public behavioral boundary between two published
  releases; it does not claim every v1 application is vulnerable.
- The v1 issue was closed rather than backported because v2 already implements
  the correct protocol-error path.
- The current machine has no Docker or Podman daemon. The verified delivery is a
  checksummed source archive with a one-command Python launcher, not an
  unverified container image.
