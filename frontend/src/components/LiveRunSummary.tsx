import type { LiveEvaluation } from '../api/evaluation'
import type { LiveReportMetrics } from '../api/types'
import { formatClock, formatPercent, formatStamp } from '../lib/format'
import { caseCategoryLabel, runStatusLabel } from '../i18n/labels'

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

  const hasRegression = verdict !== 'no-regression'
  const word =
    verdict === 'regression'
      ? '已确认回归'
      : verdict === 'localized-regression'
        ? '局部回归'
        : '无回归'
  const stampWord =
    verdict === 'regression' ? '已回归' : verdict === 'localized-regression' ? '局部回归' : '通过'

  return (
    <section className="verdict-card" aria-label="裁决结论">
      <div className="verdict-card__headline">
        <h2
          className={`verdict-card__word verdict-card__word--${
            hasRegression ? 'down' : 'clear'
          }`}
        >
          {word}
        </h2>
        <div
          className={hasRegression ? 'stamp' : 'stamp stamp--clear'}
          aria-hidden="true"
        >
          <div className="stamp__word">{stampWord}</div>
          <div className="stamp__sub">
            {run.candidate_version} vs {run.baseline_version}
          </div>
        </div>
      </div>

      <p className="verdict-card__summary">
        {evaluation.summary || '该运行尚未生成报告；完成后摘要会显示在这里。'}
      </p>

      <div className="comparison">
        <div className="comparison__cell">
          <span className="u-micro">匹配场景</span>
          <span className="comparison__value">{counts.cases}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">已回归</span>
          <span
            className={`comparison__value${regressed > 0 ? ' comparison__value--alert' : ''}`}
          >
            {regressed}
          </span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">发现</span>
          <span className="comparison__value">{counts.findings}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">证据</span>
          <span className="comparison__value">{counts.evidence}</span>
        </div>
        <div className="comparison__cell">
          <span className="u-micro">事件</span>
          <span className="comparison__value">{counts.events}</span>
        </div>
      </div>

      <dl className="ledger" style={{ borderTop: 'none' }}>
        <dt className="ledger__key">运行 ID</dt>
        <dd className="ledger__val">{run.id}</dd>
        <dt className="ledger__key">状态</dt>
        <dd className="ledger__val">{runStatusLabel(run.status)}</dd>
        <dt className="ledger__key">开始时间</dt>
        <dd className="ledger__val">{formatStamp(run.created_at)}</dd>
        <dt className="ledger__key">完成时间</dt>
        <dd className="ledger__val">
          {run.completed_at
            ? `${formatStamp(run.completed_at)} · ${formatClock(run.completed_at)}`
            : '仍在运行'}
        </dd>
        <dt className="ledger__key">报告生成时间</dt>
        <dd className="ledger__val">
          {reportGeneratedAt ? formatStamp(reportGeneratedAt) : '尚不可用'}
        </dd>
        {typeof reportMetrics.baseline_pass_rate === 'number' &&
          typeof reportMetrics.candidate_pass_rate === 'number' && (
            <>
              <dt className="ledger__key">通过率</dt>
              <dd className="ledger__val">
                {formatPercent(reportMetrics.baseline_pass_rate)} →{' '}
                {formatPercent(reportMetrics.candidate_pass_rate)}
              </dd>
            </>
          )}
        {typeof reportMetrics.mean_difference === 'number' && (
          <>
            <dt className="ledger__key">平均差值</dt>
            <dd className="ledger__val">{reportMetrics.mean_difference.toFixed(3)}</dd>
          </>
        )}
        {typeof reportMetrics.ci_lower === 'number' && typeof reportMetrics.ci_upper === 'number' && (
          <>
            <dt className="ledger__key">95% 置信区间</dt>
            <dd className="ledger__val">
              {reportMetrics.ci_lower.toFixed(3)} 至 {reportMetrics.ci_upper.toFixed(3)}
            </dd>
          </>
        )}
        {typeof reportMetrics.confidence === 'number' && (
          <>
            <dt className="ledger__key">置信度</dt>
            <dd className="ledger__val">{formatPercent(reportMetrics.confidence)}</dd>
          </>
        )}
      </dl>

      {categories.length > 0 && (
        <div className="scroll-x" style={{ marginTop: 'var(--s3)' }}>
          <table className="record">
            <caption className="visually-hidden">
              按类别统计的匹配场景，以及其中有多少发生了回归
            </caption>
            <thead>
              <tr>
                <th scope="col">类别</th>
                <th scope="col" className="record__num">
                  匹配
                </th>
                <th scope="col" className="record__num">
                  已回归
                </th>
              </tr>
            </thead>
            <tbody>
              {categories.map(([category, bucket]) => (
                <tr key={category}>
                  <td>{caseCategoryLabel(category as Parameters<typeof caseCategoryLabel>[0])}</td>
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
