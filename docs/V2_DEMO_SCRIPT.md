# V2 Demo Script

## Positioning

EvalPilot is not a scoreboard. It is an autonomous release-quality digital employee that investigates a version change, proves the root cause with counterfactual replay, and decides whether the release may ship.

## Opening

> Version 1.1 is 75 milliseconds faster and normal support answers still work. The team wants to ship it. EvalPilot has one question: can they prove it is safe?

## Act 1: Confirm the regression

Show the existing live console:

- 26 matched scenarios;
- 18 controls;
- 8 critical regressions;
- mean delta -0.173;
- 95% CI -0.288 to -0.077;
- verdict: confirmed regression.

The red tape leaving the tolerance band is the visual proof moment.

## Act 2: Ask why

Click **Start autonomous investigation** with the objective:

> Determine whether v1.1 is safe to ship, identify the root cause of the regression, and produce an evidence-backed release decision.

Show structured actions, not hidden reasoning:

1. Build risk hypotheses for escalation, safety, and security.
2. Recall similar historical incidents from memory.
3. Create follow-up probes around the failed clauses.
4. Replay failing cases under controlled interventions.

## Act 3: Recall memory

Show at least two historical incidents:

- a previous document-compression incident that removed mandatory clauses;
- a previous credential-disclosure incident.

Highlight that the agent turns past failures into guard tests.

## Act 4: Counterfactual root cause

Show the intervention panel:

- disable compression -> dropped-clause failures disappear;
- restore security guard -> credential disclosure disappears;
- controls remain unchanged.

Expected conclusion:

> The dominant root cause is the new compression layer, with a separate security-guard regression in prompt-injection handling.

## Act 5: Release decision

Show:

```text
RELEASE DECISION: BLOCK
Risk: CRITICAL
Evidence: 8 regressions / 18 controls / CI -0.288 to -0.077
Root cause: compression layer + security guard
```

Download the Markdown report and show that every claim links to evidence.

## Closing

> EvalPilot does not just find failures. It investigates them, proves the cause, blocks the unsafe release, and remembers the failure so the next release is tested automatically.

## Timing

- Problem: 25 seconds
- Confirmed regression: 45 seconds
- Autonomous investigation: 60 seconds
- Memory and root cause: 60 seconds
- Decision and report: 30 seconds
- Team/roadmap: 20 seconds

## Rules

- Do not show private chain-of-thought.
- Show plans, tool actions, observations, and artifacts.
- Never fake a live value; label deterministic mock fallback explicitly.
- Keep the first 30 seconds understandable to a non-researcher.
