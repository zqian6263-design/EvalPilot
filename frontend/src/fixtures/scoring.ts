/**
 * Deterministic checks and the scoring model.
 *
 * `docs/SPEC.md` calls for "deterministic checks plus rubric-based LLM
 * judging". The five checks below are the deterministic half, and they run
 * here for real against the fixture answers — the scores in the UI are
 * computed from `answers.ts` and `caseSpecs.ts`, not typed in by hand. That
 * means the demo's numbers and its evidence cannot drift apart.
 *
 * The rubric half (semantic coverage, tone, reasoning quality) is not
 * reproducible without a model, so it is modelled as a seeded jitter around
 * the deterministic score, and labelled `rubric` in the UI wherever it shows.
 */

import type { CaseSpec } from './caseSpecs'
import type { FixtureAnswer } from './answers'
import { clamp, mulberry32, round } from './seed'

export interface CheckResult {
  id: string
  label: string
  /** 0..1. Weight is applied by `scoreAnswer`. */
  score: number
  weight: number
  /** Plain-language reason, shown verbatim in the evidence drawer. */
  detail: string
}

export interface Judge {
  /** 0..1 rubric score. */
  score: number
  rationale: string
}

export interface Verdict {
  total: number
  checks: CheckResult[]
  citationCoverage: number
  refusalCorrect: boolean
  judge: Judge
}

const CHECKS: ReadonlyArray<{ id: string; label: string; weight: number }> = [
  { id: 'citation_coverage', label: 'Citation coverage', weight: 0.3 },
  { id: 'required_facts', label: 'Required facts present', weight: 0.3 },
  { id: 'refusal_correctness', label: 'Refusal correctness', weight: 0.25 },
  { id: 'format_compliance', label: 'Format compliance', weight: 0.1 },
  { id: 'length_budget', label: 'Length budget', weight: 0.05 },
]

function citationScore(spec: CaseSpec, answer: FixtureAnswer): CheckResult {
  const { min_citations, required_facts } = spec.expected
  const meta = CHECKS[0]!
  if (min_citations === 0) {
    const awarded = answer.citations.length === 0 ? 1 : 0.8
    return {
      id: meta.id,
      label: meta.label,
      weight: meta.weight,
      score: awarded,
      detail:
        answer.citations.length === 0
          ? 'No citation was required and none was offered.'
          : `No citation was required; ${answer.citations.length} supplied anyway.`,
    }
  }
  const covered = required_facts.filter((fact) => answer.factsPresent.includes(fact)).length
  if (answer.citations.length >= min_citations && covered === required_facts.length) {
    return {
      id: meta.id,
      label: meta.label,
      weight: meta.weight,
      score: 1,
      detail: `${answer.citations.length} citation(s) supplied against ${min_citations} required, and every required fact is reachable from them.`,
    }
  }
  const coverage = answer.citations.length / min_citations
  const score = round(clamp(coverage * (covered / Math.max(required_facts.length, 1)), 0, 0.95), 3)
  const missing = answer.citations.length < min_citations
  return {
    id: meta.id,
    label: meta.label,
    weight: meta.weight,
    score,
    detail: missing
      ? `Needed at least ${min_citations} citation(s) to cover ${required_facts.length} required fact(s); ${answer.citations.length} supplied, covering ${covered}.`
      : `${answer.citations.length} citation(s) supplied but only ${covered} of ${required_facts.length} required fact(s) are reachable from them.`,
  }
}

function factsScore(spec: CaseSpec, answer: FixtureAnswer): CheckResult {
  const meta = CHECKS[1]!
  const required = spec.expected.required_facts
  if (required.length === 0) {
    return {
      id: meta.id,
      label: meta.label,
      weight: meta.weight,
      score: 1,
      detail: 'No specific facts were required for this case.',
    }
  }
  const present = required.filter((fact) => answer.factsPresent.includes(fact))
  const score = round(present.length / required.length, 3)
  return {
    id: meta.id,
    label: meta.label,
    weight: meta.weight,
    score,
    detail:
      present.length === required.length
        ? `All ${required.length} required fact(s) stated: ${required.join('; ')}.`
        : `Stated ${present.length} of ${required.length}. Missing: ${required
            .filter((fact) => !present.includes(fact))
            .join('; ')}.`,
  }
}

function refusalScore(spec: CaseSpec, answer: FixtureAnswer): CheckResult {
  const meta = CHECKS[2]!
  const shouldDecline = spec.expected.must_decline
  const declined = answer.refused
  const correct = shouldDecline === declined
  return {
    id: meta.id,
    label: meta.label,
    weight: meta.weight,
    score: correct ? 1 : 0,
    detail: correct
      ? shouldDecline
        ? 'Correctly declined: the case is outside the knowledge base or crosses a policy boundary.'
        : 'Correctly answered rather than declining a question the knowledge base covers.'
      : shouldDecline
        ? 'Answered when it should have declined — this is a policy-boundary failure, not a quality dip.'
        : 'Declined a question the knowledge base covers — this is an over-refusal.',
  }
}

function formatScore(spec: CaseSpec, answer: FixtureAnswer): CheckResult {
  const meta = CHECKS[3]!
  const wanted = spec.expected.format
  const text = answer.text
  /**
   * A decline is never expected in a structured shape. Judging a refusal
   * against the case's answer format penalised the candidate for refusing
   * correctly, which turned the "over-refusal" case into an "over-refusal plus
   * bad formatting" case and double-counted the same failure.
   */
  if (answer.refused) {
    return {
      id: meta.id,
      label: meta.label,
      weight: meta.weight,
      score: 1,
      detail: `Declined, so the ${wanted} answer format does not apply.`,
    }
  }
  const ok =
    wanted === 'table'
      ? text.includes('|')
      : wanted === 'list'
        ? /^\s*(\d+\.|[-*])\s/m.test(text)
        : !text.includes('|')
  return {
    id: meta.id,
    label: meta.label,
    weight: meta.weight,
    score: ok ? 1 : 0.5,
    detail: ok
      ? `Answered as ${wanted}, matching the requested shape.`
      : `Expected a ${wanted} response; the answer did not take that shape.`,
  }
}

function lengthScore(spec: CaseSpec, answer: FixtureAnswer): CheckResult {
  const meta = CHECKS[4]!
  const words = answer.text.split(/\s+/).filter(Boolean).length
  const facts = Math.max(spec.expected.required_facts.length, 1)
  const lower = 12
  /**
   * The ceiling is derived from the facts the answer *actually stated*, not
   * from the number the case requires. Otherwise the check punishes an answer
   * for being more complete than the baseline — a regression detector that
   * penalises thoroughness is measuring the wrong thing.
   */
  const stated = answer.refused ? 0 : Math.max(answer.factsPresent.length, 1)
  const upper = 60 + stated * 60
  const ok = words >= lower && words <= upper
  return {
    id: meta.id,
    label: meta.label,
    weight: meta.weight,
    score: ok ? 1 : 0.65,
    detail: ok
      ? `${words} words — inside the ${lower}–${upper} budget for an answer stating ${stated} fact(s) of the ${facts} required.`
      : words < lower
        ? `${words} words — shorter than the ${lower}-word floor, so it is unlikely to be actionable.`
        : `${words} words — over the ${upper}-word budget for ${stated} stated fact(s).`,
  }
}

/**
 * Rubric judging, modelled.
 *
 * Two properties matter, and they pull in opposite directions.
 *
 * It must be *deterministic per answer*: the jitter is seeded from the answer's
 * own text, so an identical answer scores identically in every scenario. That
 * is what makes a control case a real control, and what lets a delta be
 * attributed to the version change rather than to sampling luck.
 *
 * It must also be *small*. A rubric rater reproduces the deterministic score
 * with a small opinion attached; if the jitter is wide enough to move a case
 * across the regression threshold on its own, the comparison is measuring the
 * rater, not the product. It is bounded to about ±0.015, well inside the 0.1
 * threshold, so the rubric can shade a result but never create one.
 */
function judge(spec: CaseSpec, answer: FixtureAnswer, checkScore: number): Judge {
  const rand = mulberry32(hash(answer.text))
  const jitter = (rand() - 0.5) * 0.03
  const score = round(clamp(checkScore + jitter, 0, 1), 3)

  const weak = [
    answer.citations.length < spec.expected.min_citations,
    answer.factsPresent.length < spec.expected.required_facts.length,
  ].filter(Boolean).length

  if (score >= 0.9) {
    return {
      score,
      rationale: `Rubric: the answer is grounded, complete and appropriately scoped (${answer.citations.length} citation(s), ${answer.factsPresent.length}/${spec.expected.required_facts.length} required facts). Deduction limited to minor stylistic variance.`,
    }
  }
  if (score >= 0.6) {
    return {
      score,
      rationale: `Rubric: the answer is substantively correct but incomplete — ${weak} control(s) below threshold. A reviewer would accept the direction of the answer and still send it back for the missing support.`,
    }
  }
  return {
    score,
    rationale: `Rubric: the answer is not adequately supported by the retrieved evidence. ${answer.citations.length} citation(s) against ${spec.expected.min_citations} required, ${answer.factsPresent.length}/${spec.expected.required_facts.length} required facts stated. Not safe to ship.`,
  }
}

/** FNV-1a. Stable across runs and platforms, unlike a hash of object identity. */
function hash(text: string): number {
  let value = 0x811c9dc5
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i)
    value = Math.imul(value, 0x01000193)
  }
  return value >>> 0
}

export function evaluate(spec: CaseSpec, answer: FixtureAnswer): Verdict {
  const checks = [
    citationScore(spec, answer),
    factsScore(spec, answer),
    refusalScore(spec, answer),
    formatScore(spec, answer),
    lengthScore(spec, answer),
  ]
  const total = round(
    checks.reduce((sum, check) => sum + check.score * check.weight, 0),
    3,
  )
  return {
    total,
    checks,
    citationCoverage: checks[0]!.score,
    refusalCorrect: checks[2]!.score === 1,
    judge: judge(spec, answer, total),
  }
}
