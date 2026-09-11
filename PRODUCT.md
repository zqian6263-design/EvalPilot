# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated. React + TypeScript + Vite, per the repository collaboration contract in `CLAUDE.md`. No separate stack question was asked: the contract already fixes the frontend stack, and `docs/INTERFACES.md` fixes the API contract this surface consumes. *(Inferred: no interview round was possible — see Provenance.)*

## Users

*(Inferred from `docs/SPEC.md`; not directly confirmed in an interview.)*

- **AI product and platform teams** shipping LLM applications, who must decide whether a model / prompt / retrieval / tool change is safe to ship.
- **Research groups** maintaining reproducible model or agent evaluation, who need auditable comparisons rather than vibes.
- **QA and data teams** responsible for release quality, who own the go / no-go call and must defend it to someone else.

The operating moment is a release decision under time pressure: a candidate version exists, the team believes it is an improvement, and nobody can currently prove whether quality moved.

## Product Purpose

EvalPilot is an autonomous regression-evaluation digital employee: it ingests a project brief and a version change, plans normal / boundary / adversarial test cases, executes them through allowed tools, captures evidence, scores the results, and emits an evidence-backed report on whether a real regression occurred.

Success means a reviewer can answer *"did this version change break something, and how do you know?"* without reading raw logs. `docs/SPEC.md` fixes the MVP success bar: end-to-end run from the UI without manual intervention, >= 10 seeded cases across 2 versions, every finding carrying evidence links and evaluator rationale, and reproducible detection across repeated runs.

## Positioning

The causal-evaluation layer. Matched cases, repeated samples, and controlled comparison let EvalPilot separate three things that raw before/after score deltas conflate: a real regression, a genuinely harder test set, and sampling noise. A neighboring eval tool that only reports aggregate score deltas cannot truthfully copy this, because the claim rests on the comparison design rather than on the metric.

## Operating Context

- **Surface under evaluation:** enterprise knowledge-base QA / customer-support assistants. This is the fixed MVP scenario (`docs/SPEC.md`), not a general-purpose eval platform.
- **Compared entities:** a baseline version and a candidate version of the same assistant — model, prompt, retrieval configuration, tools, or workflow.
- **Runtime:** a local demo for a competition submission; the backend is FastAPI on `127.0.0.1:8000` with a Vite dev proxy in front. Submission deadline 2026-09-19.
- **Ritual:** one-click seeded demo, live run progress, evidence inspection, verdict, report. The demo is watched by judges in real time, so the surface must hold up when someone else is driving it.
- **Artifacts:** text, screenshots, logs, citations, traces, metrics — and an evaluator rationale attached to every finding.

## Capabilities and Constraints

**In scope for this surface:**

- One-click seeded demo entry; no manual setup before the demo runs.
- Baseline vs candidate metric comparison with an explicit, defensible verdict.
- Run progress timeline / event stream rendered live.
- Test case list with category, difficulty, status, and per-version scores.
- Evidence drawer: text, screenshot placeholders, citations, logs, evaluator rationale.
- Findings and generated report with severity and recommendations.
- A Vite dev proxy to `http://127.0.0.1:8000` and an API adapter against the frozen `/api` contract.
- A deterministic mock fallback, so the console is demonstrable with the backend offline.

**Terminology is fixed** by `docs/INTERFACES.md` and must not be renamed here: `Run`, `TestCase`, `Evidence`, `Finding`, `Report`; categories `normal | boundary | adversarial | regression`; statuses `queued | planning | executing | evaluating | completed | failed | cancelled`; case statuses `pending | running | passed | failed | error`; evidence kinds `text | screenshot | log | citation | trace | metric`; severities `info | low | medium | high | critical`.

**Hard constraints:**

- `docs/INTERFACES.md` and `docs/SPEC.md` are the frozen source of truth. The frontend changes no shared doc and no backend file.
- No API keys in Git; `.env.example` only.
- Timestamps are UTC ISO-8601; IDs are UUID strings.
- Dependencies stay practical — the demo must build and run on a judge's machine.
- Desktop-first: the demo is presented on a large screen, and it must degrade to a sane narrow layout rather than break.

**Undecided:** visual world, palette, typography, motion. Deliberately not fixed here.

## Evidence on Hand

Real and citable:

- `docs/SPEC.md`, `docs/INTERFACES.md`, `docs/ROADMAP.md`, `README.md`, `CLAUDE.md` — the product and interface contract.
- The frozen event payload shape and HTTP API list in `docs/INTERFACES.md`.

**Absences future work must not fabricate:**

- There is no real backend response, no captured HTTP trace, and no real LLM-judge output in this worktree yet. Every number, screenshot, citation, and rationale shown in the demo console is **seeded mock data**, and the UI must label it as such whenever it is running on the mock transport.
- There are no real customer names, testimonials, or benchmark results, and none may be invented.

## Product Principles

1. **Evidence before verdict.** No conclusion is rendered anywhere in the UI without a path to the input, output, trace, and rationale behind it.
2. **Separate regression from noise.** The UI must show *why* a delta is trusted — matched cases, repeat samples, controlled comparison — not just that a number moved.
3. **Honest state.** Mock data is labelled mock data; a run that is still executing never renders as finished; an unknown is shown as unknown rather than defaulted to green.
4. **Demo-grade resilience.** The console is fully demonstrable with the backend offline. Never show a dead end to someone watching.
5. **Density with hierarchy.** This is an Operate surface for reviewers: information-dense, scannable, and calm — but the verdict is legible from across a demo room.

## Provenance

This file was written by an implementation agent, not through an `init` interview: the session's tool surface has no interactive question tool, and the brief supplied explicit standing authorization to build. Every section above is either quoted from a frozen repository doc (which is real evidence) or marked *(Inferred)*. The **Users** and **Stack** sections are the two inferences worth re-confirming with the product owner; Platform (`web`) is fixed by the repository contract.
