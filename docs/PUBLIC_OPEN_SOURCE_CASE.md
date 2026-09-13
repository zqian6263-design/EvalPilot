# Public Open-Source Pipeline Regression Case

Date: 2026-09-13

## Public dependency

- Project: `deepset-ai/haystack`
- Version: `haystack-ai 3.1.1`
- Source: https://github.com/deepset-ai/haystack
- License: Apache-2.0

EvalPilot evaluates an external HTTP SUT whose retrieval core is the real
Haystack pipeline:

```text
DocumentSplitter
  -> InMemoryBM25Retriever
  -> DocumentJoiner
  -> GroundedDocumentReranker
  -> grounded answer composer
```

## Controlled candidate patch

The candidate revision keeps the same public pipeline but introduces two
application-level changes:

1. a compression policy removes mandatory escalation, safety, and security
   clauses;
2. a security-guard policy is disabled for credential-injection prompts.

This is an isolated controlled patch around a public open-source dependency. It
is **not** a claim that upstream Haystack has these defects.

## Workload

- 26 matched enterprise-support scenarios.
- 18 exact controls.
- 8 controlled regressions.
- Baseline revision: `v1.0-baseline`.
- Candidate revision: `v1.1-candidate`.

## Result

```text
same-version control:
  regressions = 0
  mean delta = 0

baseline vs candidate:
  regressions = 8 / 26
  mean delta = -0.173
  95% CI = -0.288 to -0.077
  decision = BLOCK / CRITICAL
```

The investigation then replays eight failures through the HTTP boundary:

- seven recover with `compression_disabled`;
- one credential disclosure recovers with `security_guard_enabled`.

## Reproduce

```powershell
.\scripts\sut-e2e-check.ps1
```

Evidence is written to `.runtime/sut-e2e-*/summary.json`.

## Limitation

This demonstrates compatibility with a public open-source retrieval stack under
a controlled patch. A future P2+ case should select an actual upstream patch or
regression from the public repository and preserve its commit hash.
