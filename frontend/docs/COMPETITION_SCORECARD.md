# Competition Scorecard — self-assessment

**Five official criteria, 20 points each, 100 total.**

**Status of this document.** Every score below is a **self-assessment, not a
judge's score**. A team scoring its own submission is the weakest possible
evidence, so each row separates what is *verified* (with a command and a
result) from what is *asserted* (with no evidence at all). The "gap" column is
the honest distance to the target, and the largest gap in this table is in
Market feasibility, where no amount of engineering will close it.

> **Placement note.** Same path-ownership constraint as
> `frontend/docs/MARKET_STRATEGY.md`: the frontend agent owns `frontend/**`, and
> `docs/` is owned elsewhere. Move this file to `docs/` if the submission
> requires it — nothing inside depends on its location.

## Summary

| # | Criterion | Current (self) | Confidence | Target | Gap |
|---|---|---|---|---|---|
| 1 | Technical feasibility | **16 / 20** | high | 18 | 2 |
| 2 | Market feasibility | **8 / 20** | **very low** | 13 | **5** |
| 3 | Comprehensive innovation | **14 / 20** | medium | 17 | 3 |
| 4 | AI large-model integration | **15 / 20** | medium | 18 | 3 |
| 5 | Track-dimension assessment | **14 / 20** | medium | 17 | 3 |
| | **Total** | **67 / 100** | | **83** | **16** |

The distribution is the point: the product is meaningfully ahead of the market
story. That is normal for a build-first team, and it is also the shape a
submission is most likely to lose points on.

**Evidence base for all rows** (unless a row names a different command):

```bash
npm --prefix frontend run build     # -> tsc -b && vite build, 70 modules, built in 1.73s
npm --prefix frontend test          # -> 7 files, 150 tests passed
npm --prefix frontend run typecheck # -> exits 1, TS5096; see row 1
```

Repository state at time of writing: branch `task/v3-market`, HEAD
`3d969b0e` (`docs: freeze live LLM runtime interfaces`, 2026-09-12).

---

## 1. Technical feasibility — 16 / 20

**Definition applied.** Can this be built and demonstrated, by these people, in
the time available, on a judge's machine?

### Evidence (verified)

| Claim | Evidence |
|---|---|
| The MVP builds from a clean checkout | `npm --prefix frontend run build` → `tsc -b && vite build`, 70 modules transformed, no errors. |
| The frontend suite is green | `npm --prefix frontend test` → **7 test files, 150 tests passed**, 21.6s. |
| The backend suite is green | `backend/README.md` records **115 passed** on the evaluation seam work. |
| End-to-end live path exists and was checked | `scripts/e2e-check.ps1` → **31/31**, per the E2E handoff record. |
| The scenario is narrow and runnable | `docs/SPEC.md` fixes one scenario (enterprise KB QA / support) and explicitly lists out-of-scope items. |
| The demo is resilient | The console renders a labelled mock fallback when the backend is offline (`PRODUCT.md`, "Demo-grade resilience"). |
| The unit of the system is small and testable | No framework; `backend/` + `frontend/` + `docs/` per `CLAUDE.md`. |

### Reality check (measured while writing this row)

`npm --prefix frontend run typecheck` **fails today**, and unlike the other
gaps in this table it also **fails on a clean checkout of `main`** — so it is a
pre-existing defect, not something this scorecard introduced. The cause is a
configuration inconsistency, not a code error:

```text
tsconfig.app.json(10,35): error TS5096: Option 'allowImportingTsExtensions'
  can only be used when either 'noEmit' or 'emitDeclarationOnly' is set.
tsconfig.node.json(9,35): error TS5096: Option 'allowImportingTsExtensions' ...
```

`tsconfig.app.json` sets `"noEmit": true`, and the `typecheck` script
overrides it with `--noEmit false`. The two flags are mutually exclusive, so
this script can never have passed. **`npm run build` is the working gate** and
it does run `tsc -b`.

> **Trap, found while verifying this row.** The obvious fix — drop
> `--noEmit false` so `--noEmit` is honoured — *appears* to work and is worse
> than the bug. Under `tsc -b`, `--noEmit` on the command line does not
> suppress emit: every source file gains a sibling `.js`, including
> `vite.config.js`. Vite then resolves the generated `.js` in preference to
> `vite.config.ts`, so the build silently uses a stale config — and the probe
> edits made while chasing that made it look as though a stylesheet was not
> being bundled when it was. Any fix here must leave `git status` clean of
> stray `.js` under `src/`.

Recorded because an unverified claim in a submission is a feasibility risk,
and this one is cheap to fix once the trap is known.

### Gap (target 18)

- Two unverified claims carried in the pitch: the "repeated runs reproduce the
  detection" claim and the Ruby-vs-Python bootstrap-priority claim in
  `backend/README.md`. Neither is backed by an artifact in this repository.
- The demo runs on bundled fixtures. The *live* path is exercised by
  `e2e-check.ps1` but has not been demonstrated to a fresh third party.
- `npm run typecheck` is broken (above).

### Actions

| # | Action | Verification |
|---|---|---|
| 1.1 | Fix the `typecheck` script — it currently pairs `--noEmit false` with `allowImportingTsExtensions` and cannot pass. **Do not fix it by honouring `--noEmit` under `-b`**: that emits sibling `.js` files next to every source file, and Vite then resolves the generated `vite.config.js` in preference to `vite.config.ts`, silently building with a stale config. This was attempted and reverted. | `npm --prefix frontend run typecheck` exits 0, `npm run build` still exits 0, and `git status` shows no stray `.js` under `src/`. |
| 1.2 | Either remove the "reproducible across repeated runs" claim from `COMPETITION_PITCH.md`, or run the same comparison twice and record both reports as artifacts. | Two report JSONs, byte-comparable, committed or attached. |
| 1.3 | Either back the bootstrap-priority claim with a measurement, or delete it. | A committed command + output, or a deleted line. |
| 1.4 | Run the clean-start checklist in `docs/ACCEPTANCE.md` from a genuinely fresh shell, on a machine that is not the dev machine, and paste the transcript. | The transcript, with any failure left in. |

---

## 2. Market feasibility — 8 / 20

**Definition applied.** Is there a buyer, a budget, a recurring need, and a
route to them?

### Evidence

| Type | Content |
|---|---|
| Working product | Yes — a functioning comparison engine over a 26-scenario corpus. |
| Documented hypothesis | Yes — `frontend/docs/MARKET_STRATEGY.md` (ICP, buyer, trigger, pain, alternatives, differentiation, pricing, ROI model, GTM, 90-day plan). |
| Customer conversations | **0** |
| Design partners | **0** |
| Pilots | **0** |
| Paying customers | **0** |
| Revenue | **0** |
| Validated pricing | **0** — every number in the pricing section is a hypothesis. |
| Validated ROI | **0** — the ROI model's output band spans more than two orders of magnitude, and two of its multiplicands are unmeasured. |

### Why this is 8 and not higher

**There is no external evidence of demand of any kind.** The strategy document
is a well-structured plan to *obtain* that evidence; it is not the evidence.
The `COMPETITION_PITCH.md` "Business model hypothesis" section is honest about
being a hypothesis, and the market document is honest about zero traction — but
honesty about having no evidence does not score as evidence.

The only things keeping this above a floor score are: the buyer and the
trigger are named concretely (not "AI teams"), the alternatives analysis is
specific enough to be falsifiable, and the plan includes explicit kill
conditions. That is a *credible* market hypothesis. It is not a *demonstrated*
one.

### Why this cannot be inflated

No engineering action moves this score. Every point available above 8 requires a
named human being outside the team to say something. The temptation will be to
substitute a compelling pitch and a polished demo for that conversation. Doing
so would be a submission that scores itself on a claim it cannot support.

### Gap (target 13)

Five points, achievable only through the 90-day plan's Day 0–30 tasks. A
realistic competition-window version:

| # | Action | Verification | Realistic cost |
|---|---|---|---|
| 2.1 | Complete **10** ICP conversations (Day 0–30, task 1). | Written notes, one per call, with the §3 trigger question answered explicitly. | 2–3 weeks of founder time. |
| 2.2 | In those calls, extract **two** retrospective numbers: `p_bad_release` and `cost_of_bad_release`. | Two real data points replacing assumptions in the ROI model. | Free, but requires the calls in 2.1. |
| 2.3 | Confirm or kill the budget line hypothesis in §2 of the market document. | A named budget line from a real conversation, or a written "no such line exists". | Free. |
| 2.4 | Secure **one** design partner who has already had the trigger fire. | A signed (free or at-cost) pilot agreement naming the application and the corpus. | The largest single ask in this plan. |
| 2.5 | Re-run the tool on that partner's **already-shipped** release and compare the verdict to what actually happened. | A retro-diagnosis artifact: agreement or disagreement. Disagreement is a product bug and a finding. | 1–2 weeks engineering. |
| 2.6 | Replace this scorecard's market row with whatever 2.1–2.5 produced, including if it is bad news. | This document, revised. | — |

**Honest expectation.** Inside a competition preparation window, 2.1–2.3 are
realistic, 2.4–2.5 may not be. If only the conversations happen, the correct
score is **10–11**, and the correct thing to say is "no traction; here is what
we learned from ten conversations," which is worth more than a higher number
that cannot be defended.

---

## 3. Comprehensive innovation — 14 / 20

**Definition applied.** Is the core idea non-obvious, is it the product's
substance rather than a wrapper, and is the novelty real rather than claimed?

### Evidence (verified)

| Innovation | Where it lives | Why it is not a wrapper |
|---|---|---|
| **Causal comparison design** — matched cases paired by `scenario_id`, difficulty held identical across versions, so a harder test set cannot masquerade as a worse model. | `backend/evalpilot/evaluation/` (the matched-case engine the runner actually calls) | This is a claim about *the comparison*, not about a metric. A score-dashboard competitor cannot copy it without changing what it reports. |
| **Counterfactual root-cause replay** — replays a failing scenario under altered interventions and reports which one would restore the result. | `backend/evalpilot/` counterfactual replay engine; rendered in the investigation workspace, with `root cause` / `partial` / `no effect` / `inconclusive` verdicts. | Most eval tooling stops at "this case failed". Attributing the failure to a specific knob is a different product. |
| **Root-cause memory** — recalls prior incidents by fingerprint and terms, so a repeat failure is recognised rather than rediscovered. | Investigation workspace, "Recalled incidents" panel | An accumulating asset, not a feature. |
| **Uncertainty-aware verdict that is allowed to say "inconclusive."** | `regression_detected` (per-scenario) vs `regression_confirmed` (aggregate, CI must clear the threshold); `DEFAULT_REGRESSION_THRESHOLD = 0.05` in `backend/evalpilot/evaluation/comparison.py` | The product's own claim is that it separates a real regression from noise. A verdict that cannot say "I don't know" cannot substantiate that claim. |
| **Evidence chain on every finding** — evidence ids, trace, and evaluator rationale attached to each finding. | `Finding.evidence_ids` in the frozen contract; report and drawer render it | Standard-sounding, but it is what makes the report defensible rather than decorative. |
| **The strip-chart interface** — a regression is drawn as a geometric event (the candidate trace leaving the pre-printed tolerance band), not as a badge colour. | `frontend/src/components/Tape.tsx`, `frontend/styles/tape.css`; rationale in `frontend/DESIGN.md` | Deliberately refuses the category default (dark dashboard, KPI tiles, one glowing accent). Not itself an *innovation in evaluation*, but the demo's legibility depends on it. |

### Gap (target 17)

**The hard truth about this row: the mechanism is standard statistics.** Matched
pairs, repeated sampling, and bootstrap confidence intervals are textbook, and
the open-source harnesses listed in the market document's alternatives section
already ship the primitives. If "innovation" means novel technique, this scores
lower than 14. The 14 reflects **design discipline and productization**, not
invention.

Three concrete gaps:

1. **The counterfactual replay is demonstrated on seeded data, not validated
   against a real defect.** Its verdicts are plausible; plausibility on
   fixtures is not correctness.
2. **The memory asset has no real history in it.** It is the one compounding
   moat, and it is empty.
3. **The "already-shipped release" check has never been run.** The strongest
   possible evidence for the innovation claim is a retro-diagnosis where the
   tool agrees with what actually happened. That experiment has not happened.

### Actions

| # | Action | Verification |
|---|---|---|
| 3.1 | Run the retro-diagnosis (2.5) and publish the result **whether or not it agrees**. | An artifact comparing the tool's verdict to the known outcome of a real shipped release. |
| 3.2 | Publish a direct head-to-head: same candidate version, same corpus, EvalPilot's verdict vs an aggregate-score-delta tool's. | Two verdicts side by side, showing the case where they disagree. This is the differentiation claim made falsifiable. |
| 3.3 | Write down the innovation claim **without** the word "causal" (which is overloaded in ML), and check whether the claim survives the rewrite. | The rewritten claim, in the pitch. If it collapses, the pitch was leaning on the word. |
| 3.4 | Disclose the statistical power limit as a *product property*, not a caveat — minimum cases needed for the aggregate verdict to resolve, derived from the engine. | A stated minimum-N with the derivation. This turns a weakness into evidence of rigor. |

---

## 4. AI large-model integration — 15 / 20

**Definition applied.** Is the LLM load-bearing in the product, are the roles
explicit, and does the system degrade honestly when the model is absent?

### Evidence (verified)

| Claim | Evidence |
|---|---|
| Explicit LLM roles, not "an LLM somewhere" | Planner (risk hypotheses), judge (rubric rationale), report narrative — named in `docs/V3_LLM_INTERFACES.md` and `COMPETITION_PITCH.md`. |
| A frozen provider seam | `LLMProvider` with `complete_json(messages, schema, timeout) → dict`; OpenAI-compatible `/chat/completions`; injectable; **no network in unit tests**. |
| Honest failure behaviour | Any LLM failure falls back to deterministic behaviour **with an explicit warning**, recorded as `data.fallback_reason`. |
| Deterministic-vs-model steps are distinguishable | `data.source = "llm"` carries `model` and `llm_call_id`; deterministic steps carry `data.source = "deterministic"`. |
| The model cannot override measurement | Contract: "the release decision remains evidence- and counterfactual-driven. The LLM may propose hypotheses and explain results; it may not override the measured replay verdict or invent evidence." |
| No chain-of-thought leakage | "No private chain-of-thought is displayed; only structured hypotheses, rationales, and actions." Rendered as structured actions (tool name, arguments, artifact) — `frontend/src/InvestigationWorkspace.tsx` and its 11 tests. |
| Secrets are not exposed | `GET /api/runtime` returns `mode`, `llm_configured`, `model`, `base_url_host` — **not** the key. Contract requirement. |
| The frontend already distinguishes the modes | Runtime badge renders `LIVE LLM · <model>` or `DETERMINISTIC`. |

### Gap (target 18)

1. **No evidence of a real model ever answering.** Every LLM-shaped output in
   this repository is deterministic fixture data. Live mode has a contract, a
   seam, and a fallback path; it has no recorded successful call.
2. **The judge has never been validated against a human.** Its scores are
   trusted by construction.
3. **No cross-provider evidence.** "OpenAI-compatible" is a claim; only one
   provider has ever been named.
4. **Token cost is unmeasured.** The pricing hypothesis in the market document
   claims usage pricing sits below inference cost. That has never been
   computed.

### Actions

| # | Action | Verification |
|---|---|---|
| 4.1 | Record **one** live run against a real endpoint (`EVALPILOT_LLM_MODE=live`) and commit the resulting report artifact. | A committed report with `data.source = "llm"`, a model id, and an `llm_call_id`. |
| 4.2 | Record **one** deliberate failure (invalid key, or a forced timeout) showing the deterministic fallback with `data.fallback_reason`. | The fallback warning visible in the artifact. |
| 4.3 | Handle rubric disagreement explicitly: when the LLM judge and the deterministic checks disagree, the report says so and shows both. | A fixture where they disagree, rendered as two rows rather than one merged score. |
| 4.4 | Measure tokens and cost for one full comparison and put the number into the pricing hypothesis. | One measured number replacing an assumption. |
| 4.5 | Run the same comparison against a **second** OpenAI-compatible provider. | Two artifacts from two providers, same contract. |

---

## 5. Track-dimension assessment — 14 / 20

**Definition applied.** The AI+Super Agent track asks for **autonomous end-to-end
execution** and a **verifiable deliverable**. Not a demo of a feature — an agent
that does the whole job and produces something a person can check.

### Evidence (verified)

| Requirement | Evidence |
|---|---|
| Autonomous, end-to-end | The investigation workspace runs without step-by-step human input: intake → plan → probe → counterfactual replay → decision → report. |
| The loop is closed | `docs/SPEC.md` product loop: ingest brief → risk map → generate cases → execute tools → capture evidence → evaluate → compare → emit report. |
| Every step is auditable | Findings carry evidence ids; the report and drawer render them; the timeline shows structured actions with arguments and artifacts. |
| A verifiable deliverable exists | `report.md`, downloadable from the transport's own text; the button reports what it wrote ("lines written"), so a silent failure is not possible. |
| The verdict is honest | Measured: `regression_confirmed = true` on the demo, backed by paired-bootstrap evidence — mean score fell **0.173**, **95% CI −0.288 to −0.077**, entirely below the **−0.050** threshold; 8 scenarios regressed against their own baseline; 18 controls scored identically (`backend/README.md`; engine constant `DEFAULT_REGRESSION_THRESHOLD = 0.05` in `backend/evalpilot/evaluation/comparison.py`). |
| Bounded tool surface | Python tool is allowlisted and disabled unless explicitly enabled (`CLAUDE.md` non-negotiable #4). |

> **Correction to a stale note.** An earlier handoff recorded the demo's
> aggregate verdict as *inconclusive* (26 cases, mean −0.077, CI −0.173 to
> 0.000). That is no longer true: the fixture set was later expanded and the
> demo now reports a **confirmed** regression with the figures above. Do not
> repeat the stale version in the pitch.

### Gap (target 17)

1. **The submission materials are not finished, and one of them is missing.**
   `Acceptance checklist → Submission materials` requires a 2–3 minute demo
   video publicly accessible **without login**. That artifact does not exist,
   and no engineering work creates it.
2. **The demo is verified on fixtures, not on a stranger's machine.** The
   clean-start checklist in `docs/ACCEPTANCE.md` has not been run by someone
   who did not build the product.
3. **The autonomy claim has a soft edge:** the deterministic demo path does not
   require a model at all, so the "agent" is autonomous but the "AI" part of
   the track's name is optional in the demo. Live mode is where that changes,
   and live mode is unexercised (see row 4).
4. **The demo's statistical power is not stated.** The aggregate verdict now
   resolves on this corpus and the pitch should say how much data that takes —
   otherwise the first real corpus that cannot resolve looks like a product
   failure rather than a stated limit.

### Actions

| # | Action | Verification |
|---|---|---|
| 5.1 | Record the 2–3 minute video, upload it publicly, and verify it plays with no login in a private browser window. | The URL, opened logged-out. |
| 5.2 | Run the full clean-start checklist from `docs/ACCEPTANCE.md` on a machine that is not the dev machine, on a fresh shell. | The transcript, failures included. |
| 5.3 | Do the §3.1/§4.1 live run with the model actually answering, so the video shows `LIVE LLM · <model>` rather than a deterministic badge. | The badge visible in the recording. |
| 5.4 | State the minimum-N the aggregate verdict needs, in the pitch. | One sentence with the derivation. |
| 5.5 | Verify the two deep links a presenter will actually use — `#report` and `#console&demo` — on a clean backend, and screenshot both. | Two screenshots. |

---

## Cross-cutting: the three things most likely to lose points

1. **An overclaimed number.** The single highest-risk item in the whole
   submission is any figure that cannot be reproduced by a judge running the
   commands in `docs/ACCEPTANCE.md`. Three such claims exist today (row 1 gap,
   and the stale inconclusive-verdict note above). Delete or verify them.
2. **Mistaking the demo for the market.** The demo is genuinely good and it is
   easy to let it stand in for validation. The market row is 8/20 and no
   engineering action moves it.
3. **Skipping the video.** It is the largest single-points-per-hour item
   available, it is required by the acceptance checklist, and it cannot be
   replaced by a better demo.

## What this scorecard is not

- Not a judge's assessment. It is the team grading itself, which is the least
  reliable evidence in the repository.
- Not stable. Rows 2, 4, and 5 can move within days; row 3 can move only with
  a real experiment; row 1 is mostly bookkeeping.
- Not a commitment. Every target above assumes the actions in its own table are
  actually completed and verified. If they are not, the current score is the
  honest one.
