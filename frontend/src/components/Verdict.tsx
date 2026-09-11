import type { Scenario } from '../fixtures/scenarios'
import { formatClock, formatStamp } from '../lib/format'
import { at, RUN_A_ID } from '../fixtures/ids'
import { timelineFor } from '../fixtures/timeline'

interface Props {
  scenario: Scenario
}

/**
 * The verdict, stated before any chart is read.
 *
 * The headline is the plain conclusion; beneath it sit the four numbers that
 * justify it, because a verdict a reviewer cannot check is not a verdict.
 */
export function Verdict({ scenario }: Props): React.JSX.Element {
  const { comparison } = scenario
  // The run's completion time is the last event in its own transcript, so the
  // header can never disagree with the event log beneath it.
  const transcript = timelineFor(scenario.id)
  const completedAt = transcript[transcript.length - 1]?.event.created_at ?? at(232)
  const word =
    scenario.verdict === 'regression'
      ? 'Regression'
      : scenario.verdict === 'improvement'
        ? 'Improvement'
        : 'No regression'

  const stampClass =
    scenario.verdict === 'regression'
      ? 'stamp'
      : scenario.verdict === 'improvement'
        ? 'stamp stamp--better'
        : 'stamp stamp--clear'

  return (
    <section className="verdict-card" aria-label="Verdict">
      <div className="verdict-card__headline">
        <h2 className={`verdict-card__word verdict-card__word--${
          scenario.verdict === 'regression' ? 'down' : scenario.verdict === 'improvement' ? 'up' : 'clear'
        }`}>
          {word}
        </h2>
        <div className={stampClass} aria-hidden="true">
          <div className="stamp__word">{word === 'Regression' ? 'Regressed' : word}</div>
          <div className="stamp__sub">
            {scenario.candidateVersion} vs {scenario.baselineVersion}
          </div>
        </div>
      </div>

      <p className="verdict-card__summary">{scenario.summary}</p>

      <div className="comparison">
        <div className="comparison__cell">
          <span className="u-micro">Matched</span>
          <span className="comparison__value">{comparison.matched_cases}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">Repeats</span>
          <span className="comparison__value">{comparison.repeats}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">Regressed</span>
          <span className={`comparison__value${comparison.stable_regressions > 0 ? ' comparison__value--alert' : ''}`}>
            {comparison.stable_regressions}
          </span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">Noise only</span>
          <span className="comparison__value">{comparison.noise_only}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">Confidence</span>
          <span className="comparison__value">{comparison.regression_confidence.toFixed(2)}</span>
        </div>
      </div>

      <dl className="ledger" style={{ borderTop: 'none' }}>
        <dt className="ledger__key">Run</dt>
        <dd className="ledger__val">{RUN_A_ID}</dd>
        <dt className="ledger__key">Started</dt>
        <dd className="ledger__val">{formatStamp(at(0))}</dd>
        <dt className="ledger__key">Completed</dt>
        <dd className="ledger__val">
          {formatStamp(completedAt)} · {formatClock(completedAt)}
        </dd>
        <dt className="ledger__key">Change under test</dt>
        <dd className="ledger__val ledger__val--prose">{scenario.change.summary}</dd>
      </dl>
    </section>
  )
}
