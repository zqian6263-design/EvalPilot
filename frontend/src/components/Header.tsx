import type { TransportInfo } from '../api/transport'
import type { Run } from '../api/types'
import { PROVENANCE } from '../i18n/labels'

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
          <span className="u-micro">EvalPilot — 回归评估控制台</span>
          <h1 className="header__name">企业知识库问答助手</h1>
          <div className="header__meta u-device">
            <span>
              <span className="u-micro">项目</span>{' '}
              {run ? run.project_id.slice(0, 8) : live ? 'kb-qa（种子）' : 'kb-assistant'}
            </span>
            <span>
              <span className="u-micro">基线版本</span>{' '}
              {run ? run.baseline_version : live ? 'v1.0-baseline（种子）' : 'v1.4.2'}
            </span>
            <span>
              <span className="u-micro">候选版本</span>{' '}
              {run ? run.candidate_version : live ? 'v1.1-candidate（种子）' : 'v1.5.0-rc1'}
            </span>
            <span>
              <span className="u-micro">运行</span>{' '}
              {run ? run.id.slice(0, 8) : live ? '未启动' : 'a4f1c8e2'}
            </span>
          </div>
        </div>

        <div className="header__right">
          <div className="stack" style={{ gap: 'var(--s1)' }}>
            <span className="u-micro">数据来源</span>
            <div className="rocker" role="group" aria-label="数据来源">
              <button
                type="button"
                className="rocker__pos"
                aria-pressed={!live}
                onClick={() => onToggleTransport(true)}
              >
                夹具数据
              </button>
              <button
                type="button"
                className="rocker__pos"
                aria-pressed={live}
                onClick={() => onToggleTransport(false)}
              >
                后端服务
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
          {starting
            ? PROVENANCE.probing
            : live
              ? PROVENANCE.live
              : PROVENANCE.offline}
        </span>
        <span className="provenance__note">
          {runNote
            ? runNote
            : live
              ? PROVENANCE.liveValues(info.baseUrl ?? '/api')
              : PROVENANCE.offlineValues}
        </span>
        {!transportStarted && !starting && (
          <span className="provenance__note" style={{ marginLeft: 'auto' }}>
            {PROVENANCE.pressStart}
          </span>
        )}
      </div>
    </>
  )
}
