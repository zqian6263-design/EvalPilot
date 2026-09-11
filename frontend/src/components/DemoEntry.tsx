import { SCENARIOS, type ScenarioId } from '../fixtures/scenarios'

interface Props {
  scenarioId: ScenarioId
  onScenarioChange: (id: ScenarioId) => void
  starting: boolean
  onStartDemo: () => void
}

/**
 * The one-click demo entry.
 *
 * The primary key is deliberately the largest control in the first viewport.
 * It probes `/api/health` once; if the backend answers, the console runs
 * against it, and if it does not, the console runs against bundled fixtures
 * and says so. Either way the demo is one click from a cold page load.
 */
export function DemoEntry({ scenarioId, onScenarioChange, starting, onStartDemo }: Props): React.JSX.Element {
  return (
    <>
      <section className="scenario" aria-label="Demo scenario">
        <span className="u-micro">Seeded scenario</span>
        <div className="scenario__options">
          {SCENARIOS.map((scenario) => (
            <button
              key={scenario.id}
              type="button"
              className="scenario__option"
              aria-pressed={scenario.id === scenarioId}
              onClick={() => onScenarioChange(scenario.id)}
            >
              <span className="scenario__name">{scenario.label}</span>
              <span className="scenario__note">{scenario.note}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="entry" aria-label="Demo entry">
        <div className="entry__guard">
          <button
            type="button"
            className="ctl ctl--primary"
            onClick={onStartDemo}
            disabled={starting}
          >
            {starting ? 'Starting…' : 'Start demo run'}
          </button>
          <p className="entry__note">
            Loads the seeded project and both versions. If the backend is reachable it runs
            live; if not, the console presents the same run from bundled fixtures and marks
            the data as offline.
          </p>
        </div>
        <div className="entry__controls">
          <span className="u-micro">Deterministic seed</span>
          <span className="u-device">20260911</span>
        </div>
      </section>
    </>
  )
}
