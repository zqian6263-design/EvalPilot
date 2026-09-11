import type { LiveEvaluation } from '../api/evaluation'
import { evidenceForFinding, severityCounts } from '../api/evaluation'
import { SEVERITY_ORDER } from '../lib/format'

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
            Findings · {evaluation.run.baseline_version} vs {evaluation.run.candidate_version}
          </span>
          <h1 className="sheet__title">
            {evaluation.verdict === 'regression' ? 'What the change broke' : 'Nothing moved'}
          </h1>
        </div>
        <div className="stack" style={{ gap: 'var(--s1)', textAlign: 'right' }}>
          <span className="u-micro">Source</span>
          <span className="u-device">GET /api/runs/{'{id}'}/report</span>
        </div>
      </header>

      <div className="ledger-strip">
        {SEVERITY_ORDER.map((value) => (
          <div className="ledger-strip__cell" key={value}>
            <span className="u-micro">{value}</span>
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
          <span className="u-micro">Evidence links</span>
          <span className="ledger-strip__value">
            {findings.reduce((sum, finding) => sum + finding.evidence_ids.length, 0)}
          </span>
        </div>
      </div>

      {findings.length === 0 && (
        <p className="u-micro">
          This run recorded no findings. A run that has not reached its evaluation stage yet shows
          none here either — open the report once it completes.
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
                {finding.severity}
              </span>
              <span className="u-micro">confidence {finding.confidence.toFixed(2)}</span>
            </div>

            <div className="finding__body">
              <h2 className="finding__title">{finding.title}</h2>
              <p className="finding__desc">{finding.description}</p>

              {finding.recommendation && (
                <div className="finding__rec">
                  <span className="u-micro">Recommendation</span>
                  <p>{finding.recommendation}</p>
                </div>
              )}

              <div className="finding__evidence">
                <span className="u-micro">
                  {rows.length} of {finding.evidence_ids.length} evidence link(s) resolved
                </span>
                {primaryCase && (
                  <button
                    type="button"
                    className="record__open"
                    onClick={() => onSelectCase(primaryCase.candidate.id)}
                  >
                    Open case {String(primaryCase.n).padStart(2, '0')} — {primaryCase.scenarioId}
                  </button>
                )}
                {!primaryCase && <span className="u-micro">Aggregate finding across the matched set</span>}
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
                  {dangling.length} evidence id(s) in this finding resolve to no row in the run:{' '}
                  {dangling.join(', ')}
                </p>
              )}
            </div>
          </article>
        )
      })}

      <div className="signoff">
        <div className="signoff__line">
          <span className="u-micro">Report generated</span>
          <span className="u-device">
            {evaluation.sources.report
              ? `${evaluation.counts.findings} finding(s) from the report`
              : 'report not available yet'}
          </span>
        </div>
        <div className="signoff__line">
          <span className="u-micro">Reviewed by</span>
          <div className="signoff__rule" />
          <span className="u-micro">
            Every finding above links to the evidence rows this run recorded.
          </span>
        </div>
      </div>
    </div>
  )
}

/** A short, honest stand-in for an evidence row that carries no uri. */
function describePayload(payload: Record<string, unknown>): string {
  const keys = Object.keys(payload)
  return keys.length > 0 ? `payload: ${keys.join(', ')}` : 'no payload'
}
