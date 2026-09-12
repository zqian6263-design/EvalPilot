import { useCallback, useEffect, useRef, useState } from 'react'
import { HttpTransport } from './api/httpTransport'
import { MockTransport } from './api/mockTransport'
import { buildLiveEvaluation, type LiveEvaluation } from './api/evaluation'
import { ensureRunStarted, readReport, resolveDemoContext, waitForRun } from './api/runLifecycle'
import type { Transport } from './api/transport'
import type { Run, RunStatus } from './api/types'
import { DemoEntry } from './components/DemoEntry'
import { Header } from './components/Header'
import {
  DEFAULT_SCENARIO_ID,
  SCENARIOS,
  type Scenario,
  type ScenarioId,
} from './fixtures/scenarios'
import { Console } from './views/Console'
import { FindingsView } from './views/Findings'
import { LiveConsole } from './views/LiveConsole'
import { LiveFindings } from './views/LiveFindings'
import { LiveReportView } from './views/LiveReport'
import { InvestigationWorkspace } from './InvestigationWorkspace'
import { MarketImpactPanel } from './features/market'
import { ReportView } from './views/Report'
import { PROVENANCE } from './i18n/labels'

export type View = 'console' | 'findings' | 'report' | 'investigation' | 'market'

/**
 * The view keys are also the URL fragments (`#report`, `#case=22`), so `id` is
 * never translated. `label` is what the tab prints.
 */
const VIEWS: ReadonlyArray<{ id: View; label: string }> = [
  { id: 'console', label: '运行控制台' },
  { id: 'findings', label: '评估发现' },
  { id: 'report', label: '评估报告' },
  { id: 'investigation', label: '自动调查' },
  { id: 'market', label: '市场价值' },
]

/**
 * Probe timeout for the backend. Long enough for a cold FastAPI start on a
 * developer machine, short enough that a judge never watches a dead spinner —
 * after which the console falls back to bundled fixtures and says so.
 */
const PROBE_TIMEOUT_MS = 1200

/**
 * How long the console follows a live run before showing the partial state.
 *
 * The 26-scenario run plus investigation can take several seconds; thirty
 * seconds leaves room for a cold start without presenting a hung page.
 */
const RUN_TIMEOUT_MS = 30_000

/**
 * The live run the console is showing, once one exists.
 *
 * `run` is the backend's own record; `evaluation` is the assembled view built
 * from `GET /runs/{id}` and its report. Both are kept so the header can name
 * the run even while its report is still being written.
 */
interface RuntimeStatus {
  mode: 'deterministic' | 'live'
  llm_configured: boolean
  model: string | null
  fallback_active: boolean
}

interface LiveState {
  run: Run
  status: RunStatus
  evaluation: LiveEvaluation | null
  reportGeneratedAt: string | null
  reportId: string | null
  settled: boolean
  /** Set when a step failed for a reason worth showing. */
  error: string | null
}

/** `#report`, `#findings`, `#console`, `#case=09`, `#scenario=improvement`. */
interface Route {
  view: View
  caseNumber: number | null
  scenarioId: ScenarioId
  /** `#console&demo` — probe the backend and open a run without a click. */
  autoDemo: boolean
}

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#/, '')
  const params = new URLSearchParams(hash)

  const view = VIEWS.find((item) => params.has(item.id))?.id ?? 'console'
  const rawCase = Number(params.get('case'))
  const caseNumber = Number.isInteger(rawCase) && rawCase > 0 ? rawCase : null
  const scenario =
    SCENARIOS.find((item) => item.id === params.get('scenario'))?.id ?? DEFAULT_SCENARIO_ID

  return { view, caseNumber, scenarioId: scenario, autoDemo: params.has('demo') }
}

function writeRoute(route: Partial<Route>): void {
  const next = { ...readRoute(), ...route }
  const params = new URLSearchParams()
  params.set(next.view, '')
  if (next.scenarioId !== DEFAULT_SCENARIO_ID) params.set('scenario', next.scenarioId)
  if (next.caseNumber !== null) params.set('case', String(next.caseNumber))
  if (next.autoDemo) params.set('demo', '')
  window.location.hash = params.toString()
}

/**
 * Deep links are a demo feature, not a nicety: a presenter moving between
 * slides wants `#report` and `#case=22` to be plain URLs they can put on a
 * slide, and a reviewer wants to send a colleague the exact case they mean.
 *
 * The console has two complete renderings of the same three views. When a
 * backend answered the probe and returned a run, the live views render that
 * run. Otherwise the fixture views render the bundled corpus and say so. The
 * choice is made once, from what the backend actually returned, and the
 * provenance bar states which one is on screen.
 */
export function App(): React.JSX.Element {
  const [route, setRoute] = useState<Route>(() => readRoute())
  const [transport, setTransport] = useState<Transport | null>(null)
  const [starting, setStarting] = useState(false)
  const [live, setLive] = useState<LiveState | null>(null)
  const [liveNote, setLiveNote] = useState<string | null>(null)
  const [autoDemoDone, setAutoDemoDone] = useState(false)
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    let cancelled = false
    void fetch('/api/runtime')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload: RuntimeStatus | null) => {
        if (!cancelled && payload) setRuntimeStatus(payload)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const onHashChange = (): void => setRoute(readRoute())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // A demo run in flight must not keep updating a console the viewer has
  // navigated away from; the controller is the switch that stops it.
  useEffect(() => () => abortRef.current?.abort(), [])

  const scenario = SCENARIOS.find((item) => item.id === route.scenarioId)!
  const selectedCaseId =
    route.caseNumber === null
      ? null
      : (scenario.outcomes.find((outcome) => outcome.spec.n === route.caseNumber)?.caseId ?? null)

  /**
   * One click: probe, resolve a demo context, start a run, follow it, show it.
   *
   * Each step is awaited in order, and any step that fails drops the console to
   * the fixture rendering with the reason kept in `liveNote`. The console never
   * half-renders a live run it could not read.
   */
  const startDemo = useCallback(async () => {
    setStarting(true)
    setLiveNote(null)
    const probe = new AbortController()
    const timer = setTimeout(() => probe.abort(), PROBE_TIMEOUT_MS)

    try {
      const http = new HttpTransport()
      await http.health()
      setTransport(http)

      const context = await resolveDemoContext(http)
      if (context === null) {
        // Healthy but not seedable: fixtures are the only honest source here.
        setLiveNote(PROVENANCE.backendUnseedable)
        setLive(null)
        return
      }

      const controller = new AbortController()
      abortRef.current = controller

      const { run, note } = await ensureRunStarted({
        transport: http,
        run: context.run,
        create: async () => context.run,
      })
      if (note) setLiveNote(note)

      const { run: settledRun, settled } = await waitForRun({
        transport: http,
        runId: run.id,
        timeoutMs: RUN_TIMEOUT_MS,
      })

      const { report, error } = await readReport(http, settledRun.id)
      const detail = await http.getRun(settledRun.id)
      if (controller.signal.aborted) return

      setLive({
        run: settledRun,
        status: settledRun.status,
        evaluation: buildLiveEvaluation({
          detail,
          report,
          findings: report?.findings ?? [],
        }),
        reportGeneratedAt: report?.generated_at ?? null,
        reportId: report?.id ?? null,
        settled,
        error,
      })
      if (!settled) {
        setLiveNote(PROVENANCE.stillRunning(settledRun.status, RUN_TIMEOUT_MS / 1000))
      }
    } catch (cause) {
      // The backend is not reachable, or stopped mid-run. The console is still
      // fully demonstrable against bundled fixtures, and the provenance bar
      // says which it is showing.
      setTransport(new MockTransport())
      setLive(null)
      setLiveNote(
        cause instanceof Error
          ? PROVENANCE.liveUnavailable(cause.message)
          : PROVENANCE.liveUnavailableNoReason,
      )
    } finally {
      clearTimeout(timer)
      setStarting(false)
    }
  }, [])

  const toggleTransport = useCallback((toMock: boolean) => {
    abortRef.current?.abort()
    setLive(null)
    setLiveNote(toMock ? PROVENANCE.fixturesManual : null)
    setTransport(toMock ? new MockTransport() : new HttpTransport())
  }, [])

  /**
   * `#console&demo` opens a live run without a click.
   *
   * The button is the demo's entry point for a person; this is its entry point
   * for anything that cannot click - a screenshot in the e2e check, a slide
   * that should open already running, a link in a README. It runs the same
   * `startDemo` the button does, exactly once per load.
   */
  useEffect(() => {
    if (!route.autoDemo || autoDemoDone) return
    setAutoDemoDone(true)
    void startDemo()
  }, [route.autoDemo, autoDemoDone, startDemo])

  const info = transport ? transport.describe() : MockTransport.describeStatic()
  const hasLiveRun = live !== null && live.evaluation !== null

  const onSelectLiveCase = useCallback((caseId: string) => {
    writeRoute({ view: 'console', caseNumber: caseIdToNumber(caseId, live) })
  }, [live])

  return (
    <div className="shell">
      <Header
        info={info}
        transportStarted={transport !== null}
        starting={starting}
        onToggleTransport={toggleTransport}
        run={live?.run ?? null}
        runNote={liveNote}
      />

      <nav className="viewbar" aria-label="控制台分区">
        <div className="viewbar__keys" role="tablist">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              className="viewbar__key"
              aria-current={route.view === item.id ? 'page' : undefined}
              aria-selected={route.view === item.id}
              onClick={() => writeRoute({ view: item.id, caseNumber: null })}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="viewbar__tools">
          {runtimeStatus && (
            <span className={runtimeStatus.mode === 'live' ? 'u-device' : 'u-micro'}>
              {runtimeStatus.mode === 'live'
                ? `实时大模型 · ${runtimeStatus.model ?? '已配置'}`
                : '确定性模式'}
            </span>
          )}
          {hasLiveRun ? (
            <>
              <span className="u-micro">匹配场景</span>
              <span className="u-device">{live.evaluation!.counts.cases}</span>
              <span className="u-micro">发现</span>
              <span className="u-device">{live.evaluation!.counts.findings}</span>
              <span className="u-micro">证据</span>
              <span className="u-device">{live.evaluation!.counts.evidence}</span>
            </>
          ) : (
            <>
              <span className="u-micro">匹配场景</span>
              <span className="u-device">{scenario.comparison.matched_cases}</span>
              <span className="u-micro">重复采样</span>
              <span className="u-device">{scenario.comparison.repeats}</span>
              <span className="u-micro">随机种子</span>
              <span className="u-device">20260911</span>
            </>
          )}
        </div>
      </nav>

      <main className="shell__main">
        {hasLiveRun ? (
          <>
            {route.view === 'console' && (
              <LiveConsole
                evaluation={live.evaluation!}
                reportMetrics={live.evaluation!.reportMetrics}
                reportGeneratedAt={live.reportGeneratedAt}
                selectedCaseId={route.caseNumber === null ? null : String(route.caseNumber)}
                onSelectCase={(caseId) => onSelectLiveCase(caseId)}
                onClearSelection={() => writeRoute({ caseNumber: null })}
              />
            )}
            {route.view === 'findings' && (
              <LiveFindings evaluation={live.evaluation!} onSelectCase={onSelectLiveCase} />
            )}
            {route.view === 'report' && (
              <LiveReportView
                evaluation={live.evaluation!}
                report={
                  live.reportId && live.reportGeneratedAt
                    ? { id: live.reportId, generated_at: live.reportGeneratedAt }
                    : null
                }
              />
            )}
            {route.view === 'investigation' && (
              <InvestigationWorkspace
                runId={live.run.id}
                autoStart={route.autoDemo}
                runContext={{
                  baselineVersion: live.run.baseline_version,
                  candidateVersion: live.run.candidate_version,
                  matchedCases: live.evaluation!.counts.cases,
                }}
              />
            )}
            {route.view === 'market' && (
              <MarketImpactPanel
                measured={{
                  runLabel: `${live.run.baseline_version} vs ${live.run.candidate_version}`,
                  confirmed: live.evaluation!.reportMetrics.regression_confirmed === true,
                  meanDifference:
                    typeof live.evaluation!.reportMetrics.mean_difference === 'number'
                      ? live.evaluation!.reportMetrics.mean_difference
                      : undefined,
                  ciLow:
                    typeof live.evaluation!.reportMetrics.ci_lower === 'number'
                      ? live.evaluation!.reportMetrics.ci_lower
                      : undefined,
                  ciHigh:
                    typeof live.evaluation!.reportMetrics.ci_upper === 'number'
                      ? live.evaluation!.reportMetrics.ci_upper
                      : undefined,
                  threshold:
                    typeof live.evaluation!.reportMetrics.regression_threshold === 'number'
                      ? live.evaluation!.reportMetrics.regression_threshold
                      : undefined,
                }}
              />
            )}
          </>
        ) : (
          <>
            {route.view === 'console' && (
              <Console
                transport={transport}
                scenario={scenario}
                onScenarioChange={(id) => writeRoute({ scenarioId: id, caseNumber: null })}
                selectedCaseId={selectedCaseId}
                onSelectCase={(id) => {
                  const outcome = scenario.outcomes.find((item) => item.caseId === id)
                  writeRoute({ caseNumber: outcome ? outcome.spec.n : null })
                }}
                starting={starting}
                onStartDemo={startDemo}
              />
            )}

            {route.view === 'findings' && (
              <FindingsView
                scenario={scenario}
                onOpenCase={(id) => {
                  const outcome = scenario.outcomes.find((item) => item.caseId === id)
                  writeRoute({ view: 'console', caseNumber: outcome ? outcome.spec.n : null })
                }}
              />
            )}

            {route.view === 'report' && <ReportView scenario={scenario} transport={transport} />}
            {route.view === 'investigation' && <InvestigationWorkspace />}
            {route.view === 'market' && <MarketImpactPanel />}
          </>
        )}
      </main>
    </div>
  )
}

/**
 * The live run has no scenario *number*: cases are identified by the scenario
 * id the backend assigned. The route keeps its existing `#case=` shape, so
 * this maps a case id to the row's position for the URL and back in the view.
 */
function caseIdToNumber(caseId: string, live: LiveState | null): number | null {
  const rows = live?.evaluation?.cases ?? []
  const index = rows.findIndex((row) => row.candidate.id === caseId || row.baseline.id === caseId)
  return index >= 0 ? index + 1 : null
}

export { DemoEntry }
export type { Scenario }
