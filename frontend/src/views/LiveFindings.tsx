import type { LiveEvaluation } from '../api/evaluation'
import { evidenceForFinding, severityCounts } from '../api/evaluation'
import { SEVERITY_ORDER } from '../lib/format'
import { severityLabel } from '../i18n/labels'

interface Props {
  evaluation: LiveEvaluation
  onSelectCase: (caseId: string) => void
}

/**
 * The run's findings, each with the evidence rows it cites.
 *
 * `docs/SPEC.md` requires every finding to link to the exact input, output,
 * tool trace and evaluator rationale. In a live run that link is
 * `Finding.evidence_ids` → `run.evidence`, so each finding below expands to the
 * rows it actually resolved to and names any id that resolved to nothing. A
 * finding whose links dangle is shown as dangling rather than as a count that
 * happens to look complete.
 */
export function LiveFindings({ evaluation, onSelectCase }: Props): React.JSX.Element {
  const { findings } = evaluation
  const counts = severityCounts(findings)
  return (
    <div className="sheet">
      <header className="sheet__masthead">
        <div className="stack" style={{ gap: 'var(--s1)' }}>
          <span className="sheet__doctype">
            评估发现 · {evaluation.run.baseline_version} vs {evaluation.run.candidate_version}
          </span>
          <h1 className="sheet__title">
            {evaluation.verdict === 'no-regression' ? '没有任何变化' : '本次变更破坏了什么'}
          </h1>
        </div>
        <div className="stack" style={{ gap: 'var(--s1)', textAlign: 'right' }}>
          <span className="u-micro">来源</span>
          <span className="u-device">GET /api/runs/{'{id}'}/report</span>
        </div>
      </header>

      <div className="ledger-strip">
        {SEVERITY_ORDER.map((value) => (
          <div className="ledger-strip__cell" key={value}>
            <span className="u-micro">{severityLabel(value)}</span>
            <span
              className={`ledger-strip__value${
                (value === 'high' || value === 'critical') && counts[value] > 0
                  ? ' ledger-strip__value--alert'
                  : ''
              }`}
            >
              {counts[value]}
            </span>
          </div>
        ))}
        <div className="ledger-strip__cell">
          <span className="u-micro">证据关联</span>
          <span className="ledger-strip__value">
            {findings.reduce((sum, finding) => sum + finding.evidence_ids.length, 0)}
          </span>
        </div>
      </div>

      {findings.length === 0 && (
        <p className="u-micro">
          本次运行没有记录任何发现。尚未进入评估阶段的运行在这里同样为空 —— 完成后打开报告即可。
        </p>
      )}

      {findings.map((finding) => {
        const { rows, dangling } = evidenceForFinding(evaluation.detail, finding)
        const primaryCase = evaluation.cases.find(
          (row) => row.candidate.id === finding.test_case_id || row.baseline.id === finding.test_case_id,
        )
        return (
          <article className="finding" key={finding.id}>
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
                <span className="u-micro">
                  {finding.evidence_ids.length} 条证据关联中已解析 {rows.length} 条
                </span>
                {primaryCase && (
                  <button
                    type="button"
                    className="record__open"
                    onClick={() => onSelectCase(primaryCase.candidate.id)}
                  >
                    打开场景 {String(primaryCase.n).padStart(2, '0')} — {primaryCase.scenarioId}
                  </button>
                )}
                {!primaryCase && <span className="u-micro">跨匹配场景的汇总性发现</span>}
              </div>

              {rows.length > 0 && (
                <ul className="citation-list" style={{ marginTop: 'var(--s2)' }}>
                  {rows.map((row) => (
                    <li key={row.id} className="citation">
                      <span className="citation__tick tabular u-device">{row.kind}</span>
                      <span className="u-device">
                        {row.uri ?? describePayload(row.payload)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {dangling.length > 0 && (
                <p className="u-micro" style={{ color: 'var(--signal)' }}>
                  该发现中有 {dangling.length} 个证据 ID 在本次运行中找不到对应记录：
                  {dangling.join('、')}
                </p>
              )}
            </div>
          </article>
        )
      })}

      <div className="signoff">
        <div className="signoff__line">
          <span className="u-micro">报告生成情况</span>
          <span className="u-device">
            {evaluation.sources.report
              ? `报告的 ${evaluation.counts.findings} 条发现`
              : '报告尚不可用'}
          </span>
        </div>
        <div className="signoff__line">
          <span className="u-micro">复核人</span>
          <div className="signoff__rule" />
          <span className="u-micro">
            以上每条发现都关联到本次运行记录的证据。
          </span>
        </div>
      </div>
    </div>
  )
}

/** A short, honest stand-in for an evidence row that carries no uri. */
function describePayload(payload: Record<string, unknown>): string {
  const keys = Object.keys(payload)
  return keys.length > 0 ? `payload：${keys.join('、')}` : '无 payload'
}
