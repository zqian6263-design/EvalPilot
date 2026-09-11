import type { Evidence } from '../api/types'
import type { LiveCase } from '../api/evaluation'
import { formatScore } from '../lib/format'

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
          <span className="ev__kind">citation</span>
          <span className="u-micro">{str(payload.title, item.uri ?? 'document')}</span>
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
          <span className="ev__kind">tool trace</span>
          <span className="u-micro">
            {toolCalls.length} tool call(s) · {item.uri ? 'artifact stored' : 'no artifact'}
          </span>
        </header>
        <div className="ev__body">
          <p className="ev__label">Rationale</p>
          <p>{str(payload.rationale, 'no rationale recorded')}</p>
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
          <span className="ev__kind">{payload.question !== undefined ? 'prompt' : 'text'}</span>
          <span className="u-micro">{payload.refused === true ? 'refused' : 'answered'}</span>
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
          <span className="ev__kind">measured</span>
          <span className="u-micro">recorded by the executor</span>
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
        <span className="u-micro">{item.uri ?? 'no artifact'}</span>
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
        aria-label="Close the evidence packet"
        onClick={onClose}
      />
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`Evidence packet for case ${row.n}`}
      >
        <header className="drawer__head">
          <div className="drawer__title">
            <span className="u-micro">
              Case {String(row.n).padStart(2, '0')} · {row.category} · difficulty{' '}
              {row.difficulty.toFixed(2)}
            </span>
            <h2 className="drawer__case-title">{row.scenarioId}</h2>
            <span className="u-device">
              baseline {row.baselineStatus} ({baselineLatency} ms) → candidate{' '}
              {row.candidateStatus} ({candidateLatency} ms)
            </span>
          </div>
          <button type="button" className="drawer__close" onClick={onClose} autoFocus>
            Close
          </button>
        </header>

        <div className="drawer__body">
          <p className="u-micro" style={{ lineHeight: 1.6 }}>
            Question: {str(row.candidate.input?.question, '(not recorded)')}
          </p>

          <article className="ev">
            <header className="ev__head">
              <span className="ev__kind">answers</span>
              <span className="u-micro">both versions, as executed</span>
            </header>
            <div className="ev__body">
              <div className="answers">
                <div className="answer answer--baseline">
                  <div className="answer__head">
                    <span className="u-label">Baseline</span>
                    <span className="u-device">
                      {row.baselineStatus} · {formatScore(baselineLatency / 1000)}s
                    </span>
                  </div>
                  <p className="answer__text">{baselineAnswer || '(no answer recorded)'}</p>
                </div>
                <div className="answer answer--candidate">
                  <div className="answer__head">
                    <span className="u-label">Candidate</span>
                    <span className="u-device">
                      {row.candidateStatus} · {formatScore(candidateLatency / 1000)}s
                    </span>
                  </div>
                  <p className="answer__text">{candidateAnswer || '(no answer recorded)'}</p>
                </div>
              </div>
            </div>
          </article>

          <p className="u-micro">
            {ordered.length} evidence row(s) recorded for this case ({baseline.length} baseline,{' '}
            {candidate.length} candidate). The run records no per-case score, so none is shown here.
          </p>

          {ordered.map((item) => (
            <EvidenceRow key={item.id} item={item} />
          ))}

          {ordered.length === 0 && (
            <p className="u-micro">
              This case has no evidence rows yet. They are written as the executor finishes each
              version.
            </p>
          )}
        </div>
      </aside>
    </>
  )
}
