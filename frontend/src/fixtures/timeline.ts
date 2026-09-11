import type { ProgressEvent } from '../api/types'
import { at, RUN_A_ID } from './ids'
import { SCENARIOS, type Scenario } from './scenarios'

/**
 * The progress event stream, built from the scenario's own outcomes.
 *
 * The events are generated, not typed in: every message quotes a value the
 * scoring module actually computed, so the stream and the results cannot
 * disagree. `sequence` restarts per run and increments by one, as the frozen
 * event payload in docs/INTERFACES.md requires.
 */

export interface TimelineEntry {
  event: ProgressEvent
  /** Scenario the entry belongs to, so the demo entry can replay any of them. */
  scenarioId: Scenario['id']
  /** Milliseconds after run start, used for pacing the replay. */
  offsetMs: number
}

function makeEvent(
  sequence: number,
  type: ProgressEvent['type'],
  message: string,
  atSeconds: number,
  data: Record<string, unknown> = {},
): ProgressEvent {
  return {
    run_id: RUN_A_ID,
    sequence,
    type,
    message,
    data,
    created_at: at(atSeconds),
  }
}

function buildForScenario(scenario: Scenario): TimelineEntry[] {
  let seq = 0
  let clock = 0
  const entries: TimelineEntry[] = []
  const push = (
    type: ProgressEvent['type'],
    message: string,
    advanceSeconds: number,
    data?: Record<string, unknown>,
  ): void => {
    seq += 1
    clock += advanceSeconds
    entries.push({
      event: makeEvent(seq, type, message, clock, data),
      scenarioId: scenario.id,
      offsetMs: clock * 1000,
    })
  }

  const cases = scenario.outcomes

  push('run.started', `Run started. ${scenario.baselineVersion} vs ${scenario.candidateVersion}, ${scenario.comparison.matched_cases} cases matched from the project brief.`, 0, {
    baseline_version: scenario.baselineVersion,
    candidate_version: scenario.candidateVersion,
  })

  push(
    'task.created',
    `Planner produced ${cases.length} cases — ${cases.filter((c) => c.spec.category === 'normal').length} normal, ${cases.filter((c) => c.spec.category === 'boundary').length} boundary, ${cases.filter((c) => c.spec.category === 'adversarial').length} adversarial, ${cases.filter((c) => c.spec.category === 'regression').length} regression.`,
    4,
    { case_count: cases.length },
  )

  for (const outcome of cases) {
    const n = String(outcome.spec.n).padStart(2, '0')
    push(
      'task.started',
      `Case ${n} started — ${outcome.spec.title} (${outcome.spec.category}, difficulty ${outcome.spec.difficulty.toFixed(2)}).`,
      1.6,
      { case: n, category: outcome.spec.category, difficulty: outcome.spec.difficulty },
    )

    push(
      'evidence.created',
      `Case ${n}: retrieved ${outcome.baseline.retrieved.length} passages on ${scenario.baselineVersion}, ${outcome.candidate.retrieved.length} on ${scenario.candidateVersion}.`,
      2.4,
      {
        case: n,
        baseline_passages: outcome.baseline.retrieved.length,
        candidate_passages: outcome.candidate.retrieved.length,
      },
    )

    push(
      'task.completed',
      `Case ${n} completed — ${scenario.baselineVersion} ${outcome.baselineVerdict.total.toFixed(2)} → ${scenario.candidateVersion} ${outcome.candidateVerdict.total.toFixed(2)} (${outcome.delta === 0 ? 'no change' : `${outcome.delta > 0 ? '+' : ''}${outcome.delta.toFixed(2)}`}).`,
      1.2,
      { case: n, baseline: outcome.baselineVerdict.total, candidate: outcome.candidateVerdict.total },
    )
  }

  const regressions = cases.filter((c) => c.regression)
  if (regressions.length > 0) {
    for (const outcome of regressions) {
      const n = String(outcome.spec.n).padStart(2, '0')
      push(
        'finding.created',
        `Finding raised on case ${n} — ${outcome.spec.title}. Delta ${outcome.delta.toFixed(2)} reproduced across ${scenario.comparison.repeats} repeats.`,
        0.8,
        { case: n, delta: outcome.delta },
      )
    }
  }

  push(
    'run.completed',
    regressions.length > 0
      ? `Run complete. ${regressions.length} stable regression(s) of ${scenario.comparison.matched_cases} matched cases. Verdict: regression, confidence ${scenario.comparison.regression_confidence.toFixed(2)}.`
      : `Run complete. No stable regression across ${scenario.comparison.matched_cases} matched cases. Confidence ${scenario.comparison.regression_confidence.toFixed(2)}.`,
    3,
    {
      stable_regressions: regressions.length,
      regression_confidence: scenario.comparison.regression_confidence,
    },
  )

  return entries
}

export const TIMELINE: readonly TimelineEntry[] = SCENARIOS.flatMap(buildForScenario)

export function timelineFor(scenarioId: Scenario['id']): TimelineEntry[] {
  return TIMELINE.filter((entry) => entry.scenarioId === scenarioId)
}

/**
 * The tail of the stream, used by the "resume live run" transport control: a
 * partially-complete run renders as two half-legends across a seam rather than
 * as a finished tape.
 */
export function partialRun(scenarioId: Scenario['id'], completedCases: number): {
  entries: TimelineEntry[]
  total: number
} {
  const entries = timelineFor(scenarioId)
  const total = entries.length
  const cut = Math.max(1, Math.round(total * (completedCases / 24)))
  return { entries: entries.slice(0, cut), total }
}

/** Only the headline scenario ships with a live-stream transcript by default. */
export const DEFAULT_TIMELINE_SCENARIO: Scenario['id'] = SCENARIOS[0]!.id
