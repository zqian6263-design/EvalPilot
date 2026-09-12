# Product

## Platform

Web application with a local FastAPI backend and a React + TypeScript + Vite
frontend.

## Product Purpose

EvalPilot is an autonomous regression-evaluation digital employee for AI
applications. It compares a baseline and a candidate version over matched
scenarios, separates a real regression from sampling noise and a harder test
set, investigates confirmed failures with counterfactual replay, and produces
an evidence-backed release decision.

The operating question is:

> Did this version change break something, and how do we know?

## Users

- AI product and platform teams deciding whether an LLM application is safe to
  ship.
- QA and evaluation teams responsible for a defensible release decision.
- Research groups that need reproducible comparison rather than a single score.

The first commercial scenario is enterprise knowledge-base QA and customer
support.

## Current Capabilities

- One-click deterministic demo and an optional live-LLM mode.
- Baseline vs candidate evaluation over 26 matched scenarios with 18 controls.
- Deterministic checks plus an injectable rubric-judge seam.
- Paired comparison with confidence interval, effect size, and explicit verdict.
- Evidence-linked findings with severity, rationale, and recommendation.
- Autonomous investigation: risk hypotheses, historical incident recall,
  follow-up probes, counterfactual replay, and release decision.
- `BLOCK / REVIEW / ALLOW` release decision with downloadable Markdown report.
- Chinese-first professional light interface.

## Implemented Tool Surface

The current runtime registers exactly:

- `kb_search` — deterministic in-process knowledge-base search.
- `http_get` — allowlisted HTTP retrieval with timeout and size limits.
- `file_read` — read-only file access within configured roots.

The Python sandbox tool is present as a gated placeholder but has no execution
implementation. Browser execution is roadmap work, not a current capability.

## LLM Integration

The deterministic demo works without network access or an API key. Live mode
uses an OpenAI-compatible provider; the current verified product runtime is
DeepSeek V4 Pro.

The model may:

- propose risk hypotheses;
- explain measured findings and counterfactuals;
- draft recommendations and report narrative.

The model may not override measured scores, evidence ids, counterfactual
verdicts, risk level, or the release decision. Invalid output or transport
failure falls back to deterministic behaviour with an explicit reason.

## Evidence Model

Runs persist test cases, evidence, findings, and reports. Supported evidence
kinds are `text`, `screenshot`, `log`, `citation`, `trace`, and `metric`.
The current deterministic demo emits structured text, citation, trace, and
metric evidence; screenshot capture is a schema capability and roadmap item,
not a claim about the current executor.

## Constraints

- No API key is required for the reproducible demo.
- Raw scenario ids, evidence ids, model ids, and status enums remain unchanged.
- LLM output is explanatory; measured evaluation is authoritative.
- Public claims must match the implemented tool surface in this document.
