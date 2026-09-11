import { useMemo } from 'react'
import type { LiveEvaluation } from '../api/evaluation'
import type { LiveReportMetrics } from '../api/types'
import { LiveCaseTable } from '../components/LiveCaseTable'
import { LiveEvidenceDrawer } from '../components/LiveEvidenceDrawer'
import { LiveMetrics } from '../components/LiveMetrics'
import { LiveRunSummary } from '../components/LiveRunSummary'

interface Props {
  evaluation: LiveEvaluation
  reportMetrics: Record<string, unknown>
  reportGeneratedAt: string | null
  /** The row's position in the record, 1-based, as the URL carries it. */
  selectedCaseId: string | null
  onSelectCase: (caseId: string) => void
  onClearSelection: () => void
}

/**
 * The run console for a run that exists on the backend.
 *
 * Reading order matches the offline console — verdict, record, evidence — and
 * that is the only thing the two share. Every panel here renders what the run
 * produced: the case table shows the statuses the evaluator assigned, the
 * metric panel names the one metric the service reports, and the evidence
 * drawer opens the rows the run recorded for that case. Where the service
 * reports nothing, the panel says so rather than showing a fixture number in
 * live clothing.
 */
export function LiveConsole({
  evaluation,
  reportMetrics,
  reportGeneratedAt,
  selectedCaseId,
  onSelectCase,
  onClearSelection,
}: Props): React.JSX.Element {
  const selectedRow = useMemo(() => {
    if (selectedCaseId === null) return null
    const index = Number(selectedCaseId)
    if (!Number.isInteger(index) || index < 1) return null
    return evaluation.cases[index - 1] ?? null
  }, [evaluation.cases, selectedCaseId])

  const metrics = reportMetrics as LiveReportMetrics

  return (
    <>
      <div className="notice notice--live">
        <span className="notice__tag">Live</span>
        <span>
          These figures come from run{' '}
          <code className="u-device">{evaluation.run.id.slice(0, 8)}</code> on the running service:{' '}
          {evaluation.counts.cases} case(s), {evaluation.counts.evidence} evidence row(s),{' '}
          {evaluation.counts.findings} finding(s).
          {evaluation.sources.report
            ? ' The report has been generated.'
            : ' The report has not been generated yet, so the verdict below is the run status.'}
        </span>
      </div>

      <div className="console">
        <div className="console__tape">
          <LiveRunSummary
            evaluation={evaluation}
            reportMetrics={metrics}
            reportGeneratedAt={reportGeneratedAt}
          />
          <LiveCaseTable
            cases={evaluation.cases}
            unmatchedScenarios={evaluation.unmatchedScenarios}
            selectedCaseId={selectedRow?.candidate.id ?? null}
            onSelectCase={onSelectCase}
          />
        </div>

        <div className="console__side">
          <LiveMetrics
            rows={evaluation.metrics}
            baselineVersion={evaluation.run.baseline_version}
            candidateVersion={evaluation.run.candidate_version}
            live
          />
        </div>
      </div>

      {selectedRow && (
        <LiveEvidenceDrawer
          row={selectedRow}
          evidence={evaluation.evidence}
          onClose={onClearSelection}
        />
      )}
    </>
  )
}
