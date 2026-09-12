# Market Validation Plan

Date: 2026-09-12

## Purpose

Turn EvalPilot's market story from an engineering hypothesis into evidence.
This document does not claim interviews or traction that have not happened.

## Public landscape snapshot

The following figures were read from public vendor pricing pages on the date
above. Prices can change and must be rechecked before submission.

| Product | Public entry pricing | Primary category | Relevance to EvalPilot |
|---|---:|---|---|
| LangSmith | Free; Plus `$39/seat/month`; usage units; Enterprise custom | Tracing, evals, deployment | Large incumbent; broad observability and evaluation platform |
| Braintrust | Free; Pro `$249/month`; usage beyond included credits | Eval/observability platform | Strong experiment and evaluation workflow |
| Langfuse | Free; Core `$29/month`; Pro `$199/month`; Enterprise `$2499/month` | Open-source LLM engineering and observability | Strong self-host and tracing alternative |
| Confident AI / DeepEval | Free; `$200/month`; Team `$2,000/month`; Enterprise custom | LLM evaluation and tracing | Closest direct evaluation comparison |
| Galileo | Free; paid plan from `$100/month`; Enterprise | AI reliability and observability | Evaluation and production monitoring |
| Patronus AI | Free credits / low entry pricing; Enterprise custom | Evaluation and safety | Evaluation/security overlap |
| Promptfoo | Open source; Enterprise option | Prompt testing, red teaming, evals | Developer-friendly alternative |
| EvalPilot | Not yet priced | Release gate and autonomous investigation | Differentiates through matched controls, counterfactual root cause, and an auditable BLOCK decision |

### What this evidence proves

- Buyers already pay for LLM evaluation, tracing, and reliability tooling.
- Pricing models are commonly seat-based plus usage-based.
- The category is crowded; "another eval dashboard" is not a defensible wedge.
- EvalPilot's strongest positioning is the release decision:

> Given a baseline and a candidate, prove whether a real regression occurred,
> identify which change caused it, and block the release with auditable evidence.

### What this evidence does not prove

- That a buyer will pay for EvalPilot.
- That the buyer prefers a release gate over existing observability workflows.
- That the estimated time savings or ROI is accurate.

Those require interviews and a pilot.

## ICP to validate

Primary: an AI platform or QA team of 5-40 engineers that ships a
knowledge-base or customer-support LLM application and changes prompts,
retrieval, models, memory, or tools at least twice a month.

Economic buyer: engineering director, VP Engineering, or QA lead.
Champion: AI platform lead, evaluation engineer, or QA lead.
Trigger: a release candidate is believed to be an improvement, but the team
cannot prove it did not damage product-specific behavior.

## Interview target

Complete 8-10 problem interviews. Do not ask for praise or feature opinions.
Reconstruct the last real release decision.

### Interview questions

1. When did you last change an LLM application's model, prompt, retrieval, or tools?
2. What was the expected benefit of that change?
3. How did the team decide whether it was safe to release?
4. What artifacts existed at decision time: cases, traces, reports, dashboards, approvals?
5. What failed or almost failed after a release?
6. How did you discover the failure, and how long did it take?
7. How much engineering or support time did the incident consume?
8. Who owned the final go/no-go decision?
9. Which existing tools did you use? What could they not answer?
10. If a release gate produced a BLOCK decision and root-cause evidence, would you trial it? What would stop you?

### Evidence to capture per interview

- role and company size band, not personal data;
- last-release date band;
- current decision process;
- one concrete failure or near-miss;
- whether the result was measured, estimated, or unknown;
- current tool and budget owner;
- willingness to run a retrospective pilot;
- permission to quote anonymously.

## Offer to test

Start with a **historical-release retrospective**, not a generic demo:

- Input: one already-shipped baseline/candidate pair and its knowledge corpus.
- Output: regression report, root cause, and a decision.
- Success criterion: EvalPilot agrees with the incident history, or exposes a
  disagreement that the team can explain.

This avoids asking for production access and tests the strongest claim.

## Outreach copy

### Short Chinese message

你好，我们在做一套 AI 应用发布前的回归评测工具。它不只看总分，而是用匹配场景、对照组和反事实重放判断“这次版本变更是否真的造成了回归、根因是什么”。我们想找正在维护知识库问答/智能客服的团队做一次 20 分钟问题访谈，只复盘最近一次真实发布决策，不推销、不索要敏感数据。方便约个时间吗？

### Short English message

Hi — we are building an AI release-gate tool for regression decisions. Instead of reporting only a score delta, it uses matched cases, controls, and counterfactual replay to show whether a version change caused a real regression and which change is responsible. Could we run a 20-minute problem interview about your most recent LLM release decision? No sales pitch and no sensitive data required.

## What I can produce without external interviews

- competitor matrix and public pricing table;
- buyer and user map;
- interview guide and consent notes;
- outreach copy;
- survey form;
- target organization and role criteria;
- ROI calculator with explicitly labelled assumptions;
- interview synthesis and a revised market score once responses exist.

## What requires a real human outside the team

- interview responses;
- a design partner;
- a retrospective on a real release;
- pricing validation;
- a letter of intent or pilot agreement.

These must not be fabricated.
