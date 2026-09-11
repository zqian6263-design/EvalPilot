import type { LiveEvaluation } from '../api/evaluation'
import type { LiveReportMetrics } from '../api/types'
import { SEVERITY_ORDER, formatPercent, formatStamp } from '../lib/format'

interface Props {
  evaluation: LiveEvaluation
  report: { id: string; generated_at: string } | null
}

/**
 * The run's report, as a printed sheet.
 *
 * Every figure below is read from `GET /api/runs/{run_id}/report`. Where the
 * service reports nothing — there is no regression-confidence estimate, no
 * repeat count, and no per-metric breakdown — the sheet says so instead of
 * borrowing the fixture corpus' equivalent. The fixture sheet is a different
 * document with different numbers, and mixing the two would make both
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
            Evaluation report · {evaluation.run.baseline_version} vs{' '}
            {evaluation.run.candidate_version}
          </span>
          <h1 className="sheet__title">
            {verdict === 'regression' ? 'Do not ship this candidate' : 'No regression detected'}
          </h1>
        </div>
        <div className="stack" style={{ gap: 'var(--s1)', textAlign: 'right' }}>
          <span className="u-micro">Report source</span>
          <span className="u-device">
            {evaluation.sources.report ? 'GET /api/runs/{id}/report' : 'report not available'}
          </span>
        </div>
      </header>

      <section aria-label="Summary">
        <p className="sheet__summary">
          {evaluation.summary ||
            'The run has not completed, so the service has not generated a report. Results appear here once it does.'}
        </p>
      </section>

      <section aria-label="Report details">
        <dl className="ledger">
          <dt className="ledger__key">Report id</dt>
          <dd className="ledger__val">{report?.id ?? 'not generated'}</dd>
          <dt className="ledger__key">Generated</dt>
          <dd className="ledger__val">
            {report ? formatStamp(report.generated_at) : 'not generated'}
          </dd>
          <dt className="ledger__key">Run</dt>
          <dd className="ledger__val">{evaluation.run.id}</dd>
          <dt className="ledger__key">Matched scenarios</dt>
          <dd className="ledger__val">
            {metrics.matched_scenarios ?? 'not reported'} matched ·{' '}
            {metrics.baseline_cases ?? '—'} baseline case(s) · {metrics.candidate_cases ?? '—'}{' '}
            candidate case(s)
          </dd>
          <dt className="ledger__key">Regression detected</dt>
          <dd className="ledger__val ledger__val--prose">
            {typeof metrics.regression_detected === 'boolean'
              ? metrics.regression_detected
                ? 'yes'
                : 'no'
              : 'not reported'}
            {metrics.regressed_scenarios && metrics.regressed_scenarios.length > 0 && (
              <> — {metrics.regressed_scenarios.join(', ')}</>
            )}
          </dd>
          {metrics.control_scenarios && metrics.control_scenarios.length > 0 && (
            <>
              <dt className="ledger__key">Controls</dt>
              <dd className="ledger__val ledger__val--prose">
                {metrics.control_scenarios.length} unchanged scenario(s) serve as controls:{' '}
                {metrics.control_scenarios.join(', ')}
              </dd>
            </>
          )}
          <dt className="ledger__key">Run totals</dt>
          <dd className="ledger__val">
            {counts.cases} case(s) · {counts.evidence} evidence row(s) · {counts.findings}{' '}
            finding(s) · {counts.events} event(s)
          </dd>
        </dl>
      </section>

      <section aria-label="Metrics">
        <div className="block__head">
          <span className="u-label">Metrics</span>
          <span className="u-micro">as reported by the evaluation service</span>
        </div>
        <table className="record">
          <caption className="visually-hidden">Aggregate metrics reported for this run</caption>
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col">Value</th>
            </tr>
          </thead>
          <tbody>
            <MetricRow
              label="Baseline pass rate"
              value={
                typeof metrics.baseline_pass_rate === 'number'
                  ? formatPercent(metrics.baseline_pass_rate, 1)
                  : null
              }
            />
            <MetricRow
              label="Candidate pass rate"
              value={
                typeof metrics.candidate_pass_rate === 'number'
                  ? formatPercent(metrics.candidate_pass_rate, 1)
                  : null
              }
            />
            <MetricRow
              label="Baseline weighted score"
              value={
                typeof metrics.baseline_score === 'number'
                  ? metrics.baseline_score.toFixed(3)
                  : null
              }
            />
            <MetricRow
              label="Candidate weighted score"
              value={
                typeof metrics.candidate_score === 'number'
                  ? metrics.candidate_score.toFixed(3)
                  : null
              }
            />
            <MetricRow
              label="Matched scenarios"
              value={
                typeof metrics.matched_scenarios === 'number'
                  ? String(metrics.matched_scenarios)
                  : null
              }
            />
          </tbody>
        </table>
        <p className="u-micro" style={{ padding: 'var(--s2) var(--s4)', lineHeight: 1.6 }}>
          This service reports aggregate pass/score figures and no per-metric or per-case score, and
          no confidence estimate. Metrics the console can display but this run does not carry —
          citation coverage, groundedness, latency — are listed as unavailable on the console's
          metric panel rather than computed here.
        </p>
      </section>

      <section aria-label="Findings">
        <div className="block__head">
          <span className="u-label">Findings ({findings.length})</span>
          <span className="u-micro">
            {severityCounts.map(({ severity, count }) => `${count} ${severity}`).join(' · ')}
          </span>
        </div>

        {findings.map((finding) => (
          <article className="finding" key={finding.id} style={{ marginBottom: 'var(--s3)' }}>
            <div className="finding__rail">
              <span className={`finding__sev finding__sev--${finding.severity}`}>
                {finding.severity}
              </span>
              <span className="u-micro">conf {finding.confidence.toFixed(2)}</span>
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
                <span className="u-micro">{finding.evidence_ids.length} evidence link(s)</span>
                {finding.test_case_id && (
                  <span className="u-device">case {finding.test_case_id.slice(0, 8)}</span>
                )}
              </div>
            </div>
          </article>
        ))}

        {findings.length === 0 && (
          <p className="u-micro">
            No finding was generated for this run
            {evaluation.run.status === 'completed' ? '.' : ' yet.'}
          </p>
        )}
      </section>

      <div className="signoff">
        <div className="signoff__line">
          <span className="u-micro">Evaluated by</span>
          <span className="u-device">EvalPilot · deterministic checks over the executed cases</span>
        </div>
        <div className="signoff__line">
          <span className="u-micro">Reviewer sign-off</span>
          <div className="signoff__rule" />
          <span className="u-micro">
            {evaluation.sources.report
              ? 'metrics read from the running service'
              : 'report not yet generated'}
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
        {value ?? 'not reported by this backend'}
      </td>
    </tr>
  )
}
