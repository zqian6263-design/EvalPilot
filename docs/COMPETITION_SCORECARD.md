# Competition Scorecard — Current Self-Assessment

**Date: 2026-09-13**

This is an internal estimate, not a judge score. It uses public evidence and
reproducible product artifacts; customer interviews are optional here and are
not treated as a prerequisite.

## Current estimate

| Criterion | Current | Target for finals | Main reason |
|---|---:|---:|---|
| Technical feasibility | 20/20 | 20 | Product, tests, external HTTP SUT E2E, offline replay, outage failure, and one-command deployment pass |
| Market feasibility | 18/20 | 19 | Paid category, public adoption, enforceable CI gate, two public workloads, measured end-to-end cost, and one-command deployment |
| Comprehensive innovation | 19/20 | 20 | Causal comparison and bounded model-guided experiments are implemented; the core statistical method remains an integration innovation rather than a new algorithm |
| AI/LLM integration | 19/20 | 19+ | DeepSeek V4 Pro live mode can select validated replay experiments; fallback, token usage, and unit cost are verified |
| Track dimension | 19/20 | 20 | Autonomous loop, bounded model-guided replays, report, deep links, and 2:29 demo video exist |
| **Total** | **95/100** | **95-97** | Strong engineering plus an actually evaluated HTTP SUT and bounded agent control flow |

## Verified evidence

- Frontend: 153 tests pass; TypeScript check and production build pass.
- Clean-worktree acceptance: full backend suite, 31/31 basic E2E, V2 investigation E2E, and public Haystack SUT E2E all pass.
- Backend: the complete test suite passes.
- Real HTTP E2E: 31/31 passes.
- V2 autonomous-investigation E2E passes.
- Public open-source Haystack HTTP SUT E2E passes: 0 regressions in the same-revision control, 8 regressions at mean delta -0.173, 8 HTTP counterfactual replays, exact offline cache replay, and a loud failure when the SUT is unavailable.
- Same live run verifies 3 LLM steps, 1 persisted model-guided replay plan, 52 Judge calls, 8 measured counterfactuals, and the expected `BLOCK / CRITICAL` decision.
- Invalid model key produces recorded fallback steps while preserving the measured decision.
- Run and investigation deep links reopen recorded service data.
- CI gate returns `allow=0`, `review=1`, `block=2`; JUnit and SARIF exports validate against a live run.
- Judge call/token budgets, SUT capability discovery, and paired power diagnostics are implemented and tested.
- Competition video v2 is rendered at `release/EvalPilot-competition-demo-v2.mp4`; it explicitly shows the model-guided replay plan from 1:10 to 1:25.
- Public video: https://www.bilibili.com/video/BV1mPYY6sE1k (backup: https://n.uguu.se/AFnrdUSF.mp4).

## Technical feasibility — 20/20

### Strong

- One-command start and stop.
- Persistent API, event flow, evidence links, calculations, and report.
- Deterministic/offline fallback prevents a dead demo.
- Clean worktree installed dependencies and passed the 31-check E2E.
- Runtime tools are explicitly bounded: `kb_search`, `http_get`, `file_read`.
- A third-party HTTP contract and a separate Haystack-backed process prove the evaluator is not tied to its deterministic mock.
- Offline replay is content-addressed and fails loudly on a cache miss.
- The public SUT runs a splitter -> retriever -> joiner -> grounded reranker Haystack pipeline.

### Remaining

- Extend the public Haystack pipeline to a second open-source application.
- Verify the clean setup on a second physical host.
- Decide whether browser execution belongs after the competition.

## Market feasibility — 18/20

### Strong

- Public paid products establish willingness to pay for this category.
- Public repository adoption shows developer demand and distribution channels.
- EvalPilot has a clear wedge: release decision, not another observability dashboard.
- `GET /api/runs/{run_id}/gate` provides a real CI integration; exit codes `0/1/2` enforce it automatically.
- JUnit, SARIF 2.1.0, GitHub Actions, and PR summary export paths are implemented.
- GitHub webhook with HMAC verification can write the gate result to a PR.
- Release Audit generation and a public competitor capability matrix are published.
- Real upstream Haystack 3.0.0 vs 3.1.1 comparison: 52 checks, 0 semantic mismatches.
- Pricing and revenue motions are explicit: release audit, team subscription, enterprise self-host.
- Two public workloads and a measured unit-economics model are published.
- A separate HTTP SUT proves the integration is not limited to the bundled fixture.

### Remaining

- Validate pricing willingness through public adoption or a paid pilot.
- Convert the GitHub integration into a public repository install or fork.
- Add a workload in a different modality such as document or browser interaction.
- Re-run the cost model against another model/provider.
- Replace the deterministic grounded composer with a live upstream generator in a separate deployment profile.

Customer interviews are optional support, not a required gate.

## Comprehensive innovation — 19/20

### Strong

- Matched cases and 18 controls separate version change from test difficulty.
- Paired uncertainty is visible.
- Counterfactual replay identifies which change caused each failure.
- Historical incidents become reusable regression memory.
- Live mode can select a bounded replay experiment, which is then executed and measured rather than trusted.
- Naive pass-rate delta versus EvalPilot is documented on SQuAD, HotpotQA, and the enterprise workload.
- OOD planning benchmark: deterministic rules 2/6; DeepSeek V4 Pro 6/6 at 1,359 tokens.
- OOD execution benchmark: 4/4 root causes measured through HTTP.
- Real upstream Haystack 3.0.0 vs 3.1.1: 52 comparisons, 0 semantic mismatches.
- Judge calibration harness emits MAE, bias, Pearson correlation, and exact agreement; real human labels remain external.

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
- Token, run-time, storage, and full run cost measurements include persisted judge usage.

### Remaining

- Add a second OpenAI-compatible provider proof.
- Disclose the limits of LLM judging against deterministic checks.
- Extend the planning comparison beyond the eight known fixture failures to OOD scenarios.

## Track dimension — 19/20

### Strong

- Natural-language objective.
- Autonomous planning, memory recall, probing, replay, decision, and report.
- Verifiable deliverables: report, gate exit code, run id, evidence ids.
- The v2 demo video is 2:28.97, Chinese, 1080p, uses a real live investigation, and shows the model-guided replay plan.
- Deep links reproduce the exact recorded run and investigation.

### Remaining

- Add the final team and product descriptions to the competition form.
- Verify the Bilibili page from a logged-out browser after review completes.

## Highest-value next actions

1. Submit the competition form with `https://www.bilibili.com/video/BV1mPYY6sE1k`.
2. Add one paid-pilot or public-adoption conversion signal.
3. Extend the Haystack adapter to a full upstream RAG application deployment.
4. Extend planning comparison to out-of-distribution failures.
5. Re-run cost and accuracy measurements against a second provider.
