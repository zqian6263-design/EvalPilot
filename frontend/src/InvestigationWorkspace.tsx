import { useEffect, useRef, useState } from 'react'
import {
  breakEvenIntervention,
  buildStepTree,
  citedEvidenceIds,
  groupCounterfactuals,
  isInvestigationTerminal,
  reportUrl,
  riskSteps,
  rootCauseEvidenceIds,
  type CounterfactualExperiment,
  type InvestigationBundle,
  type InvestigationStep,
  type InvestigationTransport,
  type InvestigationTransportInfo,
  type RiskLevel,
} from './api/investigation'
import { MOCK_RUN_ID } from './mockInvestigation'
import { HttpInvestigationTransport } from './httpInvestigationTransport'
import { MockInvestigationTransport } from './mockInvestigationTransport'
import { defaultObjective, runInvestigation, type InvestigationRun } from './runInvestigation'
import { StepRow, visibleRows } from './StepRow'
import {
  PROVENANCE,
  counterfactualVerdictLabel,
  decisionVerdictLabel,
  investigationStatusLabel,
  riskLevelLabel,
  stepStatusLabel,
} from './i18n/labels'
// The workspace owns its own stylesheet and pulls it in itself, rather than
// asking `styles/index.css` to import it. That is what "self-contained" means
// here: wiring the component into App.tsx is one import and no stylesheet edit,
// so the integration step cannot half-land with the surface rendering unstyled.
// The file resolves every colour and size to the tokens `index.css` already
// loads, so it needs nothing from the console's own sheets to look right.
//
// The path is root-absolute, not `./styles/…`. Vite's CSS plugin resolves this
// project's relative stylesheet specifiers against the *project root* rather
// than the importing file, so `./styles/investigation.css` from `src/` looks in
// `./styles/` at the root — where nothing is — and the import is dropped with
// no error and no warning. The build still "succeeds" and the surface renders
// unstyled, which is exactly the failure mode that is easy to ship by accident.
// `/src/styles/…` is resolved from the same root, unambiguously.
import '/src/styles/investigation.css'

/**
 * Optional context about the evaluation run this investigation is opened
 * against. Every field is optional: the workspace is usable with nothing but a
 * transport, and integration is a separate step, so it must not require App.tsx
 * to have changed first.
 *
 * The optional members are all typed `| undefined` as well as `?` because the
 * project builds with `exactOptionalPropertyTypes`. Without the explicit
 * `undefined`, the most natural call site — `<InvestigationWorkspace
 * runId={live?.run.id} />`, where `live` may be null — is a type error rather
 * than an omitted prop, and the integrator's first instinct is to write
 * `runId={live!.run.id}` or a `?? undefined` shim to silence it.
 */
export interface InvestigationWorkspaceProps {
  /**
   * The evaluation run to investigate. When omitted, the workspace resolves one
   * through `resolveRunId` or falls back to the transport's own demo run — which
   * is what makes the offline mock demonstrable with no props at all.
   */
  runId?: string | undefined
  /** Called once when the workspace needs a run id and was not given one. */
  resolveRunId?: (() => Promise<string | null>) | undefined
  /** Versions and case count, for the prefilled objective and the plate. */
  runContext?:
    | {
        baselineVersion?: string | undefined
        candidateVersion?: string | undefined
        matchedCases?: number | undefined
      }
    | undefined
  /** Free text the objective field starts from, overriding the generated default. */
  defaultObjectiveText?: string | undefined
  /** Called when the viewer presses start, for a host that wants to record it. */
  onStarted?: ((objective: string, runId: string) => void) | undefined
  /** Injected in tests; the workspace builds its own when omitted. */
  transport?: InvestigationTransport | undefined
  /** Start as soon as a run id is available, for an automated demo deep link. */
  autoStart?: boolean | undefined
}

type Source = 'http' | 'mock'

/**
 * Pick a transport without the host having to.
 *
 * A probe with a short timeout, then a decision: reachable means the real
 * service, unreachable means the bundled mock. The workspace states which one
 * it used in the plate beneath the objective field, because a reviewer must be
 * able to tell at a glance whether an investigation happened or was replayed.
 *
 * Both transports are imported statically, alongside the mock dataset itself —
 * so there is nothing a dynamic import would defer, and the console's own
 * `App.tsx` imports its two transports the same way.
 */
async function pickTransport(timeoutMs = 1200): Promise<InvestigationTransport> {
  const http = new HttpInvestigationTransport()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    // The incident library is the cheapest real endpoint the V2 contract
    // exposes; a healthy service answers it, and anything else is offline.
    await http.listIncidents(undefined, undefined, { signal: controller.signal })
    return http
  } catch {
    return new MockInvestigationTransport()
  } finally {
    clearTimeout(timer)
  }
}

function riskWord(level: RiskLevel): string {
  return riskLevelLabel(level)
}

/**
 * The autonomous-investigation workspace.
 *
 * One screen, read top to bottom in the order the investigation runs: the
 * objective that was given, the decision it reached, then the record that
 * justifies it — the tree of hypotheses, probes and replays, the incidents it
 * recalled, the counterfactual scores, and the evidence every claim cites.
 *
 * What it deliberately does not do: show reasoning. The contract forbids
 * exposing private chain-of-thought, and the surface reflects that. Every step
 * is a *structured action* — a named tool, its arguments, the artefact it
 * wrote — and every conclusion is a numbered statement with evidence ids
 * attached. A reviewer can audit the record without ever being shown a
 * transcript of the model thinking.
 *
 * The decision card is above the evidence, not below it, because the decision
 * is what a release manager opens this page for; the evidence is what they
 * check it against.
 */
export function InvestigationWorkspace({
  runId,
  resolveRunId,
  runContext,
  defaultObjectiveText,
  onStarted,
  transport: injected,
  autoStart,
}: InvestigationWorkspaceProps): React.JSX.Element {
  const [transport, setTransport] = useState<InvestigationTransport | null>(injected ?? null)
  const [info, setInfo] = useState<InvestigationTransportInfo | null>(
    injected ? injected.describe() : null,
  )
  const [resolvedRunId, setResolvedRunId] = useState<string>(runId ?? '')
  const [objective, setObjective] = useState<string>(
    defaultObjectiveText ?? defaultObjective(runContext ?? {}),
  )
  const [run, setRun] = useState<InvestigationRun | null>(null)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set())
  const abortRef = useRef<AbortController | null>(null)
  const autoStartedRef = useRef(false)

  useEffect(() => () => abortRef.current?.abort(), [])

  // The host may resolve the live run after this component first mounts.
  // Adopt that id instead of keeping the empty initial state forever.
  useEffect(() => {
    if (runId) setResolvedRunId(runId)
  }, [runId])

  useEffect(() => {
    if (injected) return
    let cancelled = false
    void pickTransport().then((chosen) => {
      if (cancelled) return
      setTransport(chosen)
      setInfo(chosen.describe())
    })
    return () => {
      cancelled = true
    }
  }, [injected])

  const source: Source = info?.live ? 'http' : 'mock'
  const bundle = run?.bundle ?? null

  const start = async (): Promise<void> => {
    if (!transport || starting) return
    setStarting(true)
    setStartError(null)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      let target = resolvedRunId
      if (!target && resolveRunId) {
        target = (await resolveRunId()) ?? ''
        if (target) setResolvedRunId(target)
      }
      if (!target && source === 'mock') {
        // Nothing was supplied and nothing could be resolved, but the mock has
        // its own demo run — the one its dataset is written against. Using that
        // id keeps the workspace demonstrable with no props at all; it is never
        // used for a live transport, where inventing a run id would open an
        // investigation against a run that does not exist.
        target = MOCK_RUN_ID
        setResolvedRunId(target)
      }
      if (!target) {
        setStartError('没有可调查的评估运行。请先打开一次运行，或向工作区传入 runId。')
        return
      }

      onStarted?.(objective, target)
      const result = await runInvestigation({
        transport,
        objective,
        runId: target,
        onUpdate: (update) => setRun(update),
        signal: controller.signal,
      })
      setRun(result)
    } catch (cause) {
      setStartError(cause instanceof Error ? cause.message : '调查无法启动')
    } finally {
      setStarting(false)
    }
  }


  useEffect(() => {
    if (!autoStart || !resolvedRunId || autoStartedRef.current) return
    autoStartedRef.current = true
    void start()
  }, [autoStart, resolvedRunId, start])

  const investigation = run?.investigation ?? null
  const status = investigation?.status ?? 'queued'
  const tree = bundle ? buildStepTree(bundle.steps) : []
  const rows = visibleRows(tree, collapsed)
  const selectedStep =
    bundle && selectedStepId
      ? (bundle.steps.find((step) => step.id === selectedStepId) ?? null)
      : null

  const toggleCollapse = (stepId: string): void => {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(stepId)) next.delete(stepId)
      else next.add(stepId)
      return next
    })
  }

  return (
    <div className="inv" aria-label="自主调查">
      {/* ------------------------------------------------------------ intake */}
      <section className="inv__intake" aria-label="调查目标">
        <div className="inv__plate">
          <span className="u-micro">自主发布调查</span>
          <h1 className="inv__title">发布调查</h1>
        </div>

        <div className="inv__field">
          <label className="u-label" htmlFor="inv-objective">
            发布目标
          </label>
          <textarea
            id="inv-objective"
            className="inv__objective"
            rows={3}
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            disabled={starting}
          />
        </div>

        <div className="inv__controls">
          <button
            type="button"
            className="ctl ctl--primary"
            onClick={() => void start()}
            disabled={starting || objective.trim().length === 0}
          >
            {starting ? '调查中…' : '启动自主调查'}
          </button>

          <div className="inv__context">
            <span className="u-micro">运行</span>
            <span className="u-device">
              {resolvedRunId ? resolvedRunId.slice(0, 8) : '启动时解析'}
            </span>
            {runContext?.baselineVersion && (
              <>
                <span className="u-micro">基线版本</span>
                <span className="u-device">{runContext.baselineVersion}</span>
              </>
            )}
            {runContext?.candidateVersion && (
              <>
                <span className="u-micro">候选版本</span>
                <span className="u-device">{runContext.candidateVersion}</span>
              </>
            )}
          </div>
        </div>

        {info && (
          <div className={`inv__source inv__source--${source}`}>
            <span className="inv__lamp" aria-hidden="true" />
            <span className="u-micro">{info.label}</span>
            <span className="inv__source-note">
              {source === 'mock'
                ? PROVENANCE.mockInvestigation
                : PROVENANCE.mockInvestigationLive(info.baseUrl ?? '/api')}
            </span>
          </div>
        )}

        {startError && (
          <p className="inv__error" role="alert">
            {startError}
          </p>
        )}
      </section>

      {investigation && (
        <section className="inv__statusbar" aria-label="调查状态">
          <span className="u-micro">调查 ID</span>
          <span className="u-device">{investigation.id.slice(0, 8)}</span>
          <span className="u-micro">状态</span>
          <span className={`inv__status inv__status--${investigation.status}`}>
            {investigationStatusLabel(investigation.status)}
          </span>
          <span className="u-micro">风险</span>
          <span className={`inv__risk inv__risk--${investigation.risk_level}`}>
            {riskWord(investigation.risk_level)}
          </span>
          {run?.adopted && <span className="u-micro">已接管 —— 此前已启动</span>}
          {run && !run.settled && !isInvestigationTerminal(status) && (
            <span className="u-micro">仍在运行 —— 显示目前已记录的内容</span>
          )}
          {investigation.summary && <span className="inv__summary">{investigation.summary}</span>}
        </section>
      )}

      {bundle && (
        <div className="inv__body">
          <div className="inv__col">
            {/* ------------------------------------------------------- tree */}
            <section className="panel" aria-label="调查时间线">
              <div className="panel__title">
                <span className="u-label">时间线</span>
                <span className="u-micro">
                  {bundle.steps.length} 个步骤 ·{' '}
                  {riskSteps(bundle.steps).length} 条风险假设
                </span>
              </div>
              <ol className="inv__tree">
                {rows.map((node) => (
                  <StepRow
                    key={node.step.id}
                    node={node}
                    selectedStepId={selectedStepId}
                    onSelectStep={setSelectedStepId}
                    collapsed={collapsed}
                    onToggleCollapse={toggleCollapse}
                  />
                ))}
              </ol>
              {bundle.steps.length === 0 && (
                <p className="u-micro inv__pad">
                  调查尚未记录任何步骤。随着它开始规划，步骤会显示在这里。
                </p>
              )}
            </section>

            {selectedStep && <StepDetail step={selectedStep} />}

            {/* ------------------------------------------------------- memory */}
            <MemoryPanel bundle={bundle} onSelectStep={setSelectedStepId} />
          </div>

          <div className="inv__col inv__col--side">
            {/* --------------------------------------------------- decision */}
            <DecisionCard bundle={bundle} />

            {/* -------------------------------------------- counterfactuals */}
            <section className="panel" aria-label="反事实根因">
              <div className="panel__title">
                <span className="u-label">反事实重放</span>
                <span className="u-micro">
                  {bundle.counterfactuals.length} 次实验 ·{' '}
                  {rootCauseEvidenceIds(bundle.counterfactuals).length} 条证据关联
                </span>
              </div>
              <div className="cf">
                {groupCounterfactuals(bundle.counterfactuals).map((group) => {
                  const best = breakEvenIntervention(group.experiments)
                  return (
                    <article className="cf__group" key={group.scenario_id}>
                      <header className="cf__head">
                        <h3 className="cf__scenario u-device">{group.scenario_id}</h3>
                        {best?.intervention ? (
                          <span className="cf__break-even">
                            <span className="u-micro">可恢复至</span>
                            <span className="cf__break-even-value u-device">
                              {best.restores.toFixed(2)}
                            </span>
                            <span className="cf__break-even-note">
                              {best.intervention} · 领先次优干预 {(best.marginPoints / 100).toFixed(2)}
                            </span>
                          </span>
                        ) : (
                          <span className="u-micro">没有单一干预起主导作用</span>
                        )}
                      </header>

                      {group.experiments.map((experiment) => (
                        <ExperimentRow key={experiment.id} experiment={experiment} />
                      ))}

                      <details className="cf__why">
                        <summary className="u-micro">
                          判断理由（{group.experiments.length}）
                        </summary>
                        {group.experiments.map((experiment) => (
                          <p className="cf__rationale" key={`${experiment.id}-why`}>
                            <span className={`cf__verdict cf__verdict--${experiment.verdict}`}>
                              {counterfactualVerdictLabel(experiment.verdict)}
                            </span>{' '}
                            {experiment.rationale}
                          </p>
                        ))}
                      </details>                    </article>
                  )
                })}
                {bundle.counterfactuals.length === 0 && (
                  <p className="u-micro inv__pad">
                    尚未运行任何重放。每次重放会用单项设置变更重跑一个场景，并与候选版本自身的原始得分比较差值。
                  </p>
                )}
              </div>
            </section>

            {/* ---------------------------------------------------- evidence */}
            <EvidencePanel bundle={bundle} />
          </div>
        </div>
      )}

      {bundle && (
        <ReportBar transport={transport} info={info} investigationId={investigation?.id ?? ''} />
      )}
    </div>
  )
}

// ------------------------------------------------------------ sub-panels ----

/** The sidecar for one step: its detail, its structured action, its evidence. */
function StepDetail({ step }: { step: InvestigationStep }): React.JSX.Element {
  const data = step.data
  const tool = typeof data.tool === 'string' ? data.tool : null
  const artifact = typeof data.artifact === 'string' ? data.artifact : null
  const args = data.arguments && typeof data.arguments === 'object' ? data.arguments : null
  const runs = typeof data.runs === 'number' ? data.runs : null
  const failures = typeof data.failures === 'number' ? data.failures : null

  return (
    <section className="panel" aria-label="步骤详情">
      <div className="panel__title">
        <span className="u-label">步骤 {String(step.sequence).padStart(2, '0')}</span>
        <span className={`inv__status inv__status--${step.status}`}>{stepStatusLabel(step.status)}</span>
      </div>
      <div className="inv__pad stack" style={{ gap: 'var(--s3)' }}>
        <h3 className="step__detail-title">{step.title}</h3>
        <p className="step__detail-body">{step.detail}</p>

        {tool && (
          <div className="action">
            <span className="action__tag">动作</span>
            <div className="action__body">
              <span className="u-label">{tool}</span>
              {args && (
                <dl className="action__args">
                  {Object.entries(args).map(([key, value]) => (
                    <div key={key} style={{ display: 'contents' }}>
                      <dt className="u-micro">{key}</dt>
                      <dd className="u-device">{JSON.stringify(value)}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {artifact && <span className="action__artifact u-device">{artifact}</span>}
              {(runs !== null || failures !== null) && (
                <span className="u-micro">
                  {runs ?? 0} 次运行 · {failures ?? 0} 次失败
                </span>
              )}
            </div>
          </div>
        )}

        {step.evidence_ids.length > 0 && (
          <div className="step__evidence">
            <span className="u-micro">{step.evidence_ids.length} 条证据关联</span>
            <ul className="evlinks">
              {step.evidence_ids.map((id) => (
                <li className="evlink u-device" key={id}>
                  {id}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}

function ExperimentRow({
  experiment,
}: {
  experiment: CounterfactualExperiment
}): React.JSX.Element {
  const improved = experiment.delta > 0
  const flat = Math.abs(experiment.delta) < 1e-9
  const extent = Math.min(Math.abs(experiment.delta) / 0.5, 1) * 50

  return (
    <div className="cf__row" data-verdict={experiment.verdict}>
      <div className="cf__row-head">
        <span className="cf__intervention u-device">{experiment.intervention}</span>
        <span className={`cf__verdict cf__verdict--${experiment.verdict}`}>
          {counterfactualVerdictLabel(experiment.verdict)}
        </span>
      </div>

      <div className="cf__scores">
        <div className="cf__score">
          <span className="u-micro">重放前</span>
          <span className="cf__score-value u-device">{experiment.original_score.toFixed(2)}</span>
        </div>
        <div className="cf__score">
          <span className="u-micro">重放后</span>
          <span
            className={`cf__score-value u-device${improved ? ' cf__score-value--up' : flat ? '' : ' cf__score-value--down'}`}
          >
            {experiment.counterfactual_score.toFixed(2)}
          </span>
        </div>
        <div className="cf__meter-wrap">
          <div className="meter" role="presentation">
            {improved && (
              <div className="meter__fill meter__fill--gain" style={{ width: `${extent}%` }} />
            )}
            {!improved && !flat && (
              <div className="meter__fill meter__fill--loss" style={{ width: `${extent}%` }} />
            )}
            <div className="meter__zero" />
          </div>
          <span
            className={`cf__delta u-device${improved ? ' cf__delta--up' : flat ? ' cf__delta--flat' : ' cf__delta--down'}`}
          >
            {improved ? '+' : experiment.delta < 0 ? '−' : ''}
            {Math.abs(experiment.delta).toFixed(2)}
          </span>
          <span className="u-micro">置信度 {experiment.confidence.toFixed(2)}</span>
        </div>
      </div>

      {experiment.evidence_ids.length > 0 && (
        <ul className="evlinks evlinks--tight">
          {experiment.evidence_ids.map((id) => (
            <li className="evlink u-device" key={id}>
              {id}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function MemoryPanel({
  bundle,
  onSelectStep,
}: {
  bundle: InvestigationBundle
  onSelectStep: (stepId: string) => void
}): React.JSX.Element {
  const memoryStep = bundle.steps.find((step) => step.kind === 'memory')

  return (
    <section className="panel" aria-label="召回的历史事故">
      <div className="panel__title">
        <span className="u-label">召回的历史事故</span>
        <span className="u-micro">{bundle.memory_matches.length} 条匹配</span>
      </div>
      <div className="memory">
        {bundle.memory_matches.map((match) => (
          <article className="memory__item" key={match.incident_id}>
            <header className="memory__head">
              <span className="memory__id u-device">{match.incident_id}</span>
              <div className="memory__score">
                <span className="u-micro">相似度</span>
                <span className="memory__score-value u-device">{match.score.toFixed(2)}</span>
              </div>
            </header>
            <p className="memory__reason">{match.reason}</p>
            <div className="memory__terms">
              {match.matched_terms.map((term) => (
                <span className="chip chip--graphite" key={term}>
                  {term}
                </span>
              ))}
            </div>
          </article>
        ))}
        {bundle.memory_matches.length === 0 && (
          <p className="u-micro inv__pad">
            目前没有历史事故匹配到该故障形态。随着调查进行召回，匹配结果会显示在这里。
          </p>
        )}
        {memoryStep && (
          <button
            type="button"
            className="memory__step-link"
            onClick={() => onSelectStep(memoryStep.id)}
          >
            打开召回步骤（{String(memoryStep.sequence).padStart(2, '0')}）
          </button>
        )}
      </div>
    </section>
  )
}

function DecisionCard({ bundle }: { bundle: InvestigationBundle }): React.JSX.Element {
  const decision = bundle.decision
  if (!decision) {
    return (
      <section className="panel" aria-label="发布裁决">
        <div className="panel__title">
          <span className="u-label">发布裁决</span>
          <span className="u-micro">待定</span>
        </div>
        <p className="u-micro inv__pad">
          调查尚未得出结论。得出结论后此卡片才会出现 —— 只有支撑结论的重放全部完成，裁决才会被打印出来。
        </p>
      </section>
    )
  }

  const stampClass =
    decision.verdict === 'block'
      ? 'stamp'
      : decision.verdict === 'review'
        ? 'stamp stamp--better'
        : 'stamp stamp--clear'
  const stampWord =
    decision.verdict === 'block' ? '阻断' : decision.verdict === 'review' ? '复核' : '放行'

  return (
    <section className="panel" aria-label="发布裁决">
      <div className="panel__title">
        <span className="u-label">发布裁决</span>
        <span className={`inv__risk inv__risk--${decision.risk_level}`}>
          {riskWord(decision.risk_level)}
        </span>
      </div>

      <div className="inv__pad stack" style={{ gap: 'var(--s3)' }}>
        <div className="decision__headline">
          <h2 className={`decision__word decision__word--${decision.verdict}`}>
            {decisionVerdictLabel(decision.verdict)}
          </h2>
          <div className={stampClass} aria-hidden="true">
            <div className="stamp__word">{stampWord}</div>
            <div className="stamp__sub">置信度 {decision.confidence.toFixed(2)}</div>
          </div>
        </div>

        <p className="decision__summary">{decision.summary}</p>

        <div>
          <span className="u-micro">建议操作</span>
          <ol className="decision__actions">
            {decision.recommended_actions.map((action) => (
              <li className="decision__action" key={action}>
                {action}
              </li>
            ))}
          </ol>
        </div>

        <div>
          <span className="u-micro">
            阻断性证据（{decision.blocking_findings.length}）
          </span>
          <ul className="evlinks">
            {decision.blocking_findings.map((id) => (
              <li className="evlink u-device" key={id}>
                {id}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

function EvidencePanel({ bundle }: { bundle: InvestigationBundle }): React.JSX.Element {
  const ids = citedEvidenceIds(bundle)
  const rootIds = new Set(rootCauseEvidenceIds(bundle.counterfactuals))

  return (
    <section className="panel" aria-label="证据">
      <div className="panel__title">
        <span className="u-label">证据</span>
        <span className="u-micro">
          引用 {ids.length} 条 · 支撑根因的 {rootIds.size} 条
        </span>
      </div>
      <div className="inv__pad">
        <ul className="evlinks evlinks--grid">
          {ids.map((id) => (
            <li
              className={`evlink u-device${rootIds.has(id) ? ' evlink--root' : ''}`}
              key={id}
            >
              {id}
            </li>
          ))}
        </ul>
        {ids.length === 0 && (
          <p className="u-micro">
            尚无任何结论引用证据。没有证据的发现不得声称找到根因。
          </p>
        )}
      </div>
    </section>
  )
}

function ReportBar({
  transport,
  info,
  investigationId,
}: {
  transport: InvestigationTransport | null
  info: InvestigationTransportInfo | null
  investigationId: string
}): React.JSX.Element {
  const [state, setState] = useState<'idle' | 'reading' | 'done' | 'error'>('idle')
  const [note, setNote] = useState<string | null>(null)
  const url = info && investigationId ? reportUrl(info, investigationId) : ''

  const download = async (): Promise<void> => {
    if (!transport || !investigationId) return
    setState('reading')
    setNote(null)
    try {
      const markdown = await transport.getReport(investigationId)
      const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = `investigation-${investigationId.slice(0, 8)}-report.md`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(objectUrl)
      setState('done')
      setNote(`已写入 ${markdown.split('\n').length} 行`)
    } catch (cause) {
      setState('error')
      setNote(cause instanceof Error ? cause.message : '报告无法读取')
    }
  }

  return (
    <div className="inv__report">
      <div className="stack" style={{ gap: 'var(--s1)' }}>
        <span className="u-micro">导出</span>
        <span className="stack" style={{ gap: 0 }}>
          <span className="u-label">Markdown 报告</span>
          <span className="inv__report-url u-device">
            {url || '无端点 —— 模拟报告在本地生成'}
          </span>
        </span>
      </div>
      <div className="row" style={{ gap: 'var(--s3)' }}>
        {note && <span className="u-micro">{note}</span>}
        <button
          type="button"
          className="ctl"
          onClick={() => void download()}
          disabled={!transport || !investigationId || state === 'reading'}
        >
          {state === 'reading' ? '读取中…' : '下载 report.md'}
        </button>
      </div>
    </div>
  )
}
