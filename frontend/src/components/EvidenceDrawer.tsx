import type { Evidence } from '../api/types'
import type { CaseOutcome } from '../fixtures/scenarios'
import { evidenceForCase } from '../fixtures/findings'
import { formatScore, formatSignedScore } from '../lib/format'

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
      <p className="u-micro">System: {str(payload.system)}</p>
      <div>
        <p className="ev__label">Retrieved passages ({retrieved.length})</p>
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
            <span className="u-label">Baseline</span>
            <span className="u-device">{formatScore(outcome.baselineVerdict.total)}</span>
          </div>
          <p className="answer__text">
            <RichText text={str(payload.baseline_text)} />
          </p>
        </div>
        <div className="answer answer--candidate">
          <div className="answer__head">
            <span className="u-label">Candidate</span>
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
          <p className="ev__label">Baseline — {baseline.length} citation(s)</p>
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
          <p className="ev__label">Candidate — {candidate.length} citation(s)</p>
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
                <span>no citation supplied</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="u-micro">
        At least {required} citation(s) required by the case definition.
      </p>
    </>
  )
}

function ScreenshotEvidence({ payload }: { payload: Record<string, unknown> }): React.JSX.Element {
  return (
    <>
      <div className="shots">
        <div className="shot">
          <span className="shot__tag">Baseline capture</span>
          <span className="shot__ref">{str(payload.baseline_ref)}</span>
          <span className="u-micro">not captured in this build</span>
        </div>
        <div className="shot">
          <span className="shot__tag">Candidate capture</span>
          <span className="shot__ref">{str(payload.candidate_ref)}</span>
          <span className="u-micro">not captured in this build</span>
        </div>
      </div>
      <p className="u-micro">
        {str(payload.caption)} — no browser capture ran for this worktree, so the frame above is a
        placeholder rather than a rendered answer.
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
            <span className="u-label">{str(check.label)}</span>
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
        Weighted total: baseline {formatScore(outcome.baselineVerdict.total)} → candidate{' '}
        {formatScore(outcome.candidateVerdict.total)}.
      </p>
    </div>
  )
}

function RationaleEvidence({ payload }: { payload: Record<string, unknown> }): React.JSX.Element {
  return (
    <>
      <div className="rationale">
        <div>
          <span className="ev__label">Baseline</span>
          <p>{str(payload.baseline)}</p>
        </div>
        <div>
          <span className="ev__label">Candidate</span>
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
        <EvidenceShell kind="prompt" label={label}>
          <PromptEvidence payload={payload} />
        </EvidenceShell>
      ) : (
        <EvidenceShell kind="rationale" label="evaluator">
          <RationaleEvidence payload={payload} />
        </EvidenceShell>
      )
    case 'trace':
      return (
        <EvidenceShell kind="answers + scored points" label="evaluator">
          <AnswerEvidence payload={payload} outcome={outcome} />
        </EvidenceShell>
      )
    case 'citation':
      return (
        <EvidenceShell kind="citations" label="deterministic check">
          <CitationEvidence payload={payload} />
        </EvidenceShell>
      )
    case 'screenshot':
      return (
        <EvidenceShell kind="screenshot (placeholder)" label="capture">
          <ScreenshotEvidence payload={payload} />
        </EvidenceShell>
      )
    case 'log':
      return (
        <EvidenceShell kind="log" label="executor">
          <LogEvidence payload={payload} />
        </EvidenceShell>
      )
    case 'metric':
      return (
        <EvidenceShell kind="checks" label="deterministic">
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
        aria-label="Close the evidence packet"
        onClick={onClose}
      />
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`Evidence packet for case ${outcome.spec.n}`}
      >
        <header className="drawer__head">
          <div className="drawer__title">
            <span className="u-micro">
              Case {String(outcome.spec.n).padStart(2, '0')} · {outcome.spec.category} · difficulty{' '}
              {outcome.spec.difficulty.toFixed(2)}
            </span>
            <h2 className="drawer__case-title">{outcome.spec.title}</h2>
            <span className="u-device">
              {outcome.spec.source} · baseline {formatScore(outcome.baselineVerdict.total)} →
              candidate {formatScore(outcome.candidateVerdict.total)} (
              {formatSignedScore(outcome.delta)})
            </span>
          </div>
          <button type="button" className="drawer__close" onClick={onClose} autoFocus>
            Close
          </button>
        </header>

        <div className="drawer__body">
          <p className="u-micro" style={{ lineHeight: 1.6 }}>
            Why this case exists: {outcome.spec.rationale}
          </p>
          {items.map((evidence) => (
            <EvidenceItem key={evidence.id} evidence={evidence} outcome={outcome} />
          ))}
        </div>
      </aside>
    </>
  )
}
