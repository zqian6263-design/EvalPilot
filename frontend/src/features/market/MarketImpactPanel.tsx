import type { JSX, ReactNode } from 'react'
// Imported here rather than from `styles/index.css`, which is an existing file
// this feature does not own. Same bundle either way.
import '../../styles/market.css'
import {
  MOAT,
  PRICING,
  PRICING_FALSIFIER,
  PROOF_LADDER,
  ROI_INPUT_BY_ID,
  currentProofLevel,
  formatBand,
  formatCompact,
  formatCount,
  roiBandSpread,
  roiCostBand,
  roiIsUnresolved,
  roiValueBand,
  rungsToRevenue,
  TRACTION,
  ZERO_TRACTION_DISCLOSURE,
  bandPosition,
  GTM_PLAN,
  GTM_SUCCESS_DEFINITION,
} from './marketModel'
import type { RoiBand } from './marketModel'
import {
  SOURCE_TAG_LABEL,
  confidenceLabel,
  factBasisLabel,
  moatStrengthLabel,
} from '../../i18n/labels'
import {
  CRITERIA,
  MAX_TOTAL,
  POSITION,
  TRACTION_ROWS,
  sourceLabel,
  totalSelfScore,
  totalTargetScore,
} from './marketFixtures'

/**
 * The run the panel is mounted beside, when there is one.
 *
 * All fields are optional on purpose: a panel dropped onto a page with no run
 * must still render, and must say it has no run rather than borrowing the
 * report's authority. `meanDifference` and the interval are in the engine's own
 * units — a mean score difference between baseline and candidate, not a
 * percentage — which is why they are printed through the device face and
 * never recomputed here.
 */
export interface MarketMeasuredContext {
  /** How to name the run, e.g. `v1.4.2 vs v1.5.0-rc1`. */
  runLabel?: string | undefined
  /** `false` means the run is attributed but has no verdict yet. */
  confirmed?: boolean | undefined
  meanDifference?: number | undefined
  ciLow?: number | undefined
  ciHigh?: number | undefined
  threshold?: number | undefined
}

export interface MarketImpactPanelProps {
  /**
   * Attribute the panel's product figures to the run it is mounted beside.
   * Omit it and the panel says it has no run. It never changes what the *market*
   * claims — those are always labelled as assumptions.
   */
  measured?: MarketMeasuredContext
  /**
   * The host page's own investigation surface, injected so this feature can sit
   * beside a workspace it must not import. Omit it and a placeholder explains
   * where the workspace goes.
   */
  renderWorkspace?: () => ReactNode
}

/**
 * A label rendered beside a block, so no number is ever unlabelled.
 *
 * The chip's text is Chinese; its `title` is the model's own `meaning` string,
 * which is the sentence saying what kind of number this block carries. The
 * class suffix is the id, so the styling follows the honest category rather
 * than the word.
 */
function SourceTag({ id }: { id: Parameters<typeof sourceLabel>[0] }): JSX.Element {
  const label = sourceLabel(id)
  return (
    <span className={`mkt__tag mkt__tag--${label.id}`} title={label.meaning}>
      {SOURCE_TAG_LABEL[id] ?? label.text}
    </span>
  )
}

/**
 * The ROI band as a strip chart.
 *
 * Four inputs are assumptions with a low and a high each, so the output is an
 * interval spanning more than two orders of magnitude. Drawing that as a bar
 * is the whole honesty of the block: a point estimate would be a number nobody
 * could defend, and the chart makes it structurally awkward to print one. The
 * log axis is not decoration — on a linear axis every reading of interest
 * collapses onto the left edge.
 *
 * The same information is stated in words below the chart; nothing here is
 * legible only from the drawing.
 */
function RoiStrip(): JSX.Element {
  const value = roiValueBand()
  const cost = roiCostBand()
  const spread = roiBandSpread()
  const unresolved = roiIsUnresolved(spread)

  // One domain for both bands, so their sizes are comparable rather than each
  // being stretched to fill its own row.
  const domain: RoiBand = {
    low: Math.min(value.low, cost.low),
    high: Math.max(value.high, cost.high),
  }

  const W = 1000
  const PAD_L = 24
  const PAD_R = 24
  const PLOT_W = W - PAD_L - PAD_R
  const x = (v: number): number => PAD_L + bandPosition(v, domain) * PLOT_W

  const ticks = decadeTicks(domain)
  const midpoint = Math.sqrt(value.low * value.high)

  return (
    <div className="mkt__strip">
      <svg
        className="mkt__svg"
        viewBox={`0 0 ${W} 132`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`避免糟糕发布所带来的年化价值 ${formatBand(value)}。本工具的年化建模成本 ${formatBand(cost)}。`}
      >
        <title>年化价值与年化建模成本的对比</title>
        <desc>
          价值区间跨越 {spread === null ? '无限多' : spread.toFixed(1)} 个数量级，并与成本区间重叠。
          因此该模型在任何方向上都不支持给出一个有把握的回报数字。
        </desc>

        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={x(tick)}
              x2={x(tick)}
              y1={16}
              y2={112}
              stroke="var(--mkt-grid)"
              strokeWidth="1"
            />
            <text x={x(tick)} y={126} textAnchor="middle" className="mkt__axis-label">
              ¥{formatCompact(tick)}
            </text>
          </g>
        ))}

        {/* The value band, drawn first so the cost bar reads as sitting inside it. */}
        <rect
          x={x(value.low)}
          y={20}
          width={Math.max(x(value.high) - x(value.low), 2)}
          height={34}
          fill="var(--mkt-band)"
          stroke="var(--mkt-band-edge)"
          strokeWidth="1"
        />
        {/* An open marker for the midpoint: computed, and explicitly not a claim. */}
        <line
          x1={x(midpoint)}
          x2={x(midpoint)}
          y1={14}
          y2={60}
          stroke="var(--mkt-grid-ink)"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
        <circle
          cx={x(midpoint)}
          cy={37}
          r={4}
          fill="var(--mkt-empty)"
          stroke="var(--mkt-grid-ink)"
          strokeWidth="1"
        />
        <text x={x(midpoint) + 8} y={41} className="mkt__axis-label">
          中点 —— 不是证据
        </text>

        {/* The cost of the tool itself, on the same axis. */}
        <rect
          x={x(cost.low)}
          y={74}
          width={Math.max(x(cost.high) - x(cost.low), 2)}
          height={20}
          fill="var(--mkt-cost)"
        />
        <text x={x(cost.low)} y={108} className="mkt__axis-label">
          本工具的建模成本
        </text>
      </svg>

      <dl className="mkt__band">
        <div className="mkt__band-item">
          <dt className="u-micro">价值区间 / 年</dt>
          <dd className="mkt__band-value mkt__band-value--band">{formatBand(value)}</dd>
        </div>
        <div className="mkt__band-item">
          <dt className="u-micro">成本区间 / 年</dt>
          <dd className="mkt__band-value mkt__band-value--cost">{formatBand(cost)}</dd>
        </div>
        <div className="mkt__band-item">
          <dt className="u-micro">区间跨度</dt>
          <dd className="mkt__band-value">
            {spread === null ? '无上界' : `${spread.toFixed(2)} 个数量级`}
          </dd>
        </div>
        <div className="mkt__band-item">
          <dt className="u-micro">读数</dt>
          <dd className={`mkt__verdict mkt__verdict--${unresolved ? 'unresolved' : 'narrow'}`}>
            {unresolved ? '无法判定' : '足够窄，可以引用'}
          </dd>
        </div>
      </dl>

      <p className="mkt__note">
        {unresolved
          ? '四个输入中有两个从未在任何真实部署上被观测过，因此价值区间跨越了一个以上的数量级，并与工具成本重叠。该模型在任何方向上都不支持给出一个有把握的回报数字，中点也不是证据。来自一个真实团队的两个事后数字，比任何进一步的建模都更能收窄它。'
          : '该区间已经窄到可以连同其假设一起引用。'}
      </p>
    </div>
  )
}

/** 1-2-5 ticks across a log domain, so the axis stays readable at any span. */
function decadeTicks(domain: RoiBand): number[] {
  const out: number[] = []
  const first = Math.floor(Math.log10(domain.low))
  const last = Math.ceil(Math.log10(domain.high))
  for (let decade = first; decade <= last; decade += 1) {
    for (const multiplier of [1, 2, 5]) {
      const value = multiplier * 10 ** decade
      if (value >= domain.low && value <= domain.high) out.push(value)
    }
  }
  // A domain narrower than one 1-2-5 step would otherwise render an empty axis.
  return out.length >= 2 ? out : [domain.low, domain.high]
}

/** The ladder of evidence, weakest rung first, with our own rung marked. */
function ProofLadder(): JSX.Element {
  const current = currentProofLevel()
  const currentIndex = PROOF_LADDER.indexOf(current)

  return (
    <div className="mkt__ladder" role="list" aria-label="证据阶梯">
      {PROOF_LADDER.map((level, index) => {
        const state = index < currentIndex ? 'passed' : index === currentIndex ? 'current' : 'ahead'
        return (
          <div className={`mkt__rung mkt__rung--${state}`} role="listitem" key={level.id}>
            <div className="mkt__rung-head">
              <span className="mkt__rung-mark" aria-hidden="true">
                {state === 'passed' ? '●' : state === 'current' ? '▶' : '○'}
              </span>
              <span className="mkt__rung-label">{level.label}</span>
              <span className="mkt__rung-state">
                {state === 'current' ? '我们在这里' : state === 'ahead' ? '尚未达到' : '已通过'}
              </span>
            </div>
            <p className="mkt__rung-def">{level.definition}</p>
            {state === 'current' && (
              <p className="mkt__rung-requires">
                <span className="u-micro">主张这一级所需</span> {level.requires}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function MarketImpactPanel({
  measured,
  renderWorkspace,
}: MarketImpactPanelProps): JSX.Element {
  const value = roiValueBand()
  const current = currentProofLevel()
  const remaining = rungsToRevenue()
  const widestGap = CRITERIA.reduce((worst, criterion) =>
    criterion.target - criterion.selfScore > worst.target - worst.selfScore ? criterion : worst,
  )

  return (
    <div className="mkt">
      <header className="mkt__masthead">
        <div className="mkt__plate">
          <span className="u-micro">市场定位 · 战略假设，尚未验证</span>
          <h1 className="mkt__title">AI 应用需要一个发布门禁</h1>
        </div>
        <div className="mkt__plate mkt__plate--right">
          <span className="u-micro">评分表目标分</span>
          <span className="mkt__score">
            {totalTargetScore()}
            <span className="mkt__score-denom">/{MAX_TOTAL}</span>
          </span>
          <span className="u-micro">有证据支撑，尚未验证</span>
        </div>
      </header>

      {/* The disclosure is a block, not a footnote. It is the first thing read. */}
      <section className="mkt__disclosure" aria-label="零牵引力声明">
        <span className="mkt__tag mkt__tag--none">无数据</span>
        <p className="mkt__disclosure-text">{ZERO_TRACTION_DISCLOSURE}</p>
      </section>

      {/* ---------------------------------------------------------- traction -- */}
      <section className="mkt__block mkt__block--traction" aria-label="牵引力">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">牵引力</h2>
          <SourceTag id="none" />
        </div>
        <div className="mkt__counts">
          {TRACTION_ROWS.map((row) => {
            const counted = TRACTION[row.key]
            return (
              <div className="mkt__count" key={row.key}>
                <span className="u-micro">{row.label}</span>
                <span className="mkt__count-value">{formatCount(counted)}</span>
                <span className="mkt__count-note">{counted.note}</span>
              </div>
            )
          })}
        </div>
        <p className="mkt__note">
          短横线表示<em>未测量</em>，而不是<em>测量结果为零</em>。这是两种不同的断言，而此处只有前者为真。
        </p>
      </section>

      {/* ------------------------------------------------------------ ladder -- */}
      <section className="mkt__block mkt__block--ladder" aria-label="证据阶梯">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">进展是一种状态，不是一个计数</h2>
          <SourceTag id="target" />
        </div>
        <p className="mkt__lede">
          一个已交付的产品不等于一次试点，一次试点也不等于一个客户。在收入出现之前，报告进展最诚实的方式是说明我们正站在阶梯的哪一级 ——
          目前是<strong>{current.label}</strong>，距离第一位付费客户还有 <strong>{remaining} 级</strong>。
        </p>
        <ProofLadder />
      </section>

      {/* --------------------------------------------------------------- ROI -- */}
      <section className="mkt__block mkt__block--roi" aria-label="投资回报">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">回报，以区间呈现</h2>
          <SourceTag id="assumption" />
        </div>
        <p className="mkt__lede">
          年化价值 = 一次被避免的糟糕发布 × 一年发生多少次 × 本工具能拦下多少。四个输入，每一个都是猜测，
          因此答案是一个区间：每年 {formatBand(value)}。下方可调，读者可以直接代入自己的数字，而不必跟我们的数字争论。
        </p>
        <RoiStrip />
        <table className="record mkt__assumptions">
          <caption className="visually-hidden">ROI 模型的输入项及其依据</caption>
          <thead>
            <tr>
              <th scope="col">输入项</th>
              <th scope="col">下限</th>
              <th scope="col">上限</th>
              <th scope="col">依据</th>
              <th scope="col">可被什么替换</th>
            </tr>
          </thead>
          <tbody>
            {[...ROI_INPUT_BY_ID.values()].map((input) => (
              <tr key={input.id}>
                <td>
                  <span className="mkt__input-label">{input.label}</span>
                  <span className="mkt__input-detail">{input.detail}</span>
                </td>
                <td className="u-num">{formatCompact(input.low)}</td>
                <td className="u-num">{formatCompact(input.high)}</td>
                <td>
                  <span className={`mkt__basis mkt__basis--${input.basis}`}>
                    {factBasisLabel(input.basis)}
                  </span>
                </td>
                <td className="mkt__input-detail">{input.would_measure_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* ----------------------------------------------------------- pricing -- */}
      <section className="mkt__block" aria-label="定价假设">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">定价假设</h2>
          <SourceTag id="target" />
        </div>
        <p className="mkt__lede">
          这个页面上没有任何一个价格曾被报价给任何人，更不用说被支付过。以下是我们打算测试的形态，
          并附上推理过程 —— 这样被质疑的可以是推理，而不是那个数字。
        </p>
        <div className="mkt__prices">
          {PRICING.map((rung) => (
            <article className="mkt__price" key={rung.id}>
              <div className="mkt__price-head">
                <h3 className="mkt__price-name">{rung.name}</h3>
                <span className={`mkt__basis mkt__basis--${rung.basis}`}>
                  {factBasisLabel(rung.basis)}
                </span>
              </div>
              <span className="mkt__price-shape">{rung.shape}</span>
              <ul className="mkt__list">
                {rung.includes.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <p className="mkt__note">{rung.rationale}</p>
            </article>
          ))}
        </div>
        <p className="mkt__falsifier">
          <span className="u-micro">证伪条件</span> {PRICING_FALSIFIER}
        </p>
      </section>

      {/* --------------------------------------------------------------- GTM -- */}
      <section className="mkt__block" aria-label="市场进入">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">从零开始，九十天</h2>
          <SourceTag id="target" />
        </div>
        <p className="mkt__lede">{GTM_SUCCESS_DEFINITION}</p>
        <ol className="mkt__stages">
          {GTM_PLAN.map((stage) => (
            <li className="mkt__stage" key={stage.n}>
              <div className="mkt__stage-head">
                <span className="mkt__stage-n">{String(stage.n).padStart(2, '0')}</span>
                <div className="mkt__stage-plate">
                  <span className="mkt__stage-name">{stage.name}</span>
                  <span className="u-micro">{stage.window}</span>
                </div>
              </div>
              <dl className="mkt__stage-body">
                <dt className="u-micro">目标</dt>
                <dd>{stage.goal}</dd>
                <dt className="u-micro">交付物</dt>
                <dd>{stage.artifact}</dd>
                <dt className="u-micro">终止条件</dt>
                <dd className="mkt__kill">{stage.kill}</dd>
              </dl>
            </li>
          ))}
        </ol>
      </section>

      {/* -------------------------------------------------------------- moat -- */}
      <section className="mkt__block" aria-label="护城河">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">护城河，逐层来看</h2>
          <SourceTag id="assumption" />
        </div>
        <p className="mkt__lede">
          只宣称一条护城河是省事的版本。这几层确实各不相同，而且其中一层根本算不上防御。
        </p>
        <div className="mkt__moat">
          {MOAT.map((layer) => (
            <article className="mkt__moat-layer" key={layer.id}>
              <div className="mkt__moat-head">
                <h3 className="mkt__moat-name">{layer.name}</h3>
                <span className={`mkt__strength mkt__strength--${layer.strength}`}>
                  {moatStrengthLabel(layer.strength)}
                </span>
              </div>
              <p className="mkt__moat-claim">{layer.claim}</p>
              <p className="mkt__note">{layer.why}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------- criteria -- */}
      <section className="mkt__block" aria-label="赛道评分表">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">五个维度，每项 20 分</h2>
          <SourceTag id="assumption" />
        </div>
        <p className="mkt__lede">
          团队给自己打分是整份参赛材料里最弱的证据。以下是我们给自己的分数，附上我们对它的把握程度，
          以及每一项要怎样才能真正提分。
        </p>

        <div className="mkt__attribution">
          <span className="u-micro">归因到本面板的运行</span>
          <span className="mkt__run">
            {measured?.runLabel ?? '无 —— 本面板独立渲染'}
          </span>
          {measured && measured.confirmed !== undefined && (
            <span className="mkt__run-figures">
              {measured.confirmed ? '已确认回归' : '无裁决记录'}
              {measured.meanDifference !== undefined &&
                ` · 均值 ${measured.meanDifference.toFixed(3)}`}
              {measured.ciLow !== undefined &&
                measured.ciHigh !== undefined &&
                ` · 95% 置信区间 ${measured.ciLow.toFixed(3)} 至 ${measured.ciHigh.toFixed(3)}`}
              {measured.threshold !== undefined &&
                ` · 阈值 ${measured.threshold.toFixed(3)}`}
            </span>
          )}
        </div>

        <table className="record mkt__criteria">
          <caption className="visually-hidden">自评的赛道评分表</caption>
          <thead>
            <tr>
              <th scope="col">评分维度</th>
              <th scope="col">自评</th>
              <th scope="col">满分</th>
              <th scope="col">把握程度</th>
              <th scope="col">目标</th>
              <th scope="col">差距</th>
            </tr>
          </thead>
          <tbody>
            {CRITERIA.map((criterion) => {
              const gap = criterion.target - criterion.selfScore
              return (
                <tr key={criterion.id}>
                  <td>{criterion.official}</td>
                  <td className="u-num mkt__criterion-score">{criterion.selfScore}</td>
                  <td className="u-num">{criterion.max}</td>
                  <td>
                    <span className={`mkt__confidence mkt__confidence--${criterion.confidence}`}>
                      {confidenceLabel(criterion.confidence)}
                    </span>
                  </td>
                  <td className="u-num">{criterion.target}</td>
                  <td className={`u-num mkt__gap${gap >= 5 ? ' mkt__gap--wide' : ''}`}>{gap}</td>
                </tr>
              )
            })}
            <tr>
              <td className="u-label">合计</td>
              <td className="u-num mkt__criterion-score">{totalSelfScore()}</td>
              <td className="u-num">{MAX_TOTAL}</td>
              <td />
              <td className="u-num">{totalTargetScore()}</td>
              <td className="u-num mkt__gap">
                {totalTargetScore() - totalSelfScore()}
              </td>
            </tr>
          </tbody>
        </table>

        <div className="mkt__actions">
          {CRITERIA.map((criterion) => (
            <details className="mkt__criterion" key={criterion.id} open={criterion.id === widestGap.id}>
              <summary className="mkt__criterion-summary">
                <span className="mkt__criterion-name">{criterion.official}</span>
                <span className="mkt__criterion-question">{criterion.question}</span>
              </summary>
              <div className="mkt__criterion-body">
                <p className="mkt__note">
                  <span className="u-micro">证据</span> {criterion.evidence}
                </p>
                <p className="mkt__note">
                  <span className="u-micro">差距</span> {criterion.gap}
                </p>
                <ol className="mkt__action-list">
                  {criterion.actions.map((action) => (
                    <li className="mkt__action" key={action.id}>
                      <span className="mkt__action-id">{action.id}</span>
                      <div className="mkt__action-body">
                        <p>{action.what}</p>
                        <p className="mkt__action-verify">
                          <span className="u-micro">验证方式</span> {action.verification}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            </details>
          ))}
        </div>

        <div className="mkt__ledgers">
          <div className="mkt__ledger">
            <span className="u-label">已在我们自己的语料上演示</span>
            <ul className="mkt__list">
              {POSITION.demonstrated.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="mkt__ledger mkt__ledger--missing">
            <span className="u-label">完全缺失</span>
            <ul className="mkt__list">
              {POSITION.missing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- workspace -- */}
      <section className="mkt__block" aria-label="调查工作区">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">产品本身，运行在它旁边</h2>
          <SourceTag id="fixture" />
        </div>
        <p className="mkt__lede">
          这一块是宿主页面挂载它自己的调查界面的位置。它是被注入的，而不是被导入的，
          因此本功能可以与该工作区并排存在却不依赖它。
        </p>
        {renderWorkspace ? (
          renderWorkspace()
        ) : (
          <p className="mkt__placeholder">
            未注入工作区。传入 <code>renderWorkspace</code> 即可在此挂载一个。
          </p>
        )}
      </section>

      <footer className="mkt__footer">
        <p className="mkt__footer-text">
          {POSITION.headline} 这个页面上的每一个商业数字都是假设、目标或区间；每一个产品数字都标注为实测或夹具数据。
          如果后续版本要报告牵引力，那个数字必须点出具体的合作方，否则就不写进来。
        </p>
      </footer>
    </div>
  )
}
