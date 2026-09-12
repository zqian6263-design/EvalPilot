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
        <span className="notice__tag">实时</span>
        <span>
          以下数据来自正在运行的服务上的运行{' '}
          <code className="u-device">{evaluation.run.id.slice(0, 8)}</code>：
          {evaluation.counts.cases} 个场景，{evaluation.counts.evidence} 条证据，
          {evaluation.counts.findings} 条发现。
          {evaluation.sources.report
            ? '报告已生成。'
            : '报告尚未生成，因此下方的裁决即该运行的当前状态。'}
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
