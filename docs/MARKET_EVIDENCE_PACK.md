# Market Evidence Pack

Date: 2026-09-12

This pack does not depend on customer interviews. It uses public willingness-to-pay,
public adoption signals, implemented integration surfaces, and a falsifiable
commercial model.

## 1. The category already has paying users

Public vendor pricing on the date above:

| Product | Public entry point | Public URL |
|---|---:|---|
| LangSmith | Free; Plus `$39/seat/month`; Enterprise custom | https://www.langchain.com/pricing |
| Braintrust | Free; Pro `$249/month`; Enterprise custom | https://www.braintrust.dev/pricing |
| Langfuse | Free; Core `$29/month`; Pro `$199/month`; Enterprise `$2499/month` | https://langfuse.com/pricing |
| Confident AI / DeepEval | Free; `$200/month`; Team `$2,000/month`; Enterprise custom | https://www.confident-ai.com/pricing |
| Galileo | Free; paid plan from `$100/month`; Enterprise custom | https://galileo.ai/pricing |
| Patronus AI | Free credits / low entry pricing; Enterprise custom | https://www.patronus.ai/pricing |
| Promptfoo | Open source; Enterprise option | https://www.promptfoo.dev/docs/ |

This proves a budget category exists for LLM evaluation, tracing, reliability,
and quality operations. It does not prove that any buyer will choose EvalPilot.

## 2. Public adoption signals

GitHub public repository metrics read on 2026-09-12:

| Project | Stars | Forks | URL |
|---|---:|---:|---|
| Langfuse | 34,502 | 3,759 | https://github.com/langfuse/langfuse |
| Promptfoo | 25,044 | 2,298 | https://github.com/promptfoo/promptfoo |
| DeepEval / Confident AI | 18,231 | 1,921 | https://github.com/confident-ai/deepeval |
| LangSmith SDK | 1,051 | 291 | https://github.com/langchain-ai/langsmith-sdk |

Stars are not revenue, but they are public evidence of developer demand,
category attention, and a distribution channel. The category is crowded; the
submission should not position EvalPilot as "another eval dashboard".

## 3. EvalPilot's market wedge

Most alternatives optimise one or more of:

- tracing and observability;
- dataset and experiment management;
- prompt testing and red teaming;
- online evaluation metrics;
- production monitoring.

EvalPilot's dedicated claim is:

> Given a baseline and candidate version, produce a release decision backed by
> matched controls, paired uncertainty, counterfactual root-cause replay, and
> downloadable evidence.

This is a narrower, operational wedge: the release gate. It is compatible with
existing observability platforms instead of requiring their replacement.

## 4. Integration and landing evidence

Implemented now:

- REST API for projects, runs, reports, events, and investigations.
- Persistent run and evidence records.
- Markdown report download.
- CI gate endpoint: `GET /api/runs/{run_id}/gate`.
- Machine exit codes: `0 allow`, `1 review`, `2 block`.
- PowerShell CI client: `scripts/ci-gate.ps1`.
- Reproducible deep links for existing runs and investigations.
- Deterministic offline fallback and optional live LLM mode.

Why this matters commercially:

- A CI gate is a concrete integration point into the buyer's existing release process.
- A BLOCK exit code can prevent a PR or deployment without a custom dashboard integration.
- The Markdown report is the human artifact; the exit code is the machine artifact.
- Self-hosting can preserve private corpora and avoid sending customer data to a new vendor.

## 5. Business model

Three revenue motions, in order:

### Release audit

A single release comparison sold as a fixed-scope engagement.
Target: `$2,000-$10,000` per release audit depending on corpus size and integration.

### Team subscription

A recurring release gate for one or more AI products.
Hypothesis: `$299-$999/month` for a small team, with included runs and usage overage.

### Enterprise self-host

Air-gapped or private-cloud deployment, SSO/RBAC, audit exports, custom adapters,
and support. Pricing hypothesis: `$25,000-$100,000/year`.

The public competitor range supports these anchors; it does not validate them.

## 6. Unit-economics formula

Do not present revenue until the following are measured:

```text
cost_per_run =
  model_tokens * token_price
  + compute_seconds * compute_price
  + storage_months * storage_price
  + support_minutes * loaded_support_cost
```

The current product already records elapsed time, evidence counts, findings, and
model calls. The next engineering increment should persist token usage and
compute cost per run.

## 7. GTM without interviews

1. Publish the open-source self-host path and deterministic demo.
2. Let developers run the CI gate against their own run id.
3. Publish a public benchmark comparing a naive score delta with EvalPilot's
   matched-control decision.
4. Offer a historical-release retrospective template that a team can run
   without giving EvalPilot production access.
5. Convert successful retro-diagnoses into paid team subscriptions.

Public adoption, self-serve execution, and conversion data replace interviews as
the primary evidence path.

## 8. Required public experiments

- [x] Competitor pricing matrix.
- [x] Public repository adoption signals.
- [x] CI gate and exit-code integration.
- [x] Run public comparisons on SQuAD and HotpotQA.
- [x] Publish naive-delta vs EvalPilot comparison.
- [x] Measure model, compute, storage, and total run cost.
- [x] Package a one-command cross-platform deployment path.

These are execution tasks, not interview tasks.

## 9. Measured evidence (2026-09-12)

- Public SQuAD workload: 16 rows, 16 article titles, 5 controlled regressions, 11 controls.
- Naive pass rate: 100.00% -> 68.75%.
- EvalPilot: mean delta -0.3125, 95% CI [-0.5625, -0.1250], confidence 98.59%, regression confirmed.
- Public comparisons: SQuAD and HotpotQA, 16 rows each, 5 controlled regressions, 11 controls.
- Both workloads: mean -0.3125, 95% CI [-0.5625, -0.1250], confidence 98.59%.
- Live DeepSeek V4 Pro full run: 78,695 tokens; 52 rubric-judge calls used 61,202 tokens and the investigation used 17,493 tokens with 3 LLM steps and 1 model-guided replay plan.
- Full run compute: 474.00 seconds (410.94 run + 63.20 investigation); logical storage: 0.2500 MB.
- Model peak cost: $0.251525; compute: $0.013167; storage: $0.00000562.
- Total peak cost: $0.264697; total off-peak cost: $0.138935.
- Judge usage is persisted in the run report, and model planning plus Judge cost were verified in the same live run.

## 10. External integration proof (2026-09-13)

The evaluator is no longer demonstrated only against its own deterministic mock. The acceptance SUT is an adapter over the public Apache-2.0 `deepset-ai/haystack` BM25 retriever.
The reproducible `scripts/sut-e2e-check.ps1` starts a separate HTTP SUT process
and verifies the integration contract end to end:

- same-revision control: 0 regressed scenarios, mean delta 0;
- baseline vs candidate: 8 regressed scenarios, mean delta -0.173;
- 8 counterfactual replays executed through the HTTP boundary with trace evidence;
- cached workload replay with the SUT stopped reproduced the same result offline;
- an uncached workload with the SUT unavailable failed loudly instead of silently
  falling back to the mock.

This is integration and deployment evidence, not customer willingness-to-pay.
The commercial evidence gap remains a paid pilot or public open-source adoption.
