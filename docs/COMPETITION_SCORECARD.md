# Competition Scorecard — Current Self-Assessment

**Date: 2026-09-13**

This is an internal estimate, not a judge score. It uses public evidence and
reproducible product artifacts; customer interviews are optional here and are
not treated as a prerequisite.

## Current estimate

| Criterion | Current | Target for finals | Main reason |
|---|---:|---:|---|
| Technical feasibility | 19/20 | 19+ | Product, tests, external HTTP SUT E2E, offline replay, outage failure, and one-command deployment pass |
| Market feasibility | 15/20 | 17+ | Paid category, public adoption, enforceable CI gate, two public workloads, measured end-to-end cost, and one-command deployment |
| Comprehensive innovation | 17/20 | 18 | Causal comparison and bounded model-guided experiments are implemented; the core statistical method remains an integration innovation rather than a new algorithm |
| AI/LLM integration | 19/20 | 19+ | DeepSeek V4 Pro live mode can select validated replay experiments; fallback, token usage, and unit cost are verified |
| Track dimension | 18/20 | 19 | Autonomous loop, bounded model-guided replays, report, deep links, and 2:29 demo video exist |
| **Total** | **88/100** | **90-92** | Strong engineering plus an actually evaluated HTTP SUT and bounded agent control flow |

## Verified evidence

- Frontend: 153 tests pass; TypeScript check and production build pass.
- Backend: the complete test suite passes.
- Real HTTP E2E: 31/31 passes.
- V2 autonomous-investigation E2E passes.
- External HTTP SUT E2E passes: 0 regressions in the same-revision control, 8 regressions at mean delta -0.173, 8 HTTP counterfactual replays, exact offline cache replay, and a loud failure when the SUT is unavailable.
- Live DeepSeek V4 Pro verification passes with 3 LLM steps, 1 persisted model-guided replay plan, 8 measured counterfactuals, and the expected `BLOCK / CRITICAL` decision.
- Invalid model key produces recorded fallback steps while preserving the measured decision.
- Run and investigation deep links reopen recorded service data.
- CI gate returns `allow=0`, `review=1`, `block=2`.
- Competition video is rendered at `release/EvalPilot-competition-demo.mp4`.

## Technical feasibility — 19/20

### Strong

- One-command start and stop.
- Persistent API, event flow, evidence links, calculations, and report.
- Deterministic/offline fallback prevents a dead demo.
- Clean worktree installed dependencies and passed the 31-check E2E.
- Runtime tools are explicitly bounded: `kb_search`, `http_get`, `file_read`.
- A third-party HTTP contract and separate reference process prove the evaluator is not tied to its deterministic mock.
- Offline replay is content-addressed and fails loudly on a cache miss.

### Remaining

- Replace the reference HTTP SUT with a public open-source application adapter.
- Verify the clean setup on a second physical host.
- Decide whether browser execution belongs after the competition.

## Market feasibility — 15/20

### Strong

- Public paid products establish willingness to pay for this category.
- Public repository adoption shows developer demand and distribution channels.
- EvalPilot has a clear wedge: release decision, not another observability dashboard.
- `GET /api/runs/{run_id}/gate` provides a real CI integration; exit codes `0/1/2` enforce it automatically.
- Pricing and revenue motions are explicit: release audit, team subscription, enterprise self-host.
- Two public workloads and a measured unit-economics model are published.
- A separate HTTP SUT proves the integration is not limited to the bundled fixture.

### Remaining

- Validate pricing willingness through public adoption or a paid pilot.
- Add a workload in a different modality such as document or browser interaction.
- Re-run the cost model against another model/provider.

Customer interviews are optional support, not a required gate.

## Comprehensive innovation — 17/20

### Strong

- Matched cases and 18 controls separate version change from test difficulty.
- Paired uncertainty is visible.
- Counterfactual replay identifies which change caused each failure.
- Historical incidents become reusable regression memory.
- Live mode can select a bounded replay experiment, which is then executed and measured rather than trusted.
- Naive pass-rate delta versus EvalPilot is documented on SQuAD, HotpotQA, and the enterprise workload.

### Remaining

- State the minimum matched-case count needed for a stable aggregate verdict.
- Run a retrospective on a public application with unknown failure cases.
- Extend root-cause discovery beyond the closed two-intervention vocabulary.

## AI/LLM integration — 19/20

### Strong

- Explicit model roles: hypotheses, bounded replay planning, judge scoring, and report rationale.
- Structured JSON validation and deterministic fallback exist.
- A valid replay plan can affect control flow, but does not write scores, evidence, or verdicts.
- DeepSeek V4 Pro is verified in live mode, including one persisted model-guided replay plan.
- The fallback path is verified with a deliberate HTTP 401.
- Token, run-time, storage, and investigation-cost measurements are recorded; judge token usage is not yet persisted, so the model cost is a lower bound.

### Remaining

- Add a second OpenAI-compatible provider proof.
- Disclose the limits of LLM judging against deterministic checks.
- Persist judge token usage so the full run cost is exact.
- Measure the marginal quality gain of model-guided plans against deterministic plans.

## Track dimension — 18/20

### Strong

- Natural-language objective.
- Autonomous planning, memory recall, probing, replay, decision, and report.
- Verifiable deliverables: report, gate exit code, run id, evidence ids.
- The demo video is 2:28.9, Chinese, 1080p, and uses a real live investigation.
- Deep links reproduce the exact recorded run and investigation.

### Remaining

- Upload the video publicly and verify it in a logged-out browser.
- Add the final team and product descriptions to the competition form.
- Show the model-guided replay plan explicitly in the recording.

## Highest-value next actions

1. Upload and verify the finished competition video.
2. Record a short clip showing a real model-guided replay plan and its measured result.
3. Validate one public open-source application adapter.
4. Add one paid-pilot or public-adoption conversion signal.
5. Re-run cost and accuracy measurements against a second provider.
