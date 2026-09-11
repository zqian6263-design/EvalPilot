import type { MetricValue } from '../api/types'
import type { Scenario } from '../fixtures/scenarios'
import {
  formatMetricDelta,
  formatMetricValue,
  moveDirection,
  type MoveDirection,
} from '../lib/format'

interface Props {
  scenario: Scenario
}

const ORDER = [
  'task_success',
  'citation_coverage',
  'correct_refusal',
  'format_compliance',
  'groundedness',
  'latency_p50',
  'answer_tokens',
] as const

function deltaClass(move: MoveDirection): string {
  if (move === 'worse') return 'metric__delta metric__delta--down'
  if (move === 'better') return 'metric__delta metric__delta--up'
  return 'metric__delta metric__delta--flat'
}

function candidateClass(move: MoveDirection): string {
  if (move === 'worse') return 'metric__value metric__value--candidate-worse'
  if (move === 'better') return 'metric__value metric__value--candidate-better'
  return 'metric__value'
}

/**
 * Baseline against candidate, one metric per row.
 *
 * A meter encodes the move against a fixed zero rather than a proportional
 * bar: a bar cannot show direction honestly, and direction is the entire
 * question. Extent to the left of centre is loss, to the right is gain.
 */
function MetricRow({
  id,
  metric,
  scenario,
}: {
  id: string
  metric: MetricValue
  scenario: Scenario
}): React.JSX.Element {
  const move = moveDirection(metric, metric.baseline, metric.candidate)
  const relative = Math.abs(metric.candidate - metric.baseline) / Math.max(Math.abs(metric.baseline), 1e-6)
  const extent = Math.min(relative / 0.5, 1) * 50

  return (
    <div className="metric" data-metric={id}>
      <div className="metric__head">
        <span className="metric__name">{metric.label}</span>
        <span className="metric__n">n = {metric.n}</span>
      </div>

      <div className="metric__values">
        <div className="metric__pair">
          <span className="metric__version">{scenario.baselineVersion} baseline</span>
          <span className="metric__value metric__value--baseline">
            {formatMetricValue(metric, metric.baseline)}
          </span>
        </div>
        <div className="metric__pair">
          <span className="metric__version">{scenario.candidateVersion} candidate</span>
          <span className={candidateClass(move)}>{formatMetricValue(metric, metric.candidate)}</span>
        </div>
      </div>

      <div className="row row--between" style={{ gap: 'var(--s3)' }}>
        <div className="meter" style={{ flex: 1 }} role="presentation">
          {move === 'worse' && (
            <div className="meter__fill meter__fill--loss" style={{ width: `${extent}%` }} />
          )}
          {move === 'better' && (
            <div className="meter__fill meter__fill--gain" style={{ width: `${extent}%` }} />
          )}
          <div className="meter__zero" />
        </div>
        <span className={deltaClass(move)}>{formatMetricDelta(metric, metric.baseline, metric.candidate)}</span>
      </div>
    </div>
  )
}

export function Metrics({ scenario }: Props): React.JSX.Element {
  return (
    <section aria-label="Metrics" className="panel" style={{ border: 'none', background: 'transparent' }}>
      <div className="panel__title" style={{ borderBottom: 'var(--rule-ink)' }}>
        <span className="u-label">Metric comparison</span>
        <span className="u-micro">matched cases only</span>
      </div>
      {ORDER.map((id) => {
        const metric = scenario.metrics[id]
        if (!metric) return null
        return <MetricRow key={id} id={id} metric={metric} scenario={scenario} />
      })}
      <p className="u-micro" style={{ padding: 'var(--s3) var(--s4)', lineHeight: 1.6 }}>
        Aggregates cover cases carried to completion on both versions. A case that errored on
        either side is excluded from both, so a version cannot improve its score by failing fewer
        cases or by shrinking the denominator.
      </p>
    </section>
  )
}
