# Competition Scorecard — Current Self-Assessment

**Date: 2026-09-12**

This is an internal estimate, not a judge score. It uses public evidence and
reproducible product artifacts; customer interviews are optional here and are
not treated as a prerequisite.

## Current estimate

| Criterion | Current | Target for finals | Main reason |
|---|---:|---:|---|
| Technical feasibility | 18/20 | 18+ | Product, tests, clean-worktree E2E, and fallback rehearsals pass |
| Market feasibility | 13/20 | 16+ | Paid category, public adoption, enforceable CI gate, public cross-domain workload, measured unit cost, and one-command deployment |
| Comprehensive innovation | 17/20 | 18 | Causal comparison and counterfactual replay are implemented; direct comparison with a naive delta workflow remains |
| AI/LLM integration | 18/20 | 19 | DeepSeek V4 Pro live mode, fallback, token usage, and measured unit cost are verified |
| Track dimension | 17/20 | 18 | Autonomous loop, report, deterministic deep links, and 2:29 demo video exist |
| **Total** | **83/100** | **86-90** | Strong engineering, integration, public workload evidence, and measured economics |

## Verified evidence

- Frontend: 153 tests pass.
- Frontend: TypeScript check and production build pass.
- Backend: release-gate contract tests pass; full suite is the standing gate.
- Real HTTP E2E: 31/31 passes, including from an independent clean worktree.
- Autonomous investigation E2E passes.
- Invalid model key: HTTP 401 produces recorded fallback steps while preserving
  the measured `BLOCK / CRITICAL` decision.
- DeepSeek V4 Pro live mode is verified.
- Run and investigation deep links reopen recorded service data in seconds.
- CI gate returns `allow=0`, `review=1`, `block=2`.
- Competition video is rendered at `release/EvalPilot-competition-demo.mp4`.

## Technical feasibility — 18/20

### Strong

- One-command start and stop.
- Persistent API, event flow, evidence links, calculations, and report.
- Deterministic/offline fallback prevents a dead demo.
- Clean worktree installed dependencies and passed the 31-check E2E.
- Current runtime tools are explicitly bounded: `kb_search`, `http_get`,
  `file_read`.

### Remaining

- Measure a full run's latency and token cost.
- Decide whether to implement browser execution after the competition.
- Run the clean setup on a second physical host if available.

## Market feasibility — 11/20

### Strong

- Public paid products establish willingness to pay for this category.
- Public repository adoption shows developer demand and distribution channels.
- EvalPilot has a clear wedge: release decision, not another observability dashboard.
- `GET /api/runs/{run_id}/gate` provides a real CI integration.
- Exit codes `0/1/2` let a pipeline enforce the result automatically.
- Pricing and revenue motions are explicit: release audit, team subscription,
  enterprise self-host.
- The unit-economics formula and required measurements are documented.

### Remaining

- Repeat the public workload on a second external dataset or application.
- Validate pricing willingness through public adoption or a paid pilot.
- Measure compute and storage cost in addition to model tokens.

Customer interviews are optional support, not a required gate.

## Comprehensive innovation — 16/20

### Strong

- Matched cases and 18 controls separate version change from test difficulty.
- Paired uncertainty is visible.
- Counterfactual replay identifies which change caused each failure.
- Historical incidents become reusable regression memory.

### Remaining

- Publish the completed naive-delta vs EvalPilot head-to-head artifact.
- State the minimum matched-case count needed for the aggregate verdict.
- Run a retrospective on another workload, public or private.

## AI/LLM integration — 17/20

### Strong

- Explicit model roles: hypotheses, explanation, and report rationale.
- Structured JSON validation and deterministic fallback exist.
- The model cannot override evidence, scores, counterfactuals, or the verdict.
- DeepSeek V4 Pro is verified in live mode.
- The fallback path is verified with a deliberate HTTP 401.

### Remaining

- Extend the verified token measurement with storage/compute cost inputs.
- Add a second OpenAI-compatible provider proof.
- Disclose the limits of LLM judging against deterministic checks.

## Track dimension — 17/20

### Strong

- Natural-language objective.
- Autonomous planning, memory recall, probing, replay, decision, and report.
- Verifiable deliverables: report, gate exit code, run id, evidence ids.
- The demo video is 2:28.9, Chinese, 1080p, and uses a real live investigation.
- Deep links reproduce the exact recorded run and investigation.

### Remaining

- Upload the video publicly and verify it in a logged-out browser.
- Add the final team and product descriptions to the competition form.

## Highest-value next actions

1. Upload and verify the finished competition video.
2. Run the naive-delta vs EvalPilot comparison.
3. Measure live-run token, latency, and unit cost.
4. Exercise a public open-source assistant workload.
5. Package a one-command deployment path.
