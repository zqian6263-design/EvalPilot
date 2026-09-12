# Market Validation Plan — Evidence Without Interview Dependency

Date: 2026-09-12

## Correction

Customer interviews are useful, but they are **not required by the competition
market-feasibility criterion** and are not a prerequisite for this submission.
This plan now validates the market through public evidence, executable product
integration, deployment, pricing anchors, and falsifiable business experiments.

## Primary evidence path

1. Public willingness to pay: vendor pricing across LangSmith, Braintrust,
   Langfuse, Confident AI, Galileo, Patronus, and Promptfoo.
2. Public adoption: GitHub stars, forks, releases, and ecosystem activity for
   open-source evaluation projects.
3. Integration: REST API, CI gate endpoint, machine exit codes, Markdown report,
   and reproducible run/investigation deep links.
4. Landing feasibility: deterministic offline demo, optional live LLM mode,
   self-host path, and bounded tool surface.
5. Business model: release audit, team subscription, and enterprise self-host.
6. Unit economics: model, compute, storage, and support cost formula.

Detailed evidence is recorded in `docs/MARKET_EVIDENCE_PACK.md`.

## Implemented market proof

- `GET /api/runs/{run_id}/gate` converts measured results into a release gate.
- Exit codes are machine-readable: `0 allow`, `1 review`, `2 block`.
- `scripts/ci-gate.ps1` makes the gate usable from CI without a custom UI.
- The report is downloadable as Markdown and every finding cites evidence.
- Existing runs and investigations can be reopened by stable deep links.

## Execution experiments to replace interviews

| Experiment | Output | Why it strengthens the market score |
|---|---|---|
| Run against a public open-source assistant workload | Cross-domain result | Proves generality beyond the bundled KB fixture |
| Naive score delta vs EvalPilot | Side-by-side decision | Makes competitive advantage concrete |
| Measure one live run's tokens, time, and estimated cost | Unit-economics card | Supports pricing and margin claims |
| Package one-command setup | Reproducible deployment | Proves actual landing feasibility |
| Integrate the gate into a sample CI workflow | Failing/passing build demo | Proves business-process integration |
| Publish a historical-release retrospective template | Self-serve onboarding artifact | Replaces the need for a live customer interview |

## Optional interview appendix

If real users become available, record the following without changing the main
strategy:

1. Last model, prompt, retrieval, memory, or tool change.
2. How release safety was decided.
3. What artifacts existed at decision time.
4. What failed or nearly failed.
5. Time and engineering cost of discovery or rollback.
6. Current tool and budget owner.
7. Willingness to run a historical-release retrospective.

No interview is required for the current submission. No interview result may be
invented.
