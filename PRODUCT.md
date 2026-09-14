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
- Opt-in browser task modality with host allowlisting, action traces, extracted text, and screenshot evidence.
- Opt-in browser task modality with host allowlisting, action traces, extracted text, and screenshot evidence.

## Implemented Tool Surface

The current runtime registers exactly:

- `kb_search` — deterministic in-process knowledge-base search.
- `http_get` — allowlisted HTTP retrieval with timeout and size limits.
- `file_read` — read-only file access within configured roots.
- `browser_run` — opt-in Playwright task execution with host allowlisting, action trace, and screenshot evidence.
- `browser_run` — opt-in Playwright task execution with host allowlisting, action trace, and screenshot evidence.

The Python sandbox tool is present as a gated placeholder but has no execution
implementation. Browser execution is implemented as an opt-in bounded tool and
is disabled by default.

## LLM Integration

The deterministic demo works without network access or an API key. Live mode
uses an OpenAI-compatible provider; DeepSeek V4 Pro and GLM-4.7 are both
verified through the same runtime seam.

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
The deterministic demo emits structured text, citation, trace, and metric
evidence. The opt-in browser executor additionally persists screenshots and
per-action traces; this is verified in `docs/P3_BROWSER_MODALITY.md`.

## Constraints

- No API key is required for the reproducible demo.
- Raw scenario ids, evidence ids, model ids, and status enums remain unchanged.
- LLM output is explanatory; measured evaluation is authoritative.
- Public claims must match the implemented tool surface in this document.
