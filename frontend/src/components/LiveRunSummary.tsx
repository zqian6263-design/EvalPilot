import type { LiveEvaluation } from '../api/evaluation'
import type { LiveReportMetrics } from '../api/types'
import { formatClock, formatPercent, formatStamp } from '../lib/format'

interface Props {
  evaluation: LiveEvaluation
  /** The live report's own metrics object, when a report was available. */
  reportMetrics: LiveReportMetrics
  reportGeneratedAt: string | null
}

/**
 * What the live run actually recorded, before any chart is read.
 *
 * The console's offline verdict card is backed by a fixture corpus that knows
 * a per-case score and a repeat count. A live run reports neither, so this
 * panel states the conclusion and then shows only counts, the run's own
 * timestamps, and the per-category breakdown the backend computed. Every
 * figure here is a field the backend sent.
 */
export function LiveRunSummary({
  evaluation,
  reportMetrics,
  reportGeneratedAt,
}: Props): React.JSX.Element {
  const { run, counts, verdict } = evaluation
  const regressed = counts.cases > 0 ? (reportMetrics.regressed_scenarios?.length ?? 0) : 0
  const byCategory = reportMetrics.by_category ?? {}
  const categories = Object.entries(byCategory)

  const word = verdict === 'regression' ? 'Regression' : 'No regression'

  return (
    <section className="verdict-card" aria-label="Verdict">
      <div className="verdict-card__headline">
        <h2
          className={`verdict-card__word verdict-card__word--${
            verdict === 'regression' ? 'down' : 'clear'
          }`}
        >
          {word}
        </h2>
        <div
          className={verdict === 'regression' ? 'stamp' : 'stamp stamp--clear'}
          aria-hidden="true"
        >
          <div className="stamp__word">{verdict === 'regression' ? 'Regressed' : 'Clear'}</div>
          <div className="stamp__sub">
            {run.candidate_version} vs {run.baseline_version}
          </div>
        </div>
      </div>

      <p className="verdict-card__summary">
        {evaluation.summary || 'The run has not produced a report yet; its summary appears here once it completes.'}
      </p>

      <div className="comparison">
        <div className="comparison__cell">
          <span className="u-micro">Matched</span>
          <span className="comparison__value">{counts.cases}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">Regressed</span>
          <span
            className={`comparison__value${regressed > 0 ? ' comparison__value--alert' : ''}`}
          >
            {regressed}
          </span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">Findings</span>
          <span className="comparison__value">{counts.findings}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">Evidence</span>
          <span className="comparison__value">{counts.evidence}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">Events</span>
          <span className="comparison__value">{counts.events}</span>
        </div>
      </div>

      <dl className="ledger" style={{ borderTop: 'none' }}>
        <dt className="ledger__key">Run</dt>
        <dd className="ledger__val">{run.id}</dd>
        <dt className="ledger__key">Status</dt>
        <dd className="ledger__val">{run.status}</dd>
        <dt className="ledger__key">Started</dt>
        <dd className="ledger__val">{formatStamp(run.created_at)}</dd>
        <dt className="ledger__key">Completed</dt>
        <dd className="ledger__val">
          {run.completed_at
            ? `${formatStamp(run.completed_at)} · ${formatClock(run.completed_at)}`
            : 'still running'}
        </dd>
        <dt className="ledger__key">Report generated</dt>
        <dd className="ledger__val">
          {reportGeneratedAt ? formatStamp(reportGeneratedAt) : 'not yet available'}
        </dd>
        {typeof reportMetrics.baseline_pass_rate === 'number' &&
          typeof reportMetrics.candidate_pass_rate === 'number' && (
            <>
              <dt className="ledger__key">Pass rate</dt>
              <dd className="ledger__val">
                {formatPercent(reportMetrics.baseline_pass_rate)} →{' '}
                {formatPercent(reportMetrics.candidate_pass_rate)}
              </dd>
            </>
          )}
      </dl>

      {categories.length > 0 && (
        <div className="scroll-x" style={{ marginTop: 'var(--s3)' }}>
          <table className="record">
            <caption className="visually-hidden">
              Matched scenarios by category, with how many regressed
            </caption>
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col" className="record__num">
                  Matched
                </th>
                <th scope="col" className="record__num">
                  Regressed
                </th>
              </tr>
            </thead>
            <tbody>
              {categories.map(([category, bucket]) => (
                <tr key={category}>
                  <td>{category}</td>
                  <td className="u-num">{bucket.total ?? 0}</td>
                  <td
                    className={`u-num${(bucket.regressed ?? 0) > 0 ? ' record__score--down' : ''}`}
                  >
                    {bucket.regressed ?? 0}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
