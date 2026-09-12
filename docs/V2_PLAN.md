# V2 Delivery Plan

## Workstreams

| Stream | Branch | Scope | Output |
|---|---|---|---|
| Investigation backend | `task/v2-investigation` | persistence, memory, events, decisions, Markdown export | runnable V2 API |
| Counterfactual engine | `task/v2-counterfactual` | replay with interventions and root-cause classification | injectable engine |
| Investigation frontend | `task/v2-frontend` | timeline, memory, root cause, decision, report UI | self-contained workspace |

## Integration order

1. Merge the counterfactual engine because it is a pure dependency.
2. Merge the investigation backend and inject the real counterfactual engine.
3. Merge the investigation frontend and wire it into the existing console.
4. Run Codex integration pass: unify contracts, add V2 E2E checks, update pitch and screenshots.

## V2 acceptance

- A completed confirmed-regression run can create an investigation.
- The investigation produces risk hypotheses, memory matches, probes, and counterfactuals.
- `compression_disabled` is identified as the dominant cause of dropped-clause failures.
- `security_guard_enabled` is identified for credential disclosure.
- Release decision is `block` with evidence-backed reasons.
- Markdown report downloads successfully.
- Frontend can run the complete investigation from objective intake to decision.
- Offline deterministic demo remains available.
- No external API is required and no hidden chain-of-thought is shown.
- Backend tests, evaluator tests, frontend tests, build, startup check, and V2 E2E all pass.

## Demo polish

- Keep the confirmed regression tape as the first proof.
- Add a clear transition: “The regression is confirmed. Now investigate why.”
- Show structured agent actions, not a chat transcript.
- Use memory recall to demonstrate learning across releases.
- End on the release decision and exported report.
