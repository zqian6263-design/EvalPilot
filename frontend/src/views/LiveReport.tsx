import type { LiveEvaluation } from '../api/evaluation'
import type { LiveReportMetrics } from '../api/types'
import { SEVERITY_ORDER, formatPercent, formatStamp } from '../lib/format'
import { severityLabel } from '../i18n/labels'

interface Props {
  evaluation: LiveEvaluation
  report: { id: string; generated_at: string } | null
}

/**
 * The run's report, as a printed sheet.
 *
 * Every figure below is read from `GET /api/runs/{run_id}/report`. The report
 * now exposes the paired effect, confidence interval, and confidence. Where the
 * service reports no per-metric series or per-case score, the sheet says so
 * instead of borrowing the fixture corpus' equivalent. The fixture sheet is a
 * different document with different numbers, and mixing the two would make both
 * untrustworthy.
 */
export function LiveReportView({ evaluation, report }: Props): React.JSX.Element {
  const metrics = (evaluation.reportMetrics ?? {}) as LiveReportMetrics
  const { counts, verdict, findings } = evaluation

  const severityCounts = SEVERITY_ORDER.map((severity) => ({
    severity,
    count: findings.filter((finding) => finding.severity === severity).length,
  }))

  return (
    <div className="sheet">
      <header className="sheet__masthead">
        <div className="stack" style={{ gap: 'var(--s1)' }}>
          <span className="sheet__doctype">
            评估报告 · {evaluation.run.baseline_version} vs{' '}
            {evaluation.run.candidate_version}
          </span>
          <h1 className="sheet__title">
            {
              verdict === 'regression'
                ? '不要发布该候选版本'
                : verdict === 'localized-regression'
                  ? '检测到发布阻断项'
                  : '未检测到回归'
            }
          </h1>
        </div>
        <div className="stack" style={{ gap: 'var(--s1)', textAlign: 'right' }}>
          <span className="u-micro">报告来源</span>
          <span className="u-device">
            {evaluation.sources.report ? 'GET /api/runs/{id}/report' : '报告尚不可用'}
          </span>
        </div>
      </header>

      <section aria-label="摘要">
        <p className="sheet__summary">
          {evaluation.summary ||
            '该运行尚未完成，因此服务还没有生成报告。完成后结果会显示在这里。'}
        </p>
      </section>

      <section aria-label="报告详情">
        <dl className="ledger">
          <dt className="ledger__key">报告 ID</dt>
          <dd className="ledger__val">{report?.id ?? '尚未生成'}</dd>
          <dt className="ledger__key">生成时间</dt>
          <dd className="ledger__val">
            {report ? formatStamp(report.generated_at) : '尚未生成'}
          </dd>
          <dt className="ledger__key">运行 ID</dt>
          <dd className="ledger__val">{evaluation.run.id}</dd>
          <dt className="ledger__key">匹配场景</dt>
          <dd className="ledger__val">
            {metrics.matched_scenarios ?? '未报告'} 个匹配 ·{' '}
            {metrics.baseline_cases ?? '—'} 个基线场景 · {metrics.candidate_cases ?? '—'}{' '}
            个候选场景
          </dd>
          <dt className="ledger__key">是否检测到回归</dt>
          <dd className="ledger__val ledger__val--prose">
            {typeof metrics.regression_detected === 'boolean'
              ? metrics.regression_detected
                ? '是'
                : '否'
              : '未报告'}
            {metrics.regressed_scenarios && metrics.regressed_scenarios.length > 0 && (
              <> —— {metrics.regressed_scenarios.join('、')}</>
            )}
          </dd>
          {metrics.control_scenarios && metrics.control_scenarios.length > 0 && (
            <>
              <dt className="ledger__key">对照组</dt>
              <dd className="ledger__val ledger__val--prose">
                {metrics.control_scenarios.length} 个未变化场景作为对照：
                {metrics.control_scenarios.join('、')}
              </dd>
            </>
          )}
          <dt className="ledger__key">运行总计</dt>
          <dd className="ledger__val">
            {counts.cases} 个场景 · {counts.evidence} 条证据 · {counts.findings}{' '}
            条发现 · {counts.events} 条事件
          </dd>
        </dl>
      </section>

      <section aria-label="指标">
        <div className="block__head">
          <span className="u-label">指标</span>
          <span className="u-micro">由评估服务报告</span>
        </div>
        <table className="record">
          <caption className="visually-hidden">本次运行报告的聚合指标</caption>
          <thead>
            <tr>
              <th scope="col">指标</th>
              <th scope="col">数值</th>
            </tr>
          </thead>
          <tbody>
            <MetricRow
              label="基线版本通过率"
              value={
                typeof metrics.baseline_pass_rate === 'number'
                  ? formatPercent(metrics.baseline_pass_rate, 1)
                  : null
              }
            />
            <MetricRow
              label="候选版本通过率"
              value={
                typeof metrics.candidate_pass_rate === 'number'
                  ? formatPercent(metrics.candidate_pass_rate, 1)
                  : null
              }
            />
            <MetricRow
              label="基线版本加权得分"
              value={
                typeof metrics.baseline_score === 'number'
                  ? metrics.baseline_score.toFixed(3)
                  : null
              }
            />
            <MetricRow
              label="候选版本加权得分"
              value={
                typeof metrics.candidate_score === 'number'
                  ? metrics.candidate_score.toFixed(3)
                  : null
              }
            />
            <MetricRow
              label="匹配场景数"
              value={
                typeof metrics.matched_scenarios === 'number'
                  ? String(metrics.matched_scenarios)
                  : null
              }
            />
            <MetricRow
              label="平均得分差值"
              value={
                typeof metrics.mean_difference === 'number'
                  ? metrics.mean_difference.toFixed(3)
                  : null
              }
            />
            <MetricRow
              label="95% 置信区间"
              value={
                typeof metrics.ci_lower === 'number' && typeof metrics.ci_upper === 'number'
                  ? `${metrics.ci_lower.toFixed(3)} 至 ${metrics.ci_upper.toFixed(3)}`
                  : null
              }
            />
            <MetricRow
              label="配对效应量"
              value={
                typeof metrics.effect_size === 'number' ? metrics.effect_size.toFixed(3) : null
              }
            />
            <MetricRow
              label="置信度是否越过阈值"
              value={
                typeof metrics.confidence === 'number'
                  ? formatPercent(metrics.confidence, 1)
                  : null
              }
            />
            <MetricRow
              label="总体方向"
              value={typeof metrics.direction === 'string' ? metrics.direction : null}
            />
            <MetricRow
              label="回归是否已确认"
              value={
                typeof metrics.regression_confirmed === 'boolean'
                  ? metrics.regression_confirmed
                    ? '是'
                    : '否'
                  : null
              }
            />
          </tbody>
        </table>
        <p className="u-micro" style={{ padding: 'var(--s2) var(--s4)', lineHeight: 1.6 }}>
          聚合对比字段直接读自正在运行的评估服务。当前契约不提供逐指标、逐场景的分数序列；
          凡是控制台拿不到后端数值的地方，它都会如实说明，而不是借用夹具里的数字。
        </p>
      </section>

      <section aria-label="评估发现">
        <div className="block__head">
          <span className="u-label">评估发现（{findings.length}）</span>
          <span className="u-micro">
            {severityCounts.map(({ severity, count }) => `${count} ${severityLabel(severity)}`).join(' · ')}
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
                  <span className="u-device">场景 {finding.test_case_id.slice(0, 8)}</span>
                )}
              </div>
            </div>
          </article>
        ))}

        {findings.length === 0 && (
          <p className="u-micro">
            本次运行没有生成任何发现
            {evaluation.run.status === 'completed' ? '。' : '，暂时。'}
          </p>
        )}
      </section>

      <div className="signoff">
        <div className="signoff__line">
          <span className="u-micro">评估方</span>
          <span className="u-device">EvalPilot · 对已执行场景的确定性检查</span>
        </div>
        <div className="signoff__line">
          <span className="u-micro">复核人签署</span>
          <div className="signoff__rule" />
          <span className="u-micro">
            {evaluation.sources.report
              ? '指标读自正在运行的服务'
              : '报告尚未生成'}
          </span>
        </div>
      </div>
    </div>
  )
}

function MetricRow({ label, value }: { label: string; value: string | null }): React.JSX.Element {
  return (
    <tr>
      <td>{label}</td>
      <td className={`u-num${value === null ? ' u-micro' : ''}`}>
        {value ?? '该后端未报告此项'}
      </td>
    </tr>
  )
}
