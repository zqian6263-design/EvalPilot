# EvalPilot V2 Interfaces

This contract freezes the autonomous-investigation layer added after the confirmed-regression demo. Change this document before changing shared field names.

## User-facing goal

Turn a completed regression run into an autonomous release investigation:

```text
release objective
-> risk hypotheses
-> recalled incidents
-> follow-up probes
-> counterfactual replay
-> root cause
-> release decision
-> exportable evidence report
```

The UI must show structured actions and artifacts. It must not expose private model chain-of-thought.

## Core entities

```text
Investigation
  id: uuid
  run_id: uuid
  objective: str
  status: queued | planning | investigating | replaying | deciding | completed | failed
  summary: str
  risk_level: low | medium | high | critical
  decision_verdict: allow | review | block
  created_at: datetime
  completed_at: datetime | null

InvestigationStep
  id: uuid
  investigation_id: uuid
  parent_id: uuid | null
  sequence: int
  kind: risk | memory | probe | tool | observation | counterfactual | decision
  title: str
  status: pending | running | completed | failed
  detail: str
  data: object
  evidence_ids: list[uuid]
  created_at: datetime
  completed_at: datetime | null

HistoricalIncident
  id: str
  title: str
  symptoms: list[str]
  tags: list[str]
  root_cause: str
  resolution: str
  guard_scenario_id: str | null
  occurred_at: datetime

MemoryMatch
  incident_id: str
  score: float (0..1)
  reason: str
  matched_terms: list[str]

CounterfactualExperiment
  id: uuid
  investigation_id: uuid
  scenario_id: str
  intervention: str
  original_score: float
  counterfactual_score: float
  delta: float
  confidence: float
  verdict: root_cause | partial | no_effect | inconclusive
  evidence_ids: list[uuid]
  rationale: str
  created_at: datetime

ReleaseDecision
  verdict: allow | review | block
  risk_level: low | medium | high | critical
  summary: str
  blocking_findings: list[uuid]
  recommended_actions: list[str]
  confidence: float
  generated_at: datetime
```

## HTTP API

Base path `/api`

- `POST /investigations`
  - body: `{ run_id, objective }`
  - creates a queued investigation
- `POST /investigations/{id}/start` -> `202`
- `GET /investigations/{id}` -> `{ investigation, steps, memory_matches, counterfactuals, decision }`
- `GET /investigations/{id}/events` -> sequenced progress events; reuse the run-event envelope
- `GET /investigations/{id}/report.md` -> final Markdown report
- `GET /memory/incidents?query=&tag=` -> historical incidents and optional matches
- `GET /demo/investigation` -> deterministic demo metadata only; no side effects

## Deterministic demo behavior

The confirmed 26-case regression run is the entry point. The investigation must eventually produce:

1. at least three risk hypotheses;
2. at least two memory matches from the seeded incident history;
3. follow-up probe steps for every regressed scenario;
4. one counterfactual experiment per critical finding, or a justified grouping;
5. `compression_disabled` as the dominant root-cause intervention for dropped clauses;
6. `security_guard_enabled` as the root-cause intervention for credential disclosure;
7. OOD intervention vocabulary includes `retrieval_top_k_restored`, `unicode_normalization_restored`, `memory_scope_restored`, and `cache_bypass_enabled`;
7. `decision.verdict = block`;
8. an exportable Markdown report whose claims cite evidence ids.

No external API is required. The implementation must have a live-agent seam but remain reproducible offline.

## Frontend contract

Add an `Investigation` workspace with:

- objective intake and “Start autonomous investigation” action;
- live investigation timeline/tree;
- risk hypotheses and follow-up probes;
- recalled historical incidents;
- counterfactual root-cause panel with before/after scores;
- release decision card;
- evidence drill-down;
- report download action;
- deterministic mock fallback when the backend is offline.

The existing two-version tape, confirmed-regression verdict, case table, and evidence drawer remain available.

## Safety and evidence rules

- A finding or root-cause claim must cite persisted evidence.
- Tool traces must be displayed as structured actions, not hidden reasoning.
- External write actions are out of scope. Export and local reports are allowed.
- Every demo number must come from the running service or an explicitly labelled mock fallback.
