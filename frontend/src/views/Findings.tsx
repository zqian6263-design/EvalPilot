import { useMemo, useState } from 'react'
import type { Severity } from '../api/types'
import type { Scenario } from '../fixtures/scenarios'
import { FINDINGS, REPORT } from '../fixtures/findings'
import { SEVERITY_ORDER, formatPercent } from '../lib/format'

interface Props {
  scenario: Scenario
  onOpenCase: (caseId: string) => void
}

/**
 * Findings, ordered by severity.
 *
 * Each finding shows its confidence, the cases behind it, and the evidence
 * count, so a reviewer can see how strongly the tool believes it before
 * deciding whether to read the argument.
 */
export function FindingsView({ scenario, onOpenCase }: Props): React.JSX.Element {
  const [severity, setSeverity] = useState<Severity | 'all'>('all')

  const findings = useMemo(() => {
    const list = severity === 'all' ? FINDINGS : FINDINGS.filter((f) => f.severity === severity)
    return [...list].sort(
      (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity),
    )
  }, [severity])

  const counts = useMemo(() => {
    const map = new Map<Severity, number>()
    for (const finding of FINDINGS) map.set(finding.severity, (map.get(finding.severity) ?? 0) + 1)
    return map
  }, [])

  return (
    <div className="sheet">
      <header className="sheet__masthead">
        <div className="stack" style={{ gap: 'var(--s1)' }}>
          <span className="sheet__doctype">
            Findings · {scenario.baselineVersion} vs {scenario.candidateVersion}
          </span>
          <h1 className="sheet__title">
            {scenario.verdict === 'regression'
              ? 'What the change broke'
              : scenario.verdict === 'improvement'
                ? 'What the change improved'
                : 'Nothing moved'}
          </h1>
        </div>
        <div className="rocker" role="group" aria-label="Filter findings by severity">
          <button
            type="button"
            className="rocker__pos"
            aria-pressed={severity === 'all'}
            onClick={() => setSeverity('all')}
          >
            All ({FINDINGS.length})
          </button>
          {SEVERITY_ORDER.map((value) => (
            <button
              key={value}
              type="button"
              className="rocker__pos"
              aria-pressed={severity === value}
              onClick={() => setSeverity(value)}
              disabled={(counts.get(value) ?? 0) === 0}
            >
              {value} ({counts.get(value) ?? 0})
            </button>
          ))}
        </div>
      </header>

      <div className="ledger-strip">
        {SEVERITY_ORDER.map((value) => (
          <div className="ledger-strip__cell" key={value}>
            <span className="u-micro">{value}</span>
            <span
              className={`ledger-strip__value${
                (value === 'high' || value === 'critical') && (counts.get(value) ?? 0) > 0
                  ? ' ledger-strip__value--alert'
                  : ''
              }`}
            >
              {counts.get(value) ?? 0}
            </span>
          </div>
        ))}
        <div className="ledger-strip__cell">
          <span className="u-micro">Evidence links</span>
          <span className="ledger-strip__value">
            {FINDINGS.reduce((sum, finding) => sum + finding.evidence_ids.length, 0)}
          </span>
        </div>
      </div>

      {findings.length === 0 && (
        <p className="u-micro">
          No finding at this severity. The run recorded {FINDINGS.length} finding(s) in total.
        </p>
      )}

      {findings.map((finding) => {
        const primaryCase = finding.test_case_id
          ? scenario.outcomes.find((o) => o.caseId === finding.test_case_id)
          : undefined
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
                  {finding.evidence_ids.length} evidence link(s)
                </span>
                {primaryCase && (
                  <button
                    type="button"
                    className="record__open"
                    onClick={() => onOpenCase(primaryCase.caseId)}
                  >
                    Open case {String(primaryCase.spec.n).padStart(2, '0')} — {primaryCase.spec.title}
                  </button>
                )}
                {!primaryCase && finding.severity === 'info' && (
                  <span className="u-micro">Aggregate finding across the matched set</span>
                )}
              </div>
            </div>
          </article>
        )
      })}

      <div className="signoff">
        <div className="signoff__line">
          <span className="u-micro">Report generated</span>
          <span className="u-device">{REPORT.generated_at.replace('T', ' ')}</span>
        </div>
        <div className="signoff__line">
          <span className="u-micro">Reviewed by</span>
          <div className="signoff__rule" />
          <span className="u-micro">
            {formatPercent(scenario.comparison.regression_confidence)} confidence in the verdict
          </span>
        </div>
      </div>
    </div>
  )
}
