import type { MetricValue } from '../api/types'
import type { Scenario } from '../fixtures/scenarios'
import {
  formatMetricDelta,
  formatMetricValue,
  moveDirection,
  type MoveDirection,
} from '../lib/format'
import { metricLabel } from '../i18n/labels'

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
        <span className="metric__name">{metricLabel(id, metric.label)}</span>
        <span className="metric__n">n = {metric.n}</span>
      </div>

      <div className="metric__values">
        <div className="metric__pair">
          <span className="metric__version">{scenario.baselineVersion} 基线</span>
          <span className="metric__value metric__value--baseline">
            {formatMetricValue(metric, metric.baseline)}
          </span>
        </div>
        <div className="metric__pair">
          <span className="metric__version">{scenario.candidateVersion} 候选</span>
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
    <section aria-label="指标对比" className="panel" style={{ border: 'none', background: 'transparent' }}>
      <div className="panel__title" style={{ borderBottom: 'var(--rule-ink)' }}>
        <span className="u-label">指标对比</span>
        <span className="u-micro">仅统计匹配场景</span>
      </div>
      {ORDER.map((id) => {
        const metric = scenario.metrics[id]
        if (!metric) return null
        return <MetricRow key={id} id={id} metric={metric} scenario={scenario} />
      })}
      <p className="u-micro" style={{ padding: 'var(--s3) var(--s4)', lineHeight: 1.6 }}>
        聚合只统计在两个版本上都执行完成的场景。任一侧出错的场景会同时从两侧剔除，
        因此某个版本无法通过减少失败场景或缩小分母来提高自己的得分。
      </p>
    </section>
  )
}
