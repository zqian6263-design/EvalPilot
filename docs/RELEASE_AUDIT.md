# EvalPilot Release Audit

Date: 2026-09-12  
Purpose: freeze a defensible demo build before recording the competition video.

## Decision

The product is engineering-complete enough to enter a short release-gate pass.
It is **not** feature-complete, but no additional product breadth is required
before recording. The next work must remove demo risks and align every public
claim with what a judge can verify.

## Verified now

- Frontend: 152 tests pass.
- Frontend: TypeScript check passes; production build passes.
- Backend: full pytest suite passes.
- Real HTTP end-to-end: 31/31 checks pass.
- Autonomous investigation end-to-end: passes.
- DeepSeek V4 Pro live runtime: verified with persisted LLM-backed steps,
  measured counterfactual results, and a model rationale in the report.
- Current runtime tools: `kb_search`, `http_get`, `file_read`.
- Deterministic/offline mode remains available without an API key.
- The UI labels deterministic and live sources and does not let the model
  override measured verdicts.

## Release blockers

### P0-1: Public claims exceed the implemented product

`PRODUCT.md`, `COMPETITION_PITCH.md`, and `SPEC.md` still describe browser or
sandboxed Python execution as part of the working demo. The current runtime does
not register a browser or Python tool. Public material must say:

- implemented: knowledge-base search, allowlisted HTTP, file read;
- roadmap: browser execution and sandboxed code.

### P0-2: Stale self-assessment

`COMPETITION_SCORECARD.md` still reports 67/100, 150 tests, a broken typecheck,
and live mode as unexercised. Those statements are no longer true. A judge must
not receive contradictory submission materials.

### P0-3: Video path not frozen

The recording must use one deterministic main path plus a clearly visible live
LLM badge. Pre-recorded live model output is acceptable only when its artifact
is real and the video states that it is a recorded live run.

### P0-4: Clean-machine proof missing

The product has not yet been exercised from a clean checkout on a second
machine. Before recording, run the setup and acceptance scripts from a fresh
shell and record the transcript.

### P0-5: Live fallback needs one negative-path rehearsal

Record one deliberate live failure showing the deterministic fallback and its
visible reason. This protects the live demo against network or API instability.

## Non-blocking improvements after the video

- CI/CD release gate and webhook integration.
- Browser execution tool.
- Human-in-the-loop approval and audit workflow.
- Token, latency, and cost measurement.
- Additional model providers.
- Human calibration of the LLM judge.
- Multi-tenant authentication and permissions.

## Recording gate

Record only when all answers are yes:

- `#console&demo` reaches a live run and the final verdict without manual repair.
- `#investigation&demo` reaches BLOCK and exposes the counterfactual evidence.
- The report downloads successfully.
- The runtime badge is visible and truthful.
- Offline mode still completes the full demo.
- The demo fits a 2-3 minute narrative after editing.
- No public document claims a tool or result that the repository cannot prove.

## Next actions

1. Correct the stale product and competition documents.
2. Run the clean-machine acceptance checklist.
3. Rehearse the live failure fallback.
4. Freeze the demo build and record the video.
5. Perform real market interviews in parallel; do not fabricate traction.
