# P1 Roadmap and Status

Date: 2026-09-13

P1 focuses on turning the competition-ready P0 build into a product that external
engineering teams can integrate and operate.

## 1. SUT capability discovery

Status: implemented

- `GET /capabilities` declares contract version, executable versions,
  interventions, and evidence features.
- EvalPilot validates a request before sending it to an incompatible SUT.
- 404 falls back to the legacy answer-only contract.
- Offline replay skips discovery and remains deterministic.
- Tests cover declared, unsupported-version, and legacy paths.

## 2. Model planning robustness

Status: implemented

- Retry malformed structured output once.
- Preserve the valid subset of a partially valid replay plan.
- Merge deterministic suggestions for missing scenarios.
- Record planner confidence, repair attempts, and fallback reasons.

## 3. Cost budget guard

Status: implemented

- Set per-run model-token and dollar budgets.
- Degrade Judge or model planning before exceeding the budget.
- Persist the budget decision on the run and report.
- Test budget exhaustion without weakening deterministic evidence.

## 4. CI/CD deep integration

Status: implemented

- GitHub Actions workflow.
- GitLab CI template.
- JUnit and SARIF result exports.
- PR summary comment with decision, failures, and report link.
- Machine exit codes remain the ultimate gate.

## 5. Statistical enhancements

Status: implemented

- Minimum detectable effect and power estimate.
- Multiple-comparison policy for domain-level tests.
- Sequential monitoring safeguards.
- Sample-size recommendation when the aggregate verdict is inconclusive.

## 6. Full upstream RAG application adapter

Status: next

- Move from a BM25 retriever adapter to a complete upstream RAG deployment.
- Add document splitting, hybrid retrieval, reranking, prompt construction,
  generation, and trace collection.
- Keep the current lightweight adapter as the deterministic acceptance fixture.
