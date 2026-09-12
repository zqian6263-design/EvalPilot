import type { Evidence } from '../api/types'
import type { CaseOutcome } from '../fixtures/scenarios'
import { evidenceForCase } from '../fixtures/findings'
import { formatScore, formatSignedScore } from '../lib/format'
import { caseCategoryLabel, checkLabel } from '../i18n/labels'

interface Props {
  outcome: CaseOutcome
  onClose: () => void
}

const str = (value: unknown, fallback = ''): string => (typeof value === 'string' ? value : fallback)
const num = (value: unknown, fallback = 0): number => (typeof value === 'number' ? value : fallback)
const list = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : [])
const obj = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}

/** `**bold**` only. The fixture answers use no other inline markup. */
function RichText({ text }: { text: string }): React.JSX.Element {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith('**') && part.endsWith('**') ? (
          <strong key={index}>{part.slice(2, -2)}</strong>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  )
}

function EvidenceShell({
  kind,
  label,
  children,
}: {
  kind: string
  label: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <article className="ev">
      <header className="ev__head">
        <span className="ev__kind">{kind}</span>
        <span className="u-micro">{label}</span>
      </header>
      <div className="ev__body">{children}</div>
    </article>
  )
}

function PromptEvidence({ payload }: { payload: Record<string, unknown> }): React.JSX.Element {
  const retrieved = list<Record<string, unknown>>(payload.retrieved)
  return (
    <>
      <p className="prompt">{str(payload.question)}</p>
      <p className="u-micro">系统提示：{str(payload.system)}</p>
      <div>
        <p className="ev__label">检索到的段落（{retrieved.length}）</p>
        <ul className="citation-list" style={{ marginTop: 'var(--s1)' }}>
          {retrieved.map((passage, index) => (
            <li key={index} className="citation">
              <span className="citation__tick tabular">{num(passage.score).toFixed(2)}</span>
              <span>
                {str(passage.doc)} → {str(passage.section)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}

function AnswerEvidence({
  payload,
  outcome,
}: {
  payload: Record<string, unknown>
  outcome: CaseOutcome
}): React.JSX.Element {
  const points = list<Record<string, unknown>>(payload.points)
  return (
    <>
      {points.length > 0 && (
        <div className="points">
          {points.map((point, index) => (
            <div className="point" key={index}>
              <span>{str(point.point)}</span>
              <span
                className={`point__mark point__mark--${str(point.baseline) === 'stated' ? 'stated' : 'missing'}`}
              >
                {str(point.baseline)}
              </span>
              <span
                className={`point__mark point__mark--${str(point.candidate) === 'stated' ? 'stated' : 'missing'}`}
              >
                {str(point.candidate)}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="answers">
        <div className="answer answer--baseline">
          <div className="answer__head">
            <span className="u-label">基线版本</span>
            <span className="u-device">{formatScore(outcome.baselineVerdict.total)}</span>
          </div>
          <p className="answer__text">
            <RichText text={str(payload.baseline_text)} />
          </p>
        </div>
        <div className="answer answer--candidate">
          <div className="answer__head">
            <span className="u-label">候选版本</span>
            <span className="u-device">{formatScore(outcome.candidateVerdict.total)}</span>
          </div>
          <p className="answer__text">
            <RichText text={str(payload.candidate_text)} />
          </p>
        </div>
      </div>
    </>
  )
}

function CitationEvidence({ payload }: { payload: Record<string, unknown> }): React.JSX.Element {
  const baseline = list<Record<string, unknown>>(payload.baseline)
  const candidate = list<Record<string, unknown>>(payload.candidate)
  const required = num(payload.required_min)
  return (
    <>
      <div className="citations">
        <div>
          <p className="ev__label">基线版本 — {baseline.length} 条引用</p>
          <ul className="citation-list">
            {baseline.map((citation, index) => (
              <li key={index} className="citation">
                <span className="citation__tick" aria-hidden="true">
                  ✓
                </span>
                <span>{str(citation.uri)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="ev__label">候选版本 — {candidate.length} 条引用</p>
          <ul className="citation-list">
            {candidate.map((citation, index) => (
              <li key={index} className="citation">
                <span className="citation__tick" aria-hidden="true">
                  ✓
                </span>
                <span>{str(citation.uri)}</span>
              </li>
            ))}
            {Array.from({ length: Math.max(0, required - candidate.length) }).map((_, index) => (
              <li key={`gap-${index}`} className="citation citation--absent">
                <span className="citation__tick" aria-hidden="true">
                  —
                </span>
                <span>未提供引用</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="u-micro">
        该场景定义要求至少 {required} 条引用。
      </p>
    </>
  )
}

function ScreenshotEvidence({ payload }: { payload: Record<string, unknown> }): React.JSX.Element {
  return (
    <>
      <div className="shots">
        <div className="shot">
          <span className="shot__tag">基线版本截图</span>
          <span className="shot__ref">{str(payload.baseline_ref)}</span>
          <span className="u-micro">本次构建未采集</span>
        </div>
        <div className="shot">
          <span className="shot__tag">候选版本截图</span>
          <span className="shot__ref">{str(payload.candidate_ref)}</span>
          <span className="u-micro">本次构建未采集</span>
        </div>
      </div>
      <p className="u-micro">
        {str(payload.caption)} —— 本工作树中没有运行浏览器截图，因此上方画面是占位符，而非真实渲染的回答。
      </p>
    </>
  )
}

function LogEvidence({ payload }: { payload: Record<string, unknown> }): React.JSX.Element {
  const lines = list<string>(payload.lines)
  return (
    <pre className="log" tabIndex={0}>
      {lines.join('\n')}
    </pre>
  )
}

function CheckEvidence({
  payload,
  outcome,
}: {
  payload: Record<string, unknown>
  outcome: CaseOutcome
}): React.JSX.Element {
  const checks = list<Record<string, unknown>>(payload.checks)
  return (
    <div className="scored">
      {checks.map((check, index) => {
        const baseline = num(check.baseline)
        const candidate = num(check.candidate)
        const delta = candidate - baseline
        return (
          <div className="scored__row" key={index}>
            <span className="u-label">{checkLabel(str(check.id), str(check.label))}</span>
            <div>
              <p className="check__detail">{str(check.detail)}</p>
            </div>
            <span className={`scored__value ${delta < 0 ? 'record__delta--down' : delta > 0 ? 'record__delta--up' : ''}`}>
              {formatScore(baseline)} → {formatScore(candidate)}
              <br />
              <span className="u-micro">{formatSignedScore(delta)}</span>
            </span>
          </div>
        )
      })}
      <p className="u-micro">
        加权总分：基线 {formatScore(outcome.baselineVerdict.total)} → 候选{' '}
        {formatScore(outcome.candidateVerdict.total)}。
      </p>
    </div>
  )
}

function RationaleEvidence({ payload }: { payload: Record<string, unknown> }): React.JSX.Element {
  return (
    <>
      <div className="rationale">
        <div>
          <span className="ev__label">基线版本</span>
          <p>{str(payload.baseline)}</p>
        </div>
        <div>
          <span className="ev__label">候选版本</span>
          <p>{str(payload.candidate)}</p>
        </div>
      </div>
      <p className="rationale__note">{str(payload.source)}</p>
    </>
  )
}

function EvidenceItem({
  evidence,
  outcome,
}: {
  evidence: Evidence
  outcome: CaseOutcome
}): React.JSX.Element {
  const payload = obj(evidence.payload)
  const label = str(payload.label, evidence.kind)

  switch (evidence.kind) {
    case 'text':
      return payload.question !== undefined ? (
        <EvidenceShell kind="提问" label="输入">
          <PromptEvidence payload={payload} />
        </EvidenceShell>
      ) : (
        <EvidenceShell kind="评分理由" label="评估器">
          <RationaleEvidence payload={payload} />
        </EvidenceShell>
      )
    case 'trace':
      return (
        <EvidenceShell kind="回答与得分要点" label="评估器">
          <AnswerEvidence payload={payload} outcome={outcome} />
        </EvidenceShell>
      )
    case 'citation':
      return (
        <EvidenceShell kind="引用" label="确定性检查">
          <CitationEvidence payload={payload} />
        </EvidenceShell>
      )
    case 'screenshot':
      return (
        <EvidenceShell kind="截图（占位符）" label="采集">
          <ScreenshotEvidence payload={payload} />
        </EvidenceShell>
      )
    case 'log':
      return (
        <EvidenceShell kind="日志" label="执行器">
          <LogEvidence payload={payload} />
        </EvidenceShell>
      )
    case 'metric':
      return (
        <EvidenceShell kind="检查项" label="确定性">
          <CheckEvidence payload={payload} outcome={outcome} />
        </EvidenceShell>
      )
    default:
      return (
        <EvidenceShell kind={evidence.kind} label={label}>
          <pre className="log">{JSON.stringify(payload, null, 2)}</pre>
        </EvidenceShell>
      )
  }
}

/**
 * The evidence packet for one case.
 *
 * `docs/SPEC.md` requires that every finding link to the exact input, output,
 * tool trace and evaluator rationale. This drawer is where that requirement
 * becomes visible: the prompt, both answers, the citations each returned, the
 * execution log, the deterministic checks, and the judge's reasoning — in the
 * order the evaluator used them.
 */
export function EvidenceDrawer({ outcome, onClose }: Props): React.JSX.Element {
  const items = evidenceForCase(outcome.caseId)

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
        aria-label={`场景 ${outcome.spec.n} 的证据包`}
      >
        <header className="drawer__head">
          <div className="drawer__title">
            <span className="u-micro">
              场景 {String(outcome.spec.n).padStart(2, '0')} · {caseCategoryLabel(outcome.spec.category)} · 难度{' '}
              {outcome.spec.difficulty.toFixed(2)}
            </span>
            <h2 className="drawer__case-title">{outcome.spec.title}</h2>
            <span className="u-device">
              {outcome.spec.source} · 基线 {formatScore(outcome.baselineVerdict.total)} →
              候选 {formatScore(outcome.candidateVerdict.total)}（
              {formatSignedScore(outcome.delta)}）
            </span>
          </div>
          <button type="button" className="drawer__close" onClick={onClose} autoFocus>
            关闭
          </button>
        </header>

        <div className="drawer__body">
          <p className="u-micro" style={{ lineHeight: 1.6 }}>
            该场景存在的原因：{outcome.spec.rationale}
          </p>
          {items.map((evidence) => (
            <EvidenceItem key={evidence.id} evidence={evidence} outcome={outcome} />
          ))}
        </div>
      </aside>
    </>
  )
}
