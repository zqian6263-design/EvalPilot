# Competition Pitch

## One sentence

EvalPilot turns AI version updates into auditable regression decisions: it plans tests, executes them, gathers evidence, and tells a team whether quality truly got worse.

## Judge-facing problem

AI applications change constantly, but quality is usually checked with a few manual examples or a public benchmark. Neither proves that a product-specific capability still works. Teams need a fast answer to one question: **did this change cause a real regression?**

## Why now

LLM applications now combine models, prompts, retrieval, memory, and tools. A small change in any layer can hurt citations, refusal behavior, factual coverage, formatting, or task completion. Existing evaluation tools report a score but often cannot explain the cause or produce release-ready evidence.

## Solution

EvalPilot is a digital quality employee with a closed loop:

1. Read the product brief and version change.
2. Build a risk map.
3. Generate normal, boundary, and adversarial tests.
4. Execute through the implemented tool surface: knowledge-base search, allowlisted HTTP, and read-only file access.
5. Capture text, screenshots, citations, logs, metrics, and traces.
6. Combine deterministic checks with rubric-based LLM judging.
7. Compare matched cases across versions using repeated samples.
8. Produce findings, confidence, root-cause hints, and recommendations.
9. Expose a CI gate with machine exit codes: 0 allow, 1 review, 2 block.

## Differentiated innovation

The key differentiator is **causal regression comparison**, not another chatbot wrapper. EvalPilot controls case difficulty and randomness, uses paired samples, reports uncertainty, and refuses to call a noisy score change a regression. Every verdict is evidence-backed and reproducible. The decision can also be enforced directly in CI because the gate returns standard machine exit codes.

## Initial market

The first scenario is enterprise knowledge-base QA and customer support. Buyers include AI product teams, QA teams, platform teams, and research groups. Natural expansion paths are model selection, release gates, prompt regression, agent workflow monitoring, and compliance evidence.

## Business model hypothesis

Project-based evaluation plus team subscription, with usage-based execution for repeated release testing. The first commercial use case is a release-gate report before an AI application update.

## Competition score mapping

| Criterion | Evidence in the product |
|---|---|
| Technical feasibility | Narrow scenario, runnable MVP, practical tools |
| Market feasibility | Clear buyer, recurring release workflow, expanding use |
| Innovation | Causal comparison, uncertainty-aware verdict, evidence chain |
| LLM integration | Planner, tool executor, judge, and report generator are explicit roles |
| Track dimension | Autonomous end-to-end execution and a verifiable deliverable |

## Five-minute presentation

### 0:00-0:45 Problem

AI teams ship changes faster than they can validate product-specific behavior. Manual testing is slow; benchmark scores do not answer whether this release caused a regression.

### 0:45-1:30 Product

Show the one-line promise and the complete loop: brief -> tests -> execution -> evidence -> causal comparison -> report.

### 1:30-3:15 Live demo

Open the seeded knowledge-base QA project. Run baseline and candidate versions. Show progress, evidence, matched comparison, uncertainty, and the final high-severity regression.

### 3:15-4:15 Differentiation and value

Explain why matched samples and uncertainty matter. Show time saved, release risk reduced, and the path from one scenario to a reusable quality gate.

### 4:15-5:00 Team and roadmap

Explain team roles, what is already working, the next validation milestone, and the commercial or research path.

## Three-minute video script

1. 20 seconds: state the pain and promise.
2. 40 seconds: show project and run creation.
3. 50 seconds: show task execution and evidence capture.
4. 40 seconds: show the regression verdict and causal explanation.
5. 30 seconds: show the exported report and business value.
