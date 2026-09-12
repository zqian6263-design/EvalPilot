# Market Strategy — Strategy Hypothesis (pre-validation)

**Status: hypothesis, not validated.** Nothing in this document has been
confirmed by a customer, a pilot, a paid engagement, or a single external
conversation. It is the set of beliefs the team intends to test, written down so
the tests can falsify them. Where a number appears it is either a *target*, a
*range*, or a figure measured inside this repository — never a market result.

> **Placement note.** Under the repository's per-agent path ownership
> (`frontend/**` for the frontend agent; `docs/` owned elsewhere and read-only),
> this document lives at `frontend/docs/MARKET_STRATEGY.md` rather than
> `docs/MARKET_STRATEGY.md`. If the submission requires it at `docs/`, move the
> file — no path inside it depends on its location.

## 0. Zero-traction disclosure

Read this before anything below.

| Question | Honest answer |
|---|---|
| Paying customers | **0** |
| Pilots run with an external party | **0** |
| Design partners | **0** |
| External users of the product | **0** |
| External interviews conducted | **0** |
| Letters of intent | **0** |
| Revenue | **0** (none, any currency) |
| LOIs, waitlist, inbound leads | **0 / none** |
| Production deployments | **0** |

What *does* exist:

- One working end-to-end implementation in this repository, validated against
  its own bundled fixture corpus (`backend/README.md`: 26 matched scenarios ×
  2 versions = 52 test-case rows; baseline passes 26/26, candidate 18/26).
- The competition demo itself. A demo is not a customer.
- This document, which is a plan.

**Any claim in this file that is not a target, a range, or a measurement from
this repository is an assumption and is marked as one.** If a later revision of
this document reports traction, the number must be traceable to a named
counterparty, or it does not go in.

## 1. ICP — ideal customer profile

**Primary ICP (the one to test first).**

A **platform / AI engineering team of 5–40 engineers** inside a company that
already ships a **customer-facing LLM application** on a knowledge base or
support corpus — RAG over help-centre articles, policy documents, or product
manuals.

Qualifying signals (structural, observable from outside):

1. The assistant answers questions from a **curated internal corpus**, not from
   the open web. This is what makes "did it lose a citation?" a measurable
   question rather than a taste question.
2. The application **changes at least twice a month** — retrieval settings,
   prompt revisions, model or provider swaps, context assembly, chunking.
   Change frequency is what converts an evaluation from a project into a
   recurring cost.
3. **A human is accountable for the quality call** and has to write down why:
   a release manager, a QA lead, a platform lead whose name is on the release.
   Someone who must defend the decision to a different person.
4. Deployment happens where **regressions are expensive to discover in
   production**: regulated advice, billing, health, security, onboarding flows.

**Anti-ICP — deliberately not the target.**

- Teams with no LLM product in production (nothing to regression-test).
- Teams whose assistant is a general chatbot with no ground-truth corpus
  (there is no citable answer to lose, so the whole causal design is moot).
- Research groups optimizing a metric on a public benchmark. They have a
  different problem — absolute score, not controlled comparison — and a
  different tool set.
- Anyone shopping for a general-purpose agent framework. EvalPilot is not one.

## 2. Buyer

Two roles, and they are not the same person. Confusing them is the most likely
early go-to-market error.

| Role | Who | What they are buying | What makes them say no |
|---|---|---|---|
| **Champion / user** | AI platform lead, QA lead, eval engineer | The evidence artifact. "I can show my director *why* we blocked the release, with the case, the trace, and the rationale." | If the report is not defensible to a skeptical engineer, the whole value evaporates. |
| **Economic buyer** | Engineering director / VP Engineering, occasionally Head of QA | Release risk reduction and engineering hours returned. Buys *fewer bad releases*, not *a nicer dashboard*. | Cannot articulate the loss they are avoiding. No budget line for "eval". |

**Budget hypothesis (untested):** the purchase does not come from a new
"evaluation tool" line. It comes from one of two existing lines — **QA /
release-engineering tooling**, or **the LLM application's own platform/infra
budget**, where a per-seat eval tool is a rounding error against model spend.
The first commercial entry point is therefore a **release-gate report bought for
one specific release**, not a platform subscription.

**Who is *not* the buyer:** the individual engineer who will use it daily.
They are the champion. Treating them as the buyer produces free trials that
never convert.

## 3. Trigger — the moment the problem becomes a purchase

The trigger is an **event**, not a general dissatisfaction with evaluation.

**Primary trigger:** *a release is blocked, delayed, or rolled back because
nobody could say whether the candidate version was worse.* Concretely: a
model/prompt/retrieval change that scored better on the team's dashboards, and
then produced a support escalation, a factually wrong answer to a customer, or
a lost citation in an audit.

**Secondary trigger:** a **forced change** with a deadline — a provider
deprecating a model, a cost-reduction mandate requiring a smaller model, a
security review requiring an inference path change. The team must migrate and
must prove the migration did not break quality.

**Why the trigger matters more than the pain:** eval pain is chronic and
tolerable. Teams live with it for years. The purchase happens in the two-week
window after an incident, when someone has to explain what happened. The 90-day
plan in §7 is built to be *reachable* inside that window.

**Disqualifying non-trigger:** "we know our eval is bad, we'll fix it next
quarter." This has no date and no owner. It is not a pipeline entry.

## 4. Pain

Stated as the buyer would state it:

1. **"We cannot prove this change is safe."** Public benchmarks do not describe
   this product. The team's own test set is ten hand-written examples that
   everyone has stopped trusting.
2. **"A score moved and we don't know why."** Aggregate before/after deltas
   conflate three different things — a real regression, a genuinely harder
   test set, and sampling noise. A dashboard that reports one number cannot
   separate them.
3. **"The evidence doesn't survive scrutiny."** When the release is
   questioned, there is no artifact. Someone re-runs the examples by hand, days
   later, and gets a different answer.
4. **The cost is paid in the wrong currency.** Not primarily tool spend —
   engineer-hours spent hand-testing, and the much larger cost of a bad release
   discovered in production.

**Honest caveat:** pain magnitude is *assumed*, not measured. The ranking above
is a hypothesis about which pain is sharpest. §7's first task is to find out
whether it is wrong.

## 5. Alternatives — what the buyer does today

Listed in the order buyers actually adopt them.

| Alternative | Why it wins today | Where it structurally fails |
|---|---|---|
| **Do nothing / manual spot-checking** | Free, familiar, no procurement. | No repeatability, no evidence artifact, no way to separate a real drop from a harder sample. It works right up until someone asks for proof. |
| **Spreadsheets + hand-written test sets** | Cheap, owned by the team, fully transparent. | Does not scale past ~20 cases; no repeat sampling; drift is invisible; nobody re-runs it under deadline. |
| **Generic eval SaaS (prompt/eval platforms)** | Real product, real dashboards, easy to try. | Optimized for **absolute score on a fixed set** — not controlled comparison across versions. They report that a number moved; they do not establish that the *change caused* it. |
| **Open-source eval harnesses** | Free, extensible, engineer-friendly, no procurement. | You assemble the comparison design yourself: matched cases, repeat sampling, uncertainty, evidence linkage. The harness runs the model; it does not design the experiment. |
| **Public benchmarks (MMLU-style)** | Credible-looking, one number, sortable across teams. | Measures general capability, not *this product's* behaviour on *this corpus*. A benchmark score going up while the product regresses is a normal outcome. |
| **Cloud provider's own eval service** | Tight integration, no new vendor, already in the contract. | Single-provider, and typically reports aggregate metrics. Locked to one model family — precisely the case where a cross-version comparison matters most. |
| **Internal home-grown harness** | Exactly fits the team, owned end-to-end. | Expensive to build, usually dies at the statistics: the person who built it leaves, and nobody trusts the number enough to gate a release on it. |

**The honest read:** the real competitor is **"do nothing" plus a spreadsheet**,
and it is a strong competitor because it is free and it feels adequate. Generic
eval SaaS is the competitor in a *funded* evaluation; open-source is the
competitor in a *technical* evaluation. Beating the spreadsheet requires the
trigger in §3 to have already fired.

## 6. Differentiation

**The claim.** EvalPilot is a *causal* regression-evaluation layer, not another
eval dashboard. It separates a real regression from a harder test set and from
sampling noise, and it can refuse to call a noisy change a regression.

**The mechanism** (from `docs/SPEC.md` and `PRODUCT.md`; implemented and
partially exercised in this repository):

1. Matched cases — the same scenario runs on both versions, paired by
   `scenario_id`. An unmatched comparison is not a comparison.
2. Repeated samples — a flag that does not survive repeats is reported as a
   single-sample flag, not as a regression.
3. Controlled comparison — difficulty is a property of the case, held identical
   across versions, so a harder set cannot masquerade as a worse model.
4. Evidence chain — every finding carries evidence ids, and every claim is
   traceable to input, output, tool trace, and evaluator rationale.
5. Uncertainty-aware verdict — the aggregate verdict is allowed to come back
   **inconclusive**. This is a feature and it is demonstrated: the demo's own
   aggregate comparison does not clear its threshold (see §9), and the report
   says so instead of dressing it up.

**Why a neighboring eval tool cannot copy it cheaply.** The claim rests on the
*comparison design*, not on the metric. A tool whose product is a score
dashboard would have to change what it reports — including reporting that it
cannot tell. That is an uncomfortable product change, not a feature addition.

**Honest limits of the moat (read this as the bearing on the scorecard):**

- The mechanism is **not defensible by itself**. Matched pairs, repeated
  sampling, and bootstrap confidence intervals are standard statistics that any
  competent team could implement in a sprint, and the open-source harnesses in
  §5 already have the primitives. The differentiation is **design discipline and
  evidence hygiene**, not proprietary technology.
- The **real, compounding moat is the accumulated regression memory**: the
  run history, the recalled incident fingerprints, the counterfactual replays
  that tell the next engineer which knob caused which failure. That asset takes
  time and repetition to build, and it is the only thing here that gets harder
  to copy the longer it runs.
- **Today that memory asset is demonstrated on seeded data**, not on a real
  customer's history. Its defensibility is a hypothesis. Stated plainly: the
  moat is a *plan* for a moat.

## 7. Pricing hypothesis

**Every number below is a hypothesis to be tested in the pilot. None is
validated pricing.** No customer has been quoted, and no price has been paid.

**Shape: two-part, priced to the release.**

| Component | Hypothesis | Rationale |
|---|---|---|
| **Pilot / first engagement** | **Fixed-fee, one project.** Range **¥30k–80k** (≈ $4k–11k) for a scoped engagement: one application, one corpus, a configured baseline/candidate comparison, and a release-gate report. | Converts the §3 trigger into a purchase order without a platform decision. Buys the team's time to configure the target system against real data. |
| **Team subscription** | **Per-seat or per-project, annual.** Range **¥8k–25k / seat / year** (≈ $1.1k–3.5k), floor of 3–5 seats. | The champion and the reviewer both need access; a floor prevents a one-seat deal that never spreads. |
| **Usage** | **Per executed comparison.** Metered on matched scenarios × repeats × versions, priced to sit *below* the model-inference cost the run itself consumes. | The cost is dominated by the LLM calls the run makes. Pricing above inference cost makes the tool look like a tax on running it. |

**Why not usage-only:** it makes the tool's cost scale with the customer's own
change frequency, which penalizes exactly the behaviour the product wants
(more frequent releases). The subscription is the anchor; usage is a guardrail
against pathological runs.

**Why not free-tier-led:** the buyer in §2 does not adopt release-gating
infrastructure from a free tier. A free tier attracts the anti-ICP in §1.

**Falsification criterion for this whole section.** If, after ten qualified
conversations (§8), no champion can name the budget line in §2 that would pay
for it, the pricing shape is wrong — not the price. Re-derive the shape before
touching the numbers.

## 8. Adjustable ROI model

**How to read this model.** It is a *sensitivity model*, not a forecast. It has
one output — the annual value of one avoided bad release, compared against the
annual tool cost — and every input is deliberately adjustable. The bands below
are the high/low of the output as the two lowest-confidence inputs move across
their honest ranges. **Nobody has measured these inputs on a real deployment.**
Replace them with a customer's own numbers in the first pilot conversation;
until then, treat the output as a shape, not a quantity.

### Model

```
annual_value  =  releases_per_year × p_bad_release × p_detected × cost_of_bad_release
annual_cost   =  (seats × seat_price) + (releases_per_year × cost_per_comparison)
net           =  annual_value − annual_cost
```

### Inputs

| Input | Symbol | Low | High | Confidence | Source |
|---|---|---|---|---|---|
| Releases per year (version changes that could regress) | `releases_per_year` | 24 | 104 | medium — derived from the ≥2/month qualifier in §1 | assumption |
| Share of releases that regress quality | `p_bad_release` | 5% | 20% | **low — no measurement exists** | assumption |
| Share of those the tool actually catches before production | `p_detected` | 30% | 70% | **low — no measurement exists**; bounded above by the tool's own demonstrated statistical power | assumption |
| Cost of one bad release reaching production | `cost_of_bad_release` | ¥50k | ¥500k | **low — the widest and most load-bearing input** | assumption |
| Seats | `seats` | 3 | 10 | medium — floor from §7 | assumption |
| Seat price / year | `seat_price` | ¥8k | ¥25k | low — §7 hypothesis | assumption |
| Comparisons / year | — | = `releases_per_year` | | medium | assumption |
| Cost per comparison | `cost_per_comparison` | ¥20 | ¥200 | medium — dominated by the run's own LLM inference | assumption |

**Cost of a bad release, decomposed** (so a pilot can fill it in per line
instead of guessing a lump sum): engineer-hours to diagnose and hotfix; support
or escalation cost per affected customer × affected customers; engineering
hours of the delayed release itself; and — for regulated or advisory-facing
deployments — any compliance cost. Only the first two are usually quantifiable
at all.

### Worked band

At the model's own low end (`24 releases × 5% × 30% × ¥50k`) annual value is
**≈ ¥18k**; at the high end (`104 × 20% × 70% × ¥500k`) it is **≈ ¥7.3M**. The
band spans more than two orders of magnitude, and that is the honest headline:
**the model does not yet support a confident ROI claim in either direction.**

At the band's midpoint the comparison is favorable — the tool's annual cost
sits in the low tens of thousands of yuan, well under the midpoint value — but
the midpoint of two unmeasured multiplicands is not evidence.

**What would collapse the band (and is therefore the top research priority):**
measuring `p_bad_release` and `cost_of_bad_release` on the design partner's
actual release history. Two retrospective data points from one real team would
narrow the band more than any amount of further modelling. Note also that
`p_detected` is bounded by the tool's statistical power, which on the demo
corpus is genuinely limited (§9); it is not a free 100%.

## 9. GTM — go-to-market

**Motion: narrow, technical, and consultative first.** Not self-serve, not
PLG, not a content engine.

**Sequence.**

1. **One vertical, one integration.** Enterprise knowledge-base QA / customer
   support against an internal corpus. The integration surface is small: the
   customer's HTTP endpoint plus the corpus. Do not add a second vertical until
   one pilot has completed end to end.
2. **Design partner, not a customer.** Find one team that has *already* had the
   §3 trigger fire — ideally within the last quarter, ideally still
   post-morteming it. Offer the pilot at cost or free in exchange for real run
   data and a reference if it works. Their real corpus is the asset the pilot
   buys.
3. **Lead with the report artifact, not the platform.** Open the conversation
   with one page: a release-gate report from a run against *their* scenarios
   showing what evidence a blocked release actually looks like. The demo in
   this repository is the template; it must be re-run on their data before it
   is shown.
4. **Publish the negative result.** The aggregate comparison in the demo does
   not clear its threshold, and the report says so. Leading with a tool that
   visibly refuses to overclaim is the sharpest possible differentiator against
   every dashboard in §5. It also pre-qualifies: a buyer who wants a
   green-checkmark tool is the wrong buyer.
5. **Expand along release gates.** Second use case is prompt regression, third
   is agent-workflow monitoring, fourth is compliance evidence. Each is the
   same comparison engine pointed at a different artifact. Do not pursue them
   in parallel.

**Channels, in priority order:** direct outbound to the §1 ICP by technical
founder; engineering communities where eval practitioners already argue about
this (the champion in §2 is reachable and vocal); conference/competition demos
as credibility, not as lead generation.

**Explicitly not doing (and why):** paid acquisition before a validated
message; a public free tier before the ICP is confirmed; a self-serve signup
before the integration is productized; horizontal "AI quality platform"
positioning, which puts the product in direct feature-comparison with funded
incumbents and abandons the causal claim.

## 10. 90-day pilot plan

Starting from zero traction. **Days are elapsed days from the start of the
plan, not calendar dates**, because the plan has not started.

**Days 0–30 — falsify the ICP and the trigger.**

| # | Task | Artifact | Kill condition |
|---|---|---|---|
| 1 | 10 conversations with people matching §1 | Written notes, one per call | If fewer than 4 of 10 have experienced the §3 trigger in the last 6 months, the trigger hypothesis is wrong. Rewrite §3 before continuing. |
| 2 | Ask each for their last release's `p_bad_release` and `cost_of_bad_release` | Two retrospective data points | If nobody can estimate either, the ROI model in §8 has no input and the tool cannot be sold on ROI. Sell on the evidence artifact instead. |
| 3 | Confirm the budget line in §2 exists | Named budget line, per conversation | No named line after 10 calls → the pricing shape in §7 is wrong. |

**Days 31–60 — one real run on real data.**

| # | Task | Artifact | Kill condition |
|---|---|---|---|
| 4 | Secure one design partner from the Day 0–30 cohort | Signed pilot agreement (free or at cost) | No partner by Day 45 → the ICP or the trigger is wrong again; loop back, do not build. |
| 5 | Configure EvalPilot against their assistant and their corpus | A configured project + two real versions | If integration takes longer than 5 engineer-days, the product is not yet sellable as-is; the integration cost is the finding. |
| 6 | Run the comparison on a release they have **already shipped** | A retro-diagnosis: does the tool agree with what actually happened? | If the tool's verdict contradicts the known outcome, that is a product bug and the pilot pauses for it. |
| 7 | Measure `p_detected` for real, on their history | One measured number replacing an assumption in §8 | — |

**Days 61–90 — the decision.**

| # | Task | Artifact | Kill condition |
|---|---|---|---|
| 8 | Run the tool as a **live release gate** on one real, upcoming release | A gate decision the team actually acted on | If the gate's recommendation was ignored, the product is not yet load-bearing. |
| 9 | Instrument the value claim: how many engineer-hours did the gate replace? | One measured number replacing an assumption in §8 | — |
| 10 | Ask for the purchase | A price quoted, and a yes or a no | A "no" here is a *result*: it is the first real data point in this document. |
| 11 | Write the honest outcome back into this file, replacing hypotheses with measurements | This document, revised | If nothing was measured, the pilot produced no value regardless of the outcome. |

**Definition of pilot success.** Not "the tool worked." Success is: *one named
team ran it on real data, acted on its verdict for a real release, and can say
in one sentence what it replaced.* Everything else is a demo.

## 11. Risks and what would falsify this document

| Risk | Why it is real | Falsification signal |
|---|---|---|
| **The pain is real but not urgent.** | Chronic eval pain is tolerable indefinitely; §3's trigger may be rarer than assumed. | Fewer than 4 of 10 ICP conversations report a recent trigger. |
| **"Do nothing" is good enough.** | The §5 spreadsheet competitor is free and feels adequate. | Prospects agree the problem exists and still will not allocate time to a pilot. |
| **The moat does not hold.** | §6's mechanism is standard statistics. | A prospect says "we can build this ourselves in a sprint" — and is right. |
| **The statistics do not resolve at realistic scale.** | Demonstrated in-repo: 26 matched scenarios do not clear the aggregate threshold. | A pilot's real corpus is too small or too noisy to produce a decision. Note this is a *product* limit, not a marketing one, and it must be disclosed rather than tuned away. |
| **Integration cost exceeds willingness to pay.** | The pilot must be configured against a real system. | Task 5 exceeds 5 engineer-days. |
| **The competition result is mistaken for the market result.** | The demo is compelling and it is easy to let it stand in for validation. | Any report of traction that cannot name a counterparty. |

## 12. What this document is not

- Not a validated strategy. It is §0's zero-traction table plus a plan.
- Not a revenue forecast. §8 is a sensitivity model with two unmeasured
  multiplicands and a two-orders-of-magnitude output band.
- Not evidence that anyone wants this. §1–§7 are the team's beliefs, written
  down so §10 can falsify them.

The single sentence: **the mechanism is implemented and demonstrated on seeded
data; the market is a hypothesis; the only thing measured so far is the
product's own behaviour on its own corpus.**
