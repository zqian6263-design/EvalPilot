import type { LiveMetricRow } from '../api/evaluation'
import type { MetricValue } from '../api/types'
import { formatMetricDelta, formatMetricValue, moveDirection, type MoveDirection } from '../lib/format'
import { metricLabel } from '../i18n/labels'

interface Props {
  rows: readonly LiveMetricRow[]
  baselineVersion: string
  candidateVersion: string
  /** False when the whole panel is the offline fixture corpus. */
  live: boolean
}

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

function MetricRow({
  id,
  metric,
  baselineVersion,
  candidateVersion,
}: {
  id: string
  metric: MetricValue
  baselineVersion: string
  candidateVersion: string
}): React.JSX.Element {
  const move = moveDirection(metric, metric.baseline, metric.candidate)
  const relative =
    Math.abs(metric.candidate - metric.baseline) / Math.max(Math.abs(metric.baseline), 1e-6)
  const extent = Math.min(relative / 0.5, 1) * 50

  return (
    <div className="metric" data-metric={id}>
      <div className="metric__head">
        <span className="metric__name">{metricLabel(id, metric.label)}</span>
        <span className="metric__n">n = {metric.n}</span>
      </div>

      <div className="metric__values">
        <div className="metric__pair">
          <span className="metric__version">{baselineVersion} 基线</span>
          <span className="metric__value metric__value--baseline">
            {formatMetricValue(metric, metric.baseline)}
          </span>
        </div>
        <div className="metric__pair">
          <span className="metric__version">{candidateVersion} 候选</span>
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
        <span className={deltaClass(move)}>
          {formatMetricDelta(metric, metric.baseline, metric.candidate)}
        </span>
      </div>
    </div>
  )
}

/**
 * The metric comparison, for either data source.
 *
 * The same component renders both because the difference between them is a
 * fact about the data, not about the layout. What changes is the caption: a
 * live panel names the one metric the run reported and marks every other row
 * "not reported by this evaluation service"; an offline panel is the fixture
 * corpus and says so. The rule that matters is that a row with no backend
 * value never borrows a fixture number to fill itself in.
 */
export function LiveMetrics({ rows, baselineVersion, candidateVersion, live }: Props): React.JSX.Element {
  const reported = rows.filter((row) => row.value !== null)
  const missing = rows.filter((row) => row.value === null)

  return (
    <section
      aria-label="指标对比"
      className="panel"
      style={{ border: 'none', background: 'transparent' }}
    >
      <div className="panel__title" style={{ borderBottom: 'var(--rule-ink)' }}>
        <span className="u-label">指标对比</span>
        <span className="u-micro">
          {live ? `${reported.length}/${rows.length} 项有报告值` : '仅统计匹配场景'}
        </span>
      </div>

      {reported.map((row) => (
        <MetricRow
          key={row.id}
          id={row.id}
          metric={row.value!}
          baselineVersion={baselineVersion}
          candidateVersion={candidateVersion}
        />
      ))}

      {live && missing.length > 0 && (
        <>
          <div
            className="panel__title"
            style={{ borderBottom: 'var(--rule-ink)', marginTop: 'var(--s3)' }}
          >
            <span className="u-label">未报告</span>
            <span className="u-micro">{missing.length} 项指标</span>
          </div>
          <ul className="u-micro" style={{ padding: 'var(--s2) var(--s4)', lineHeight: 1.7 }}>
            {missing.map((row) => (
              <li key={row.id}>
                <span className="u-device">{row.id}</span> — {metricLabel(row.id, row.label)}
                <span style={{ opacity: 0.75 }}> · 该评估服务未报告此项</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="u-micro" style={{ padding: 'var(--s3) var(--s4)', lineHeight: 1.6 }}>
        {live
          ? '评估服务只报告一组聚合值 —— 匹配场景上的通过率 —— 不提供逐指标或逐场景的分数。上方没有值的行会被列出而不是补全：这些数字在本次运行中并不存在，用替代值填充就不是证据了。'
          : '聚合只统计在两个版本上都执行完成的场景。任一侧出错的场景会同时从两侧剔除，因此某个版本无法通过减少失败场景或缩小分母来提高自己的得分。'}
      </p>
    </section>
  )
}
