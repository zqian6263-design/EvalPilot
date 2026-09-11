# Evaluation Subsystem

Evidence-backed evaluation for EvalPilot: deterministic answer checks, an
injected LLM judge, and a matched baseline/candidate comparison that separates
a real regression from test difficulty and sampling noise.

Pure Python. No LLM SDK, no network client, no numpy/scipy. The only
third-party dependency is `pydantic` (already required by the backend).

- Source: `backend/evalpilot/evaluation/`
- Tests: `backend/tests/test_evaluation.py`

```bash
cd backend && python -m pytest tests/test_evaluation.py -q
```

## Why the comparison is built this way

The product claim is that EvalPilot can tell a genuine regression from a harder
test set. That is a design constraint, not a feature flag, so it is worth
stating how the numbers are produced.

**Cases are matched.** Every statistic is computed on the *difference within a
test case*: the same case run against both versions. A case that is
intrinsically hard contributes that difficulty to both arms, so it cancels out.
Comparing a candidate's mean against a baseline's mean — the naive approach —
conflates "the change broke things" with "the candidate happened to be tested on
harder cases". `test_matched_design_resists_a_harder_test_set_that_is_not_a_regression`
pins this behaviour: an unpaired comparison of those numbers reports a 0.52
drop, while the matched comparison correctly reports no change.

**Repeats are collapsed before pairing.** Multiple trials of the same case are
averaged into one score per version, *then* differences are formed. The
alternative — treating every trial as an independent pair — inflates the sample
size, shrinks the confidence interval, and manufactures significance out of
nothing but sampling noise. Collapsing keeps the unit of analysis the test case,
which is what the change actually acts on. `trial_count` is still reported so a
reader can see how much averaging happened.

**Effect size is paired Cohen's *d*.** Mean difference over the standard
deviation of the difference scores. Hedges' *g* for unpaired samples is
deliberately not used: it is a between-groups statistic and reintroduces exactly
the case-difficulty variance that matching removes.

**The interval is a seeded bootstrap.** A local multiplicative-congruential
generator means results are bit-for-bit reproducible on any machine with no
numeric dependency. The seed moves the interval only; point estimates never
depend on it.

**The decision is a confidence interval, not a p-value.** The interval is
compared against a practical-significance threshold (default `0.05`):

| Condition                        | Verdict        |
| -------------------------------- | -------------- |
| whole interval below `-threshold`| `regression`   |
| whole interval above `+threshold`| `improvement`  |
| otherwise                        | `inconclusive` |

Two consequences worth knowing:

- A change smaller than the threshold is `inconclusive` even when it is
  statistically tidy. Practical significance is judged separately from noise.
- Fewer than `MIN_CASES_FOR_SIGNIFICANCE` (3) matched cases is *always*
  `inconclusive`, however clean the numbers look. The bootstrap cannot resolve
  an interval worth acting on below that.

`confidence` is the confidence that the true difference clears the threshold on
the side the point estimate leans toward. It is reported alongside the verdict
rather than folded into it, so a reader can see how close the call was. Note
that a regression in which every case moved by exactly the same amount has zero
spread and therefore reports full confidence — the strongest evidence, not the
weakest.

## Scoring

Each sampled observation is scored on two independent axes, then blended with
equal weight:

- **deterministic** — always available, reproducible, free;
- **judge** — only when a rubric is supplied and the observation did not error.

If the judge fails (transport error, malformed output), the failure is counted
in `judge_failures` and the deterministic score is used alone. One flaky judge
call cannot zero out a run. If nothing is applicable to a case, it scores `1.0`
rather than `0.0`: a case that asserts nothing has not failed anything.

An observation with `error` set scores `0.0` and is never sent to the judge —
there is no answer to judge.

## Deterministic checks

| Check                  | Asserts                                                     |
| ---------------------- | ----------------------------------------------------------- |
| `ResponseFormatCheck`  | required markers present, forbidden absent, length in window |
| `RequiredRefusalCheck` | refusal when the case demands one                            |
| `CitationPresenceCheck`| at least one **structured** citation                         |
| `ToolTraceCheck`       | at least one recorded tool call                              |
| `ExpectedFactsCheck`   | fraction of required keywords present (partial credit)        |

A check with no corresponding expectation returns `applicable=False` and is
excluded from the average, so an inapplicable check never scores `0`.

`CitationPresenceCheck` inspects `answer.citations`, not the answer text. An
answer that merely writes a filename in prose has not grounded itself; that
distinction is pinned by `test_citation_check_ignores_citations_carried_in_the_answer_text`.

Failing a check that stands for a piece of *evidence* (citation, tool trace)
produces a `MissingEvidence` record. Repeated trials of the same gap collapse
into one record with an `occurrences` count — "this case cited nothing" is one
defect per case and version, not one per trial.

## The judge protocol

The judge is an injected async callable taking a `JudgeRequest` and returning
the model's raw text. Validation happens in `RubricJudge`, not in the callable,
so a judge cannot silently return a plausible but malformed verdict.

```python
from evalpilot.evaluation import JudgeRequest, RubricJudge

async def my_llm(request: JudgeRequest) -> str:
    # Adapt to any provider. This module never calls one itself.
    return await my_client.complete(build_judge_prompt(request))

judge = RubricJudge(judge_fn=my_llm, criteria=["faithfulness", "tone"])
```

Accepted output is strict JSON:

```json
{
  "score": 0.75,
  "confidence": 0.8,
  "rationale": "Answer is grounded but omits the refund window.",
  "criteria": [
    { "name": "faithfulness", "score": 0.9, "rationale": "All claims appear in the context." },
    { "name": "tone", "score": 0.6, "rationale": "Abrupt but not rude." }
  ]
}
```

`confidence` is optional (defaults to `0.5`) and a single wrapping markdown code
fence is tolerated, because models emit them constantly and it is a formatting
quirk rather than a schema violation. Everything else raises `JudgeError`:

| Input                              | Result                          |
| ---------------------------------- | ------------------------------- |
| `this is not json`                 | `JudgeError: not valid JSON`    |
| `{"score": "high", ...}`           | `JudgeError: schema validation` |
| `{"score": 1.4, ...}`              | `JudgeError: schema validation` |
| `[1, 2, 3]`                        | `JudgeError: schema validation` |
| `{"score": NaN}`                   | `JudgeError: not valid JSON`    |
| callable raises                    | `JudgeError: judge call failed` |

The service catches `JudgeError`, counts it, and continues. `JudgeError` is
raised directly only when a caller drives `RubricJudge` themselves.

## Usage

```python
from evalpilot.evaluation import (
    EvaluationService, ExpectedBehavior, SampleObservation, AnswerInput, Citation,
)

service = EvaluationService(judge=judge, judge_criteria=["faithfulness"], seed=7)

report = service.compare(
    observations=observations,              # every case, every version, every trial
    expectations={case_id: ExpectedBehavior(...)},
    evidence_ids_by_case={case_id: [...], ...},   # evidence ids persisted by the run
    rubric="Score faithfulness and tone.",
    run_id=run_id,
)

report.comparison.direction      # ComparisonDirection.REGRESSION
report.comparison.confidence     # 0.993
report.comparison.mean_difference
report.findings                  # every finding carries evidence_ids
report.warnings                  # what was skipped, and why
```

`compare()` runs judge calls concurrently and is the sync entry point.
`compare_async()` is the same thing awaitable. `compare()` **refuses** to run
inside a live event loop rather than deadlocking on one — await
`compare_async()` there.

Because `compare` filters observations by case, passing the whole run's
observations is expected. `evaluate_case` is the single-case entry point and
returns a `CaseEvaluation` with per-version scores and the deduplicated
missing-evidence list.

### Comparing one case directly

```python
from evalpilot.evaluation import compare_matched_cases

result = compare_matched_cases(
    [(0.90, 0.35), (0.88, 0.42), (0.92, 0.30), (0.85, 0.48), (0.91, 0.39)],  # per matched case
    seed=7,
)
result.direction    # <ComparisonDirection.REGRESSION: 'regression'>
result.confidence   # 1.0
result.effect_size  # -5.333
result.ci_lower     # -0.574
result.ci_upper     # -0.436
```

Scores must be **per-case aggregates across trials**, not raw trials, or the
interval will be too narrow.

## Report JSON

The numbers below are the real output for the five `(baseline, candidate)` pairs
above, with `run_id` set and evidence ids shortened for readability.

```json
{
  "run_id": "3f1c-9d2a",
  "comparison": {
    "direction": "regression",
    "mean_difference": -0.504,
    "std_difference": 0.09449867723941964,
    "ci_lower": -0.574,
    "ci_upper": -0.436,
    "effect_size": -5.33340798753275,
    "confidence": 1.0,
    "is_significant": true,
    "sample_size": 5,
    "trial_count": 3,
    "threshold": 0.05,
    "baseline_mean": 0.892,
    "candidate_mean": 0.388,
    "rationale": "Mean score fell 0.504 (95% CI -0.574 to -0.436), entirely below the -0.050 regression threshold."
  },
  "findings": [
    {
      "id": "5f0a0cad-6a7f-4523-8976-69e286fa9e4a",
      "run_id": "3f1c-9d2a",
      "case_id": null,
      "severity": "critical",
      "title": "Candidate version regressed against baseline",
      "description": "Across 5 matched case(s), the candidate's mean score changed by -0.504 (effect size -5.33). Confidence the change clears the threshold: 100%.",
      "confidence": 1.0,
      "evidence_ids": ["ev-1", "ev-2"],
      "rationale": "Mean score fell 0.504 (95% CI -0.574 to -0.436), entirely below the -0.050 regression threshold.",
      "recommendation": "Re-run the affected cases against the previous version to confirm the regression persists, then inspect the retrieval and prompting changes that landed between the two versions.",
      "metrics": {
        "mean_difference": -0.504,
        "ci_lower": -0.574,
        "ci_upper": -0.436,
        "effect_size": -5.33340798753275,
        "sample_size": 5,
        "threshold": 0.05,
        "direction": "regression"
      },
      "created_at": "2026-09-11T13:10:30.296280Z"
    }
  ],
  "metrics": {
    "case_count": 5,
    "evaluated_case_count": 5,
    "trial_count": 3,
    "baseline_mean": 0.892,
    "candidate_mean": 0.388,
    "mean_difference": -0.504,
    "ci_lower": -0.574,
    "ci_upper": -0.436,
    "effect_size": -5.33340798753275,
    "confidence": 1.0,
    "direction": "regression"
  },
  "excluded_case_ids": [],
  "warnings": [],
  "judge_failures": 0,
  "generated_at": "2026-09-11T13:10:30.296280Z"
}
```

`case_id` is set only when a finding concerns exactly one case. A finding about
a whole matched comparison leaves it `null` and cites every contributing case
through `evidence_ids`, which is why the regression finding above has `null`
there. A missing-evidence finding always names its case.

Additional findings are emitted per case that lacked required evidence, each
carrying that case's evidence ids — so a run typically returns one comparison
finding plus one finding per evidence gap.


## Findings and evidence

`Finding` requires a non-empty `evidence_ids`, enforced twice:

1. the model rejects an empty list at validation time;
2. the builders raise `ValueError` before constructing anything.

The builder guard runs **before** the direction check, so a caller that forgot
to attach evidence always hears about it rather than having the mistake masked
by an inconclusive result.

When the service detects a regression but was given no evidence ids for those
cases, it emits **no finding** and records a warning. It does not invent a
placeholder. This is the one place where the subsystem prefers a loudly
incomplete report to a complete-looking one: an unattributable finding would
violate the contract that every finding links to evidence.

Severity is banded by the size of the mean difference, then downgraded one band
when confidence is below `0.90` — an effect we are unsure about should not be
reported as loudly as one we are sure about. Inconclusive and improving
comparisons are `info`; only a confirmed regression is a defect.

| mean difference | severity   |
| --------------- | ---------- |
| ≥ 0.40          | `critical` |
| ≥ 0.25          | `high`     |
| ≥ 0.10          | `medium`   |
| < 0.10          | `low`      |

## Test coverage

`backend/tests/test_evaluation.py` covers, offline:

- stable improvement, stable regression, and noisy non-regression;
- a harder unconsumed test set that must *not* read as a regression;
- a sub-threshold drop, and the same drop under a tighter threshold;
- reproducibility for a fixed seed, and seed-independence of point estimates;
- invalid judge output: malformed JSON, wrong types, out-of-range scores,
  non-object JSON, NaN, and transport failure;
- judge output wrapped in a markdown fence;
- missing evidence, deduplication across trials, and the refusal to emit a
  finding without evidence;
- zero-variance regressions reporting full confidence;
- JSON round-trip of a report preserving evidence ids.

Every judge interaction in the suite is a fake async callable. There are no
network calls and no LLM SDK anywhere in the package or its tests.
