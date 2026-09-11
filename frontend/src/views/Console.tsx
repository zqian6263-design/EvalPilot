import { useMemo } from 'react'
import type { Transport } from '../api/transport'
import { CaseTable } from '../components/CaseTable'
import { EventIndex } from '../components/EventIndex'
import { EvidenceDrawer } from '../components/EvidenceDrawer'
import { DemoEntry } from '../components/DemoEntry'
import { Metrics } from '../components/Metrics'
import { Tape } from '../components/Tape'
import { Verdict } from '../components/Verdict'
import type { Scenario } from '../fixtures/scenarios'

interface Props {
  transport: Transport | null
  scenario: Scenario
  onScenarioChange: (id: Scenario['id']) => void
  selectedCaseId: string | null
  onSelectCase: (caseId: string | null) => void
  starting: boolean
  onStartDemo: () => void
}

/**
 * The run console: the tape on the left, the verdict and metrics beside it,
 * the record and the event index below.
 *
 * Reading order is deliberate. Verdict first, so nobody has to interpret a
 * chart to learn the answer; the tape second, so they can check it; the
 * record third, so they can audit it; evidence only when they ask for it.
 */
export function Console({
  transport,
  scenario,
  onScenarioChange,
  selectedCaseId,
  onSelectCase,
  starting,
  onStartDemo,
}: Props): React.JSX.Element {
  const selectedOutcome = useMemo(
    () => scenario.outcomes.find((outcome) => outcome.caseId === selectedCaseId) ?? null,
    [scenario, selectedCaseId],
  )

  const activeCaseNumber = selectedOutcome ? selectedOutcome.spec.n : null

  const jumpToCase = (caseNumber: number): void => {
    const outcome = scenario.outcomes.find((o) => o.spec.n === caseNumber)
    if (outcome) onSelectCase(outcome.caseId)
  }

  return (
    <>
      <DemoEntry
        scenarioId={scenario.id}
        onScenarioChange={onScenarioChange}
        starting={starting}
        onStartDemo={onStartDemo}
      />

      {transport && !transport.describe().live && (
        <div className="notice notice--alert">
          <span className="notice__tag">Offline</span>
          <span>
            The backend did not answer <code className="u-device">/api/health</code>. This run is
            served from bundled fixtures and reproduces identically on every load — useful for a
            demo, but it is not evidence about a real system. Press{' '}
            <strong>Start demo run</strong> again once the backend is up to switch to the real
            service; the header will name the run it opens.
          </span>
        </div>
      )}

      <div className="console">
        <div className="console__tape">
          <Tape
            scenario={scenario}
            selectedCaseNumber={activeCaseNumber}
            onSelectCase={onSelectCase}
          />
          <Verdict scenario={scenario} />
          <CaseTable
            scenario={scenario}
            selectedCaseId={selectedCaseId}
            onSelectCase={onSelectCase}
          />
        </div>

        <div className="console__side">
          <Metrics scenario={scenario} />
          <EventIndex
            scenarioId={scenario.id}
            onJumpToCase={jumpToCase}
            activeCaseNumber={activeCaseNumber}
          />
        </div>
      </div>

      {selectedOutcome && (
        <EvidenceDrawer outcome={selectedOutcome} onClose={() => onSelectCase(null)} />
      )}
    </>
  )
}
