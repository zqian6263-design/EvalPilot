# EvalPilot Release Audit

Date: 2026-09-12  
Purpose: freeze a defensible demo build before recording the competition video.

## Decision

The product is engineering-complete enough to enter the final pre-recording
freeze. The remaining work is presentation and external market evidence, not
additional product breadth.

## Gate status

| Gate | Status | Evidence |
|---|---|---|
| Frontend tests | Pass | 152/152 |
| TypeScript | Pass | `npm run typecheck` |
| Production build | Pass | `npm run build` |
| Backend tests | Pass | full pytest suite |
| Real HTTP E2E | Pass | 31/31 |
| Autonomous investigation E2E | Pass | V2 E2E |
| Clean worktree install/start/E2E | Pass | separate checkout `EvalPilot-clean`, ports 8100/5273, 31/31 |
| Live DeepSeek runtime | Pass | persisted LLM steps and report rationale |
| Deliberate live failure fallback | Pass | invalid key -> HTTP 401 -> 2 fallback steps -> BLOCK/CRITICAL |
| Public claims aligned | Pass | current tool surface documented as kb_search/http_get/file_read |
| Reproducible run/investigation deep links | Pass | #console&run=<id> and #investigation&run=<id>&inv=<id> open recorded service data in seconds |
| Competition video | Pass | `release/EvalPilot-competition-demo-v2.mp4`, 1920x1080, 30fps, 2:28.97, Chinese narration, model-plan panel at 1:10-1:25 |
| CI release gate | Pass | GET /api/runs/{id}/gate and scripts/ci-gate.ps1 return exit codes 0/1/2 |

## Verified now

- The current runtime registers exactly `kb_search`, `http_get`, and `file_read`.
- The Python sandbox is a disabled placeholder with no execution implementation.
- Browser execution is roadmap work and is no longer presented as implemented.
- Deterministic/offline mode remains available without an API key.
- Live mode uses DeepSeek V4 Pro and falls back with an explicit reason on
  transport failure.
- LLM output cannot override measured scores, counterfactuals, risk, or decision.

## Clean-worktree acceptance record

A detached worktree was created at `D:\z工程文件\EvalPilot-clean` from the
release-gate commit. It created its own Python virtual environment and npm
dependencies, started on alternate ports, and completed:

```text
E2E OK - 31 checks passed.
```

Screenshot artifact:

```text
D:\z工程文件\EvalPilot-clean\.runtime\clean-machine-console.png
```

This is still the same physical machine, so it proves path/dependency
independence but not a second physical host.

## Fallback rehearsal record

An invalid DeepSeek key was configured deliberately. The investigation
completed, recorded two fallback steps, and preserved the measured decision:

```text
fallback_reason: hypotheses call failed:
  LLMTransportError: LLM endpoint api.deepseek.com returned HTTP 401
decision: block
risk: critical
```

## Remaining before submission

- Public MP4: https://n.uguu.se/AFnrdUSF.mp4; backup: https://gofile.io/d/TPBMWhtR. Verify in a logged-out browser and migrate to a permanent platform if available.
- Submit the updated team description and detailed product description.
- Complete public-market and integration experiments; interviews are optional.

## Non-blocking improvements after the video

- CI/CD release gate and webhook integration.
- Browser execution tool.
- Human-in-the-loop approval and audit workflow.
- Token, latency, and cost measurement.
- Additional model providers.
- Human calibration of the LLM judge.
- Multi-tenant authentication and permissions.
