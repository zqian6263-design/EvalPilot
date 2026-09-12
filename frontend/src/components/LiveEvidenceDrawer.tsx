import type { Evidence } from '../api/types'
import type { LiveCase } from '../api/evaluation'
import { formatScore } from '../lib/format'
import { caseCategoryLabel, caseStatusLabel } from '../i18n/labels'

interface Props {
  /** The case row whose candidate side is open. */
  row: LiveCase
  evidence: readonly Evidence[]
  onClose: () => void
}

const str = (value: unknown, fallback = ''): string => (typeof value === 'string' ? value : fallback)
const num = (value: unknown, fallback = 0): number => (typeof value === 'number' ? value : fallback)

/**
 * One evidence row, rendered by kind.
 *
 * The live backend emits four kinds — `citation`, `trace`, `text`, `metric` —
 * with a flat payload, where the fixture transport's payloads are richer and
 * differently keyed. This renders the live payload as it is rather than
 * reshaping it into the fixture layout, because a reshaped payload would read
 * as a field the backend never sent.
 */
function EvidenceRow({ item }: { item: Evidence }): React.JSX.Element {
  const payload = item.payload

  if (item.kind === 'citation') {
    return (
      <article className="ev">
        <header className="ev__head">
          <span className="ev__kind">引用</span>
          <span className="u-micro">{str(payload.title, item.uri ?? '文档')}</span>
        </header>
        <div className="ev__body">
          <p className="citation__tick tabular u-device">{item.uri ?? str(payload.doc_id)}</p>
          <p className="answer__text">{str(payload.quote)}</p>
        </div>
      </article>
    )
  }

  if (item.kind === 'trace') {
    const toolCalls = Array.isArray(payload.tool_calls) ? payload.tool_calls : []
    return (
      <article className="ev">
        <header className="ev__head">
          <span className="ev__kind">工具调用轨迹</span>
          <span className="u-micro">
            {toolCalls.length} 次工具调用 · {item.uri ? '已存工件' : '无工件'}
          </span>
        </header>
        <div className="ev__body">
          <p className="ev__label">判断理由</p>
          <p>{str(payload.rationale, '未记录理由')}</p>
          {toolCalls.length > 0 && (
            <pre className="log" tabIndex={0}>
              {JSON.stringify(toolCalls, null, 2)}
            </pre>
          )}
        </div>
      </article>
    )
  }

  if (item.kind === 'text') {
    return (
      <article className="ev">
        <header className="ev__head">
          <span className="ev__kind">{payload.question !== undefined ? '提问' : '文本'}</span>
          <span className="u-micro">{payload.refused === true ? '已拒答' : '已作答'}</span>
        </header>
        <div className="ev__body">
          {payload.question !== undefined && <p className="prompt">{str(payload.question)}</p>}
          {payload.answer !== undefined && <p className="answer__text">{str(payload.answer)}</p>}
        </div>
      </article>
    )
  }

  if (item.kind === 'metric') {
    return (
      <article className="ev">
        <header className="ev__head">
          <span className="ev__kind">实测</span>
          <span className="u-micro">由执行器记录</span>
        </header>
        <div className="ev__body">
          <div className="scored">
            {Object.entries(payload).map(([key, value]) => (
              <div className="scored__row" key={key}>
                <span className="u-label">{key}</span>
                <div />
                <span className="scored__value u-device">
                  {typeof value === 'number' ? value : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </article>
    )
  }

  return (
    <article className="ev">
      <header className="ev__head">
        <span className="ev__kind">{item.kind}</span>
        <span className="u-micro">{item.uri ?? '无工件'}</span>
      </header>
      <div className="ev__body">
        <pre className="log" tabIndex={0}>
          {JSON.stringify(payload, null, 2)}
        </pre>
      </div>
    </article>
  )
}

/**
 * The evidence packet for one live case.
 *
 * Both answers, the citations each returned, the tool trace, and the values
 * the executor measured — read from `GET /api/runs/{run_id}`'s evidence rows
 * for this case, in the order the run recorded them. Nothing is synthesised
 * when a kind is absent: a case with three rows shows three.
 */
export function LiveEvidenceDrawer({ row, evidence, onClose }: Props): React.JSX.Element {
  const baseline = evidence.filter((item) => item.test_case_id === row.baseline.id)
  const candidate = evidence.filter((item) => item.test_case_id === row.candidate.id)
  const ordered = [...baseline, ...candidate]

  const baselineAnswer = str(row.baseline.output?.answer)
  const candidateAnswer = str(row.candidate.output?.answer)
  const baselineLatency = num(row.baseline.output?.latency_ms)
  const candidateLatency = num(row.candidate.output?.latency_ms)

  return (
    <>
      <button
        type="button"
        className="drawer__scrim"
        aria-label="关闭证据包"
        onClick={onClose}
      />
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`场景 ${row.n} 的证据包`}
      >
        <header className="drawer__head">
          <div className="drawer__title">
            <span className="u-micro">
              场景 {String(row.n).padStart(2, '0')} · {caseCategoryLabel(row.category)} · 难度{' '}
              {row.difficulty.toFixed(2)}
            </span>
            <h2 className="drawer__case-title">{row.scenarioId}</h2>
            <span className="u-device">
              基线 {caseStatusLabel(row.baselineStatus)}（{baselineLatency} ms）→ 候选{' '}
              {caseStatusLabel(row.candidateStatus)}（{candidateLatency} ms）
            </span>
          </div>
          <button type="button" className="drawer__close" onClick={onClose} autoFocus>
            关闭
          </button>
        </header>

        <div className="drawer__body">
          <p className="u-micro" style={{ lineHeight: 1.6 }}>
            问题：{str(row.candidate.input?.question, '（未记录）')}
          </p>

          <article className="ev">
            <header className="ev__head">
              <span className="ev__kind">回答</span>
              <span className="u-micro">两个版本，按实际执行结果</span>
            </header>
            <div className="ev__body">
              <div className="answers">
                <div className="answer answer--baseline">
                  <div className="answer__head">
                    <span className="u-label">基线版本</span>
                    <span className="u-device">
                      {caseStatusLabel(row.baselineStatus)} · {formatScore(baselineLatency / 1000)}s
                    </span>
                  </div>
                  <p className="answer__text">{baselineAnswer || '（未记录回答）'}</p>
                </div>
                <div className="answer answer--candidate">
                  <div className="answer__head">
                    <span className="u-label">候选版本</span>
                    <span className="u-device">
                      {caseStatusLabel(row.candidateStatus)} · {formatScore(candidateLatency / 1000)}s
                    </span>
                  </div>
                  <p className="answer__text">{candidateAnswer || '（未记录回答）'}</p>
                </div>
              </div>
            </div>
          </article>

          <p className="u-micro">
            该场景共记录 {ordered.length} 条证据（基线 {baseline.length} 条，候选 {candidate.length}{' '}
            条）。本次运行不记录逐场景分数，因此这里也不显示。
          </p>

          {ordered.map((item) => (
            <EvidenceRow key={item.id} item={item} />
          ))}

          {ordered.length === 0 && (
            <p className="u-micro">
              该场景还没有证据记录。执行器每完成一个版本就会写入一条。
            </p>
          )}
        </div>
      </aside>
    </>
  )
}
