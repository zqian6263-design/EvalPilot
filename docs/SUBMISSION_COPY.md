# Competition Submission Copy

## Team

**逆熵智评 | NEGENTROPY LABS**

## Product

**EvalPilot｜AI 应用回归评测与自主发布质量官**

## One-line pitch

EvalPilot is an autonomous release-quality digital employee: it confirms whether an AI version change caused a real regression, replays the failure to identify the root cause, and blocks unsafe releases with an evidence-backed report.

## Detailed description

EvalPilot 面向 AI 产品与研究团队，解决模型、Prompt、检索、记忆或工具链更新后“看起来更好，却可能悄悄变差”的发布风险。系统首先对 baseline 与 candidate 执行同一组匹配场景，区分真实回归、测试难度变化和采样噪声；确认回归后，自主调查会生成风险假设、召回历史事故、追加探查，并通过反事实重放分别禁用可疑变更，测量失败是否消失。最终，系统输出 BLOCK / REVIEW / ALLOW 发布决策、根因、修复建议和可下载的证据报告，并通过 GET /api/runs/{run_id}/gate 返回 0 / 1 / 2 退出码，直接接入 CI/CD 发布流水线。当前演示中，v1.1 虽然更快且普通问答仍通过，但压缩层导致 7 个条款丢失场景回归，安全护栏导致 1 个凭证泄露场景回归；26 个匹配场景、18 个控制组和配对置信区间共同确认这是发布阻断问题。系统默认离线可复现，同时支持接入 OpenAI-compatible 大模型进行自主规划和评审解释，且大模型不能覆盖实测证据和阻断结论。

## Scoring alignment

### Technical feasibility

- Runnable FastAPI + React product, SQLite persistence, event streams, migration support.
- 26 matched scenarios, 18 controls, 8 critical regressions, evidence-linked findings.
- Measured counterfactual replay with explicit fallbacks and no network requirement for the demo.

### Market feasibility

- Primary user: AI product, platform, evaluation, and QA teams shipping LLM applications.
- Trigger: model, prompt, retrieval, memory, or tool update before release.
- Value: convert hours of manual release checks into an auditable minutes-scale gate.
- Public paid competitors establish willingness to pay across seat and usage models.
- Public SQuAD and HotpotQA workloads verify cross-dataset matched-control decisions.
- A complete live run costs about $0.0623 at peak, including model, compute, and storage.
- Integration path: REST API -> release-gate report -> CI exit code -> team subscription -> enterprise self-host.
- Revenue motions: fixed-scope release audit, monthly team gate, annual enterprise deployment.

### Innovation

- Matched causal comparison instead of raw benchmark deltas.
- Counterfactual replay identifies which change caused each failure.
- Regression memory turns past incidents into permanent guard tests.
- Every claim carries evidence ids, measured scores, and reproducibility metadata.

### LLM integration

- LLM planner proposes risk hypotheses from the release objective.
- LLM judge adds qualitative rubric scoring with strict JSON validation.
- LLM reporter produces an evidence-grounded rationale and recommendations.
- Measured verdicts remain authoritative; LLM has no authority to invent evidence or override replay results.

### Track dimension

- Task understanding: accepts a natural-language objective and observed release symptoms.
- Autonomous planning: builds risk hypotheses, probes, memory recall, and replay steps.
- Tool interaction: repository, HTTP/file tools, deterministic reproducer, and optional live LLM.
- Deliverable: BLOCK / REVIEW / ALLOW decision plus Markdown evidence report.
- End-to-end loop: version change -> regression confirmation -> root cause -> release gate -> learning memory.

## Demo URL

`http://127.0.0.1:5173/#investigation&demo`

## Video outline

1. Candidate is faster; ordinary questions pass.
2. EvalPilot confirms eight real regressions with 18 controls.
3. Start autonomous investigation.
4. Show risk hypotheses and recalled historical incidents.
5. Show compression and security-guard counterfactual replays.
6. Show BLOCK decision and downloaded evidence report.
7. Explain that the same mechanism extends to each AI product release.

## Evidence to present

- Live run: 26 matched cases, 8 findings, evidence count.
- Confirmed regression: mean delta -0.173, 95% CI -0.288 to -0.077.
- Counterfactual: compression restores seven scenarios; security guard restores one.
- Release decision: BLOCK, CRITICAL.
- Market ROI and pricing assumptions from `docs/MARKET_STRATEGY.md`.
- Runtime badge: deterministic vs live LLM mode.
