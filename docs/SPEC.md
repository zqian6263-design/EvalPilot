# Product Specification

> **Implementation status (2026-09-14).** The working runtime implements
> `kb_search`, allowlisted `http_get`, read-only `file_read`, and an opt-in,
> bounded `browser_run` modality. The sandboxed Python tool remains a disabled
> placeholder. Public material must distinguish implemented tools from planned
> tools.

## One-line positioning

EvalPilot is an autonomous regression-evaluation digital employee for AI products and research teams.

## Problem

AI teams routinely change models, prompts, retrieval settings, tools, and workflows. Existing manual regression testing is expensive and incomplete, while public benchmarks do not represent product-specific quality. Teams need an auditable way to know whether a version change caused a real regression.

## Primary users

- AI product and platform teams shipping LLM applications.
- Research groups maintaining reproducible model or agent evaluation.
- QA and data teams responsible for release quality.

## Primary MVP scenario

An enterprise knowledge-base QA or customer-support assistant has two versions. EvalPilot compares them and detects a real regression while controlling for test difficulty, randomness, and irrelevant changes.

## Product loop

1. Ingest a project brief, version change, and golden scenarios.
2. Build a risk map and generate normal, boundary, and adversarial test cases.
3. Execute each case through allowed tools (HTTP/API, browser, file parsing, optional sandboxed Python).
4. Capture text, screenshots, logs, citations, and traces.
5. Evaluate with deterministic checks plus rubric-based LLM judging.
6. Compare matched cases across versions and repeat samples.
7. Estimate whether the change is a stable regression rather than noise.
8. Emit an evidence-backed report with failures, severity, root-cause hints, and recommendations.

## Differentiator

The causal-evaluation layer uses matched cases, repeated samples, and controlled comparison so a harder test set is not mistaken for a model regression. Every conclusion is traceable and reproducible.

## Out of scope for the first MVP

- General-purpose model pretraining or fine-tuning.
- Full autonomous code modification.
- Unbounded arbitrary code execution.
- Multi-tenant billing and enterprise SSO.
- Arbitrary internet crawling without explicit allowlists.

## Success metrics

- End-to-end run completes from UI without manual intervention.
- At least 10 seeded test cases and 2 versions.
- Every finding contains evidence links and evaluator rationale.
- Regression detection is reproducible across repeated runs.
- Human reviewers can understand the report without reading raw logs.
