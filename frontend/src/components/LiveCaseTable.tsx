import type { LiveCase } from '../api/evaluation'
import { formatSignedScore } from '../lib/format'
import { caseCategoryLabel, caseStatusLabel } from '../i18n/labels'

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
          <span className="u-micro">匹配场景</span>
          <span className="u-device">{cases.length}</span>
        </div>
        <div className="filters__group">
          <span className="u-micro">已回归</span>
          <span className="u-device">{regressed.length}</span>
        </div>
        {unmatchedScenarios.length > 0 && (
          <div className="filters__group">
            <span className="u-micro">已排除（仅单侧版本）</span>
            <span className="u-device">{unmatchedScenarios.length}</span>
          </div>
        )}
        <span className="u-micro" style={{ marginLeft: 'auto' }}>
          {cases.length} / {cases.length} 个匹配场景
        </span>
      </div>

      <div className="scroll-x">
        <table className="record">
          <caption className="visually-hidden">
            实时运行中的匹配场景，含每个版本的状态与候选版本的回答
          </caption>
          <thead>
            <tr>
              <th scope="col" className="record__num">
                编号
              </th>
              <th scope="col">场景</th>
              <th scope="col">类别</th>
              <th scope="col">难度</th>
              <th scope="col" className="record__score-col">
                基线版本
              </th>
              <th scope="col" className="record__score-col">
                候选版本
              </th>
              <th scope="col">候选版本回答</th>
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
                        <span className="chip chip--fail">已回归</span>
                      </>
                    )}
                  </td>
                  <td>
                    <span className="u-micro">{caseCategoryLabel(row.category)}</span>
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
          该运行尚未记录到任何匹配场景。启动运行后，执行器每报告一个场景，此表就会填入一行。
        </p>
      )}

      <p className="u-micro" style={{ padding: 'var(--s3) var(--s4)', lineHeight: 1.6 }}>
        这里不显示分数，因为评估服务按场景给出的是通过／未通过状态，而不是逐场景分数。离线夹具语料会计算分数，
        实时运行则不会；本表只打印该运行真正产生的数据。
      </p>
    </div>
  )
}

function StatusChip({ status }: { status: LiveCase['candidateStatus'] }): React.JSX.Element {
  const kind = status === 'passed' ? 'pass' : status === 'error' ? 'error' : 'fail'
  return <span className={`chip chip--${kind}`}>{caseStatusLabel(status)}</span>
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value || '—'
}
