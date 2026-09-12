# Competition Scorecard — Current Self-Assessment

**Date: 2026-09-12**

This is an internal estimate, not a judge score. It is intentionally stricter
than the pitch: a claim enters this document only when the repository contains a
reproducible artifact for it.

## Current estimate

| Criterion | Current | Target for finals | Main reason |
|---|---:|---:|---|
| Technical feasibility | 18/20 | 18+ | Product, tests, live mode, and E2E are working |
| Market feasibility | 9/20 | 13+ | No external interviews, design partner, pilot, or validated pricing |
| Comprehensive innovation | 16/20 | 17+ | Causal comparison and counterfactual replay are real, but not yet compared head-to-head against a simple aggregate-delta workflow |
| AI/LLM integration | 17/20 | 18 | DeepSeek live path is verified; token cost, failure rehearsal, and judge calibration remain |
| Track dimension | 16/20 | 17+ | Autonomous loop and report exist; public video and clean-machine proof are missing |
| **Total** | **76/100** | **84-88** | Strong engineering, incomplete validation and submission evidence |

## Verified evidence

- Frontend: 152 tests pass.
- Frontend: TypeScript check and production build pass.
- Backend: full pytest suite passes.
- Real HTTP E2E: 31/31 checks pass.
- Autonomous investigation E2E: passes.
- Live runtime: DeepSeek V4 Pro configured and exercised with persisted
  LLM-backed planning and report rationale.
- Current runtime tools: `kb_search`, `http_get`, `file_read`.
- Deterministic/offline mode remains available without an API key.
- Current UI is Chinese-first and uses a professional light console.

## Technical feasibility — 18/20

### Strong

- One-command start and stop.
- Real API, persistence, event flow, evidence links, calculations, and report.
- Deterministic fallback prevents a dead demo when the model or network fails.
- The earlier broken typecheck was repaired without generating stray `.js`
  files.

### Remaining

- Clean-machine acceptance has not been completed by a second operator.
- Live fallback has not yet been recorded as an explicit negative-path proof.
- A full run must document latency and token cost.

## Market feasibility — 9/20

### Strong

- Clear ICP, buyer, trigger, alternative, pricing hypothesis, and ROI model.
- The product solves a recurring release decision, not a one-off research task.

### Blocking

- External interviews: 0.
- Design partners: 0.
- Pilots: 0.
- Paying customers: 0.
- Validated pricing and ROI: 0.

The next market action is not more writing. It is 5-10 real problem interviews,
followed by one historical-release retrospective if a design partner is found.

## Comprehensive innovation — 16/20

### Strong

- Matched cases and controls separate version change from test difficulty.
- Paired uncertainty is visible rather than hidden.
- Counterfactual replay identifies which change caused each failure.
- Historical incidents become regression memory.

### Remaining

- Publish a direct comparison against a naive aggregate-score workflow.
- State the minimum matched-case count needed for the aggregate verdict.
- Run the retrospective experiment on a real, already-shipped release.

## AI/LLM integration — 17/20

### Strong

- The model has explicit roles: risk hypotheses, explanation, and report rationale.
- Structured JSON validation and deterministic fallback exist.
- The model cannot overwrite evidence, scores, counterfactuals, or the verdict.
- DeepSeek V4 Pro live mode is working.

### Remaining

- Measure token usage, cost, and latency for one complete investigation.
- Record one forced failure showing the fallback reason.
- Calibrate or at least disclose the limits of LLM judging against deterministic
  checks.

## Track dimension — 16/20

### Strong

- Natural-language objective.
- Autonomous planning, memory recall, probing, replay, decision, and report.
- Verifiable deliverable with evidence ids and measured outcomes.
- A clear `BLOCK / REVIEW / ALLOW` output.

### Remaining

- Record the required 2-3 minute public demo video.
- Produce clean-start and deep-link evidence.
- Present the live model badge and the deterministic fallback honestly.

## Pre-video checklist

- [ ] All public claims match the implemented tool surface.
- [ ] Clean-machine setup passes.
- [ ] `#console&demo` completes without repair.
- [ ] `#investigation&demo` reaches BLOCK and shows counterfactual evidence.
- [ ] Report downloads successfully.
- [ ] Live and deterministic modes are both visible and labelled correctly.
- [ ] Live failure fallback is rehearsed.
- [ ] Demo narrative fits 2-3 minutes after editing.

## Highest-value next actions

1. Record the video.
2. Conduct 5-10 real customer interviews and update the market score.
3. Publish the naive-delta vs EvalPilot comparison.
4. Measure one live investigation's latency and token cost.
5. Run the clean-machine acceptance.
