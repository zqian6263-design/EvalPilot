import { useCallback, useEffect, useState } from 'react'
import { HttpTransport } from './api/httpTransport'
import { MockTransport } from './api/mockTransport'
import type { Transport } from './api/transport'
import { DemoEntry } from './components/DemoEntry'
import { Header } from './components/Header'
import {
  DEFAULT_SCENARIO_ID,
  SCENARIOS,
  type ScenarioId,
} from './fixtures/scenarios'
import { Console } from './views/Console'
import { FindingsView } from './views/Findings'
import { ReportView } from './views/Report'

export type View = 'console' | 'findings' | 'report'

const VIEWS: ReadonlyArray<{ id: View; label: string }> = [
  { id: 'console', label: 'Run console' },
  { id: 'findings', label: 'Findings' },
  { id: 'report', label: 'Report' },
]

/**
 * Probe timeout for the backend. Long enough for a cold FastAPI start on a
 * developer machine, short enough that a judge never watches a dead spinner —
 * after which the console falls back to bundled fixtures and says so.
 */
const PROBE_TIMEOUT_MS = 1200

/** `#report`, `#findings`, `#console`, `#case=09`, `#scenario=improvement`. */
interface Route {
  view: View
  caseNumber: number | null
  scenarioId: ScenarioId
}

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#/, '')
  const params = new URLSearchParams(hash)

  const view = VIEWS.find((item) => params.has(item.id))?.id ?? 'console'
  const rawCase = Number(params.get('case'))
  const caseNumber = Number.isInteger(rawCase) && rawCase > 0 ? rawCase : null
  const scenario =
    SCENARIOS.find((item) => item.id === params.get('scenario'))?.id ?? DEFAULT_SCENARIO_ID

  return { view, caseNumber, scenarioId: scenario }
}

function writeRoute(route: Partial<Route>): void {
  const next = { ...readRoute(), ...route }
  const params = new URLSearchParams()
  params.set(next.view, '')
  if (next.scenarioId !== DEFAULT_SCENARIO_ID) params.set('scenario', next.scenarioId)
  if (next.caseNumber !== null) params.set('case', String(next.caseNumber))
  window.location.hash = params.toString()
}

/**
 * Deep links are a demo feature, not a nicety: a presenter moving between
 * slides wants `#report` and `#case=22` to be plain URLs they can put on a
 * slide, and a reviewer wants to send a colleague the exact case they mean.
 */
export function App(): React.JSX.Element {
  const [route, setRoute] = useState<Route>(() => readRoute())
  const [transport, setTransport] = useState<Transport | null>(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    const onHashChange = (): void => setRoute(readRoute())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const scenario = SCENARIOS.find((item) => item.id === route.scenarioId)!
  const selectedCaseId =
    route.caseNumber === null
      ? null
      : (scenario.outcomes.find((outcome) => outcome.spec.n === route.caseNumber)?.caseId ?? null)

  const startDemo = useCallback(async () => {
    setStarting(true)
    const probe = new AbortController()
    const timer = setTimeout(() => probe.abort(), PROBE_TIMEOUT_MS)
    try {
      const http = new HttpTransport()
      await http.health()
      setTransport(http)
    } catch {
      // The backend is not reachable. The console is still fully demonstrable
      // against bundled fixtures, and the provenance bar states which it is.
      setTransport(new MockTransport())
    } finally {
      clearTimeout(timer)
      setStarting(false)
    }
  }, [])

  const toggleTransport = useCallback((toMock: boolean) => {
    setTransport(toMock ? new MockTransport() : new HttpTransport())
  }, [])

  const info = transport ? transport.describe() : MockTransport.describeStatic()

  return (
    <div className="shell">
      <Header
        info={info}
        transportStarted={transport !== null}
        starting={starting}
        onToggleTransport={toggleTransport}
      />

      <nav className="viewbar" aria-label="Console sections">
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
          <span className="u-micro">Matched cases</span>
          <span className="u-device">{scenario.comparison.matched_cases}</span>
          <span className="u-micro">Repeats</span>
          <span className="u-device">{scenario.comparison.repeats}</span>
          <span className="u-micro">Seed</span>
          <span className="u-device">20260911</span>
        </div>
      </nav>

      <main className="shell__main">
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
      </main>
    </div>
  )
}

export { DemoEntry }
