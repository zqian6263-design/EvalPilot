# Competitor Capability Matrix

Date: 2026-09-13

This matrix compares **publicly described capabilities**, not private
roadmaps, sales claims, or benchmark scores. A cell marked `Not found in
reviewed public docs` means only that: it is not a denial that the capability
may exist behind an enterprise offering.

## Products reviewed

- EvalPilot (this repository)
- [LangSmith](https://www.langchain.com/langsmith)
- [Braintrust](https://www.braintrust.dev/)
- [Langfuse](https://langfuse.com/)
- [Confident AI / DeepEval](https://github.com/confident-ai/deepeval)
- [Promptfoo](https://github.com/promptfoo/promptfoo)

## Matrix

| Capability | EvalPilot | LangSmith | Braintrust | Langfuse | DeepEval | Promptfoo |
|---|---|---|---|---|---|---|
| Dataset and experiment management | Yes | Yes | Yes | Yes | Yes | Yes |
| Tracing / observability | Run-level evidence and traces; no production APM | Yes | Yes | Yes | Not the primary product | Evaluation traces, not full APM |
| LLM-as-judge | Yes, optional | Yes | Yes | Yes | Yes | Yes |
| Offline deterministic demo | Yes | Not found in reviewed public docs | Not found in reviewed public docs | Self-host available, offline demo depends on setup | Yes, pytest-style | Yes, CLI/self-host |
| Matched baseline/candidate design | First-class | Experiment comparison available; matched-gate semantics not advertised | Experiment comparison available; matched-gate semantics not advertised | Dataset experiments available; release-gate semantics not advertised | User-defined test cases | User-defined test cases |
| Control-group separation | Yes, explicit | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs | User-defined | User-defined |
| Paired confidence interval / effect size | Yes, built into report | Aggregate experiment comparison; exact paired gate semantics depend on user setup | Experiment statistics available; exact paired gate semantics depend on setup | Depends on user analysis | User-defined metrics, not a release decision | Assertions and summaries, not a release decision |
| Minimum detectable effect / power diagnostics | Yes | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs |
| Counterfactual intervention replay | Yes, first-class | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs |
| Root-cause attribution | Yes, measured replay | Trace inspection and evaluation analysis | Experiment analysis | Trace inspection and analysis | Test failure analysis | Failure output and assertions |
| Release gate exit code `0/1/2` | Yes | Not found as a dedicated contract in reviewed public docs | CI integration exists; exact exit-code contract not advertised | Not found as a dedicated contract in reviewed public docs | Can be run under pytest/CI; EvalPilot-style gate not advertised | CLI can fail CI; EvalPilot-style gate not advertised |
| JUnit export | Yes | Via test-runner integrations, not a dedicated documented endpoint | CI integrations available | Not found in reviewed public docs | Native pytest/JUnit ecosystem | CI reporters available |
| SARIF export | Yes | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs | Not found in reviewed public docs |
| GitHub PR comment webhook | Yes | Platform integrations may exist; not the reviewed contract | Platform integrations may exist; not the reviewed contract | Not found in reviewed public docs | External CI setup | CI integration |
| SUT capability discovery | Yes, `/capabilities` | Not applicable; SDK/API integration | Not applicable; SDK/API integration | Not applicable; SDK/API integration | Not applicable | Not applicable |
| External HTTP SUT adapter | Yes | Via user instrumentation | Via user instrumentation | Via user instrumentation | Via user tests | Via provider adapters |
| Self-hosted / private deployment | Yes | Enterprise deployment options | Enterprise deployment options | Open-source self-host | Open-source | Open-source |

## EvalPilot's defensible wedge

The comparison does not claim that EvalPilot has more features than mature
observability or evaluation platforms. The narrower claim is:

> EvalPilot turns a paired baseline/candidate comparison into a release decision
> with matched controls, uncertainty, counterfactual root-cause replay, explicit
> per-case blocking, and machine-enforceable CI artifacts.

That is a release-gate wedge. Existing platforms can remain the tracing and
online-evaluation layer; EvalPilot can sit before the merge or deploy as the
release-quality decision layer.

## Commercial implication

The strongest integration path is not replacing an observability vendor. It is:

1. export traces/evaluation data from the existing platform;
2. run EvalPilot's matched release workload;
3. block or approve the release with the gate;
4. attach the report to the PR and release record.
