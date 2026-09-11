import type { LiveCase } from '../api/evaluation'
import { formatSignedScore } from '../lib/format'

interface Props {
  cases: readonly LiveCase[]
  /** Scenario ids the run executed on one version only, and which are excluded. */
  unmatchedScenarios: readonly string[]
  selectedCaseId: string | null
  onSelectCase: (caseId: string) => void
}

/**
 * The live run's tabulated record.
 *
 * One row per matched scenario, in the order the backend reported it, showing
 * both versions' status and the candidate's answer. The console's offline
 * table prints a 0..1 score per version because the fixture corpus computes
 * one; the live backend computes no per-case score, so this table prints the
 * status it did compute and a candidate latency delta, and stops there. A
 * score column here would be a number the backend never produced.
 */
export function LiveCaseTable({
  cases,
  unmatchedScenarios,
  selectedCaseId,
  onSelectCase,
}: Props): React.JSX.Element {
  const regressed = cases.filter((row) => row.regressed)

  return (
    <div className="record-wrap">
      <div className="filters">
        <div className="filters__group">
          <span className="u-micro">Matched scenarios</span>
          <span className="u-device">{cases.length}</span>
        </div>
        <div className="filters__group">
          <span className="u-micro">Regressed</span>
          <span className="u-device">{regressed.length}</span>
        </div>
        {unmatchedScenarios.length > 0 && (
          <div className="filters__group">
            <span className="u-micro">Excluded (one version only)</span>
            <span className="u-device">{unmatchedScenarios.length}</span>
          </div>
        )}
        <span className="u-micro" style={{ marginLeft: 'auto' }}>
          {cases.length} of {cases.length} matched cases
        </span>
      </div>

      <div className="scroll-x">
        <table className="record">
          <caption className="visually-hidden">
            Matched scenarios from the live run, with each version's status and the candidate's
            answer
          </caption>
          <thead>
            <tr>
              <th scope="col" className="record__num">
                No
              </th>
              <th scope="col">Case</th>
              <th scope="col">Category</th>
              <th scope="col">Diff.</th>
              <th scope="col" className="record__score-col">
                Baseline
              </th>
              <th scope="col" className="record__score-col">
                Candidate
              </th>
              <th scope="col">Candidate answer</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((row) => {
              const selected = selectedCaseId === row.candidate.id
              const answer = asText(row.candidate.output?.answer)
              const latency =
                typeof row.candidate.output?.latency_ms === 'number'
                  ? `${Math.round(row.candidate.output.latency_ms as number)} ms`
                  : null
              return (
                <tr key={row.candidate.id} aria-selected={selected}>
                  <td className="record__num record__case-no">
                    {String(row.n).padStart(2, '0')}
                  </td>
                  <td className="record__title-cell">
                    <button
                      type="button"
                      className="record__open"
                      onClick={() => onSelectCase(row.candidate.id)}
                    >
                      {row.scenarioId}
                    </button>
                    {row.regressed && (
                      <>
                        {' '}
                        <span className="chip chip--fail">regressed</span>
                      </>
                    )}
                  </td>
                  <td>
                    <span className="u-micro">{row.category}</span>
                  </td>
                  <td className="u-num">{row.difficulty.toFixed(2)}</td>
                  <td className="u-num">
                    <StatusChip status={row.baselineStatus} />
                  </td>
                  <td className="u-num">
                    <StatusChip status={row.candidateStatus} />
                  </td>
                  <td className="record__title-cell">
                    <span className="u-micro">{truncate(answer, 88)}</span>
                    {latency && <span className="u-device"> · {latency}</span>}
                    {row.latencyDeltaMs !== null && row.latencyDeltaMs !== 0 && (
                      <span
                        className={`u-device ${row.latencyDeltaMs < 0 ? 'record__delta--up' : 'record__delta--down'}`}
                      >
                        {' '}
                        {formatSignedScore(row.latencyDeltaMs / 1000)}s
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {cases.length === 0 && (
        <p className="u-micro" style={{ padding: 'var(--s4)' }}>
          The run has recorded no matched case yet. Start the run and this table fills as the
          executor reports each scenario.
        </p>
      )}

      <p className="u-micro" style={{ padding: 'var(--s3) var(--s4)', lineHeight: 1.6 }}>
        Scores are not shown because the evaluation service reports a pass/fail status per case and
        no per-case score. The offline fixture corpus does compute one; the live run does not, and
        this table prints only what the run produced.
      </p>
    </div>
  )
}

function StatusChip({ status }: { status: LiveCase['candidateStatus'] }): React.JSX.Element {
  const kind = status === 'passed' ? 'pass' : status === 'error' ? 'error' : 'fail'
  return <span className={`chip chip--${kind}`}>{status}</span>
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value || '—'
}
