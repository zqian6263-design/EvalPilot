import type { TransportInfo } from '../api/transport'
import type { Run } from '../api/types'

interface Props {
  info: TransportInfo
  transportStarted: boolean
  starting: boolean
  onToggleTransport: (toMock: boolean) => void
  /** The live run, when one was resolved. Null while showing fixtures. */
  run: Run | null
  /** A one-line note about how the data source was chosen, when there is one. */
  runNote: string | null
}

/**
 * The identification plate: who the run is, and — in the provenance bar
 * directly beneath — where the numbers on screen came from.
 *
 * The plate names the actual run when the console is showing one. Before a
 * demo run exists it names the project and versions the *seed* advertises, and
 * says the run is not yet resolved, because printing a run id the backend
 * never issued is the one label a reviewer cannot check.
 *
 * The provenance bar is not decoration. Every figure in this console is
 * fixture data unless a backend answered the health probe, and a reviewer
 * must be able to tell which at a glance.
 */
export function Header({
  info,
  transportStarted,
  starting,
  onToggleTransport,
  run,
  runNote,
}: Props): React.JSX.Element {
  const live = info.live

  return (
    <>
      <header className="header">
        <div className="header__id">
          <span className="u-micro">EvalPilot — regression evaluation console</span>
          <h1 className="header__name">Enterprise knowledge-base assistant</h1>
          <div className="header__meta u-device">
            <span>
              <span className="u-micro">Project</span>{' '}
              {run ? run.project_id.slice(0, 8) : live ? 'kb-qa (seed)' : 'kb-assistant'}
            </span>
            <span>
              <span className="u-micro">Baseline</span>{' '}
              {run ? run.baseline_version : live ? 'v1.0-baseline (seed)' : 'v1.4.2'}
            </span>
            <span>
              <span className="u-micro">Candidate</span>{' '}
              {run ? run.candidate_version : live ? 'v1.1-candidate (seed)' : 'v1.5.0-rc1'}
            </span>
            <span>
              <span className="u-micro">Run</span>{' '}
              {run ? run.id.slice(0, 8) : live ? 'not started' : 'a4f1c8e2'}
            </span>
          </div>
        </div>

        <div className="header__right">
          <div className="stack" style={{ gap: 'var(--s1)' }}>
            <span className="u-micro">Data source</span>
            <div className="rocker" role="group" aria-label="Data source">
              <button
                type="button"
                className="rocker__pos"
                aria-pressed={!live}
                onClick={() => onToggleTransport(true)}
              >
                Fixtures
              </button>
              <button
                type="button"
                className="rocker__pos"
                aria-pressed={live}
                onClick={() => onToggleTransport(false)}
              >
                Backend
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="provenance">
        <span
          className={`provenance__lamp ${live ? 'provenance__lamp--live' : 'provenance__lamp--mock'}`}
          aria-hidden="true"
        />
        <span className="u-micro" style={{ color: 'var(--chassis-label)' }}>
          {starting ? 'Probing backend…' : live ? 'Live backend' : 'Offline demo — bundled fixtures'}
        </span>
        <span className="provenance__note">
          {runNote
            ? runNote
            : live
              ? `${info.baseUrl ?? '/api'} · values come from the running service`
              : 'Every figure below is seeded fixture data, not a real evaluation'}
        </span>
        {!transportStarted && !starting && (
          <span className="provenance__note" style={{ marginLeft: 'auto' }}>
            press START DEMO below to probe the backend
          </span>
        )}
      </div>
    </>
  )
}
