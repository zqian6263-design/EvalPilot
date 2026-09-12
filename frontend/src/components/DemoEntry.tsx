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
      <section className="scenario" aria-label="演示场景">
        <span className="u-micro">预置场景</span>
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

      <section className="entry" aria-label="演示入口">
        <div className="entry__guard">
          <button
            type="button"
            className="ctl ctl--primary"
            onClick={onStartDemo}
            disabled={starting}
          >
            {starting ? '正在启动…' : '启动演示运行'}
          </button>
          <p className="entry__note">
            加载预置项目及其两个版本。后端可达时会创建或打开这两个版本的真实运行并实时执行 ——
            再次点击只会重新打开同一个运行，而不会创建第二个。后端不可达时，控制台改为展示内置夹具数据中的同一场景，
            并明确标注数据为离线。
          </p>
        </div>
        <div className="entry__controls">
          <span className="u-micro">确定性随机种子</span>
          <span className="u-device">20260911</span>
        </div>
      </section>
    </>
  )
}
