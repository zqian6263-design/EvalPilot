import { useEffect, useState } from 'react'
import type { MetricValue, Report } from '../api/types'
import type { Transport } from '../api/transport'
import type { Scenario } from '../fixtures/scenarios'
import { FINDINGS, REPORT, REPORT_RUN_IDS } from '../fixtures/findings'
import { RUN_SUMMARY } from '../fixtures/metrics'
import {
  SEVERITY_ORDER,
  formatMetricDelta,
  formatMetricValue,
  formatPercent,
  formatStamp,
} from '../lib/format'
import { metricLabel, severityLabel } from '../i18n/labels'

interface Props {
  scenario: Scenario
  transport: Transport | null
}

const METRIC_ORDER = [
  'task_success',
  'citation_coverage',
  'correct_refusal',
  'format_compliance',
  'groundedness',
  'latency_p50',
  'answer_tokens',
] as const

/**
 * The generated report, rendered as a printed sheet.
 *
 * When a backend is live the report is fetched from
 * `GET /api/runs/{run_id}/report`; the response is the frozen `Report` shape,
 * whose `metrics` field is an untyped object. The renderer treats every metric
 * as optional and says "not reported" rather than inventing a value, so an
 * unfamiliar payload degrades instead of breaking.
 */
export function ReportView({ scenario, transport }: Props): React.JSX.Element {
  const fallback: Report = { ...REPORT, run_id: REPORT_RUN_IDS[scenario.id] }
  const [report, setReport] = useState<Report>(fallback)
  const [source, setSource] = useState<'fixtures' | 'backend'>(
    transport?.describe().live ? 'backend' : 'fixtures',
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setReport({ ...REPORT, run_id: REPORT_RUN_IDS[scenario.id] })
    setError(null)
  }, [scenario.id])

  useEffect(() => {
    if (!transport || !transport.describe().live) {
      setSource('fixtures')
      return
    }
    let cancelled = false
    transport
      .getReport(REPORT_RUN_IDS[scenario.id])
      .then((fetched) => {
        if (cancelled) return
        setReport(fetched)
        setSource('backend')
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        setSource('fixtures')
        setError(cause instanceof Error ? cause.message : '报告请求失败')
      })
    return () => {
      cancelled = true
    }
  }, [transport, scenario.id])

  const metrics = { ...RUN_SUMMARY.metrics, ...scenario.metrics }
  const reportedMetrics = (report.metrics ?? {}) as Record<string, unknown>
  const findings = report.findings.length > 0 ? report.findings : [...FINDINGS]

  const metricValue = (key: string): MetricValue | null => {
    const local = metrics[key]
    if (local) return local
    const remote = reportedMetrics[key]
    if (remote && typeof remote === 'object' && 'baseline' in remote) return remote as MetricValue
    return null
  }

  return (
    <div className="sheet">
      <header className="sheet__masthead">
        <div className="stack" style={{ gap: 'var(--s1)' }}>
          <span className="sheet__doctype">
            评估报告 · {scenario.baselineVersion} vs {scenario.candidateVersion}
          </span>
          <h1 className="sheet__title">
            {scenario.verdict === 'regression'
              ? '不要发布该候选版本'
              : scenario.verdict === 'improvement'
                ? '可以发布该候选版本'
                : '可以安全发布，没有任何变化'}
          </h1>
        </div>
        <div className="stack" style={{ gap: 'var(--s1)', textAlign: 'right' }}>
          <span className="u-micro">报告来源</span>
          <span className="u-device">
            {source === 'backend' ? 'GET /api/runs/{id}/report' : '内置夹具数据'}
          </span>
          {error && <span className="u-micro">回退原因：{error}</span>}
        </div>
      </header>

      <section aria-label="摘要">
        <p className="sheet__summary">{report.summary || scenario.summary}</p>
      </section>

      <section aria-label="报告详情">
        <dl className="ledger">
          <dt className="ledger__key">报告 ID</dt>
          <dd className="ledger__val">{report.id}</dd>
          <dt className="ledger__key">生成时间</dt>
          <dd className="ledger__val">{formatStamp(report.generated_at)}</dd>
          <dt className="ledger__key">受测变更</dt>
          <dd className="ledger__val ledger__val--prose">{scenario.change.summary}</dd>
          {scenario.change.settings.map((setting) => (
            <div key={setting.key} style={{ display: 'contents' }}>
              <dt className="ledger__key">{setting.key}</dt>
              <dd className="ledger__val">
                {setting.baseline} → {setting.candidate}
                {setting.baseline === setting.candidate ? '（未变更）' : ''}
              </dd>
            </div>
          ))}
          <dt className="ledger__key">匹配场景</dt>
          <dd className="ledger__val">
            {scenario.comparison.matched_cases} 个场景 · {scenario.comparison.repeats} 次重复采样 ·{' '}
            {formatPercent(scenario.comparison.regression_confidence)} 回归置信度
          </dd>
          <dt className="ledger__key">裁决</dt>
          <dd className="ledger__val ledger__val--prose">
            {scenario.comparison.stable_regressions} 个稳定回归，{scenario.comparison.noise_only}{' '}
            个单次采样标记未能复现，已排除在外。
          </dd>
        </dl>
      </section>

      <section aria-label="指标">
        <div className="block__head">
          <span className="u-label">指标</span>
          <span className="u-micro">
            {source === 'backend' ? '来自后端报告' : '由夹具语料计算得出'}
          </span>
        </div>
        <table className="record">
          <caption className="visually-hidden">报告的指标：基线版本与候选版本对比</caption>
          <thead>
            <tr>
              <th scope="col">指标</th>
              <th scope="col">{scenario.baselineVersion}</th>
              <th scope="col">{scenario.candidateVersion}</th>
              <th scope="col">变化</th>
              <th scope="col">n</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_ORDER.map((key) => {
              const metric = metricValue(key)
              if (!metric) {
                return (
                  <tr key={key}>
                    <td>{key}</td>
                    <td colSpan={4} className="u-micro">
                      该后端未报告此项
                    </td>
                  </tr>
                )
              }
              const raw = metric.candidate - metric.baseline
              const worse = raw !== 0 && (metric.direction === 'lower' ? raw > 0 : raw < 0)
              return (
                <tr key={key}>
                  <td>{metricLabel(key, metric.label)}</td>
                  <td className="u-num">{formatMetricValue(metric, metric.baseline)}</td>
                  <td className={`u-num ${worse ? 'record__score--down' : raw !== 0 ? 'record__score--up' : ''}`}>
                    {formatMetricValue(metric, metric.candidate)}
                  </td>
                  <td className={`u-num ${worse ? 'record__delta--down' : raw !== 0 ? 'record__delta--up' : ''}`}>
                    {formatMetricDelta(metric, metric.baseline, metric.candidate)}
                  </td>
                  <td className="u-num">{metric.n}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      <section aria-label="评估发现">
        <div className="block__head">
          <span className="u-label">
            评估发现（{findings.length}）
          </span>
          <span className="u-micro">
            {SEVERITY_ORDER.map(
              (severity) =>
                `${findings.filter((f) => f.severity === severity).length} ${severityLabel(severity)}`,
            ).join(' · ')}
          </span>
        </div>

        {findings.map((finding) => (
          <article className="finding" key={finding.id} style={{ marginBottom: 'var(--s3)' }}>
            <div className="finding__rail">
              <span className={`finding__sev finding__sev--${finding.severity}`}>
                {severityLabel(finding.severity)}
              </span>
              <span className="u-micro">置信度 {finding.confidence.toFixed(2)}</span>
            </div>
            <div className="finding__body">
              <h2 className="finding__title">{finding.title}</h2>
              <p className="finding__desc">{finding.description}</p>
              {finding.recommendation && (
                <div className="finding__rec">
                  <span className="u-micro">改进建议</span>
                  <p>{finding.recommendation}</p>
                </div>
              )}
              <div className="finding__evidence">
                <span className="u-micro">{finding.evidence_ids.length} 条证据关联</span>
                {finding.test_case_id && (
                  <span className="u-device">场景 {finding.test_case_id.slice(0, 6)}</span>
                )}
              </div>
            </div>
          </article>
        ))}
      </section>

      <div className="signoff">
        <div className="signoff__line">
          <span className="u-micro">评估方</span>
          <span className="u-device">EvalPilot · 确定性检查 + 评分表裁判</span>
        </div>
        <div className="signoff__line">
          <span className="u-micro">复核人签署</span>
          <div className="signoff__rule" />
          <span className="u-micro">
            {source === 'backend'
              ? '指标读自正在运行的服务'
              : '离线演示 —— 夹具数据'}
          </span>
        </div>
      </div>
    </div>
  )
}
