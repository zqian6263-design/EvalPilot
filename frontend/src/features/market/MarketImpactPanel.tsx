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

/** A label rendered beside a block, so no number is ever unlabelled. */
function SourceTag({ id }: { id: Parameters<typeof sourceLabel>[0] }): JSX.Element {
  const label = sourceLabel(id)
  return (
    <span className={`mkt__tag mkt__tag--${label.id}`} title={label.meaning}>
      {label.text}
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
        aria-label={`Annual value of avoided bad releases, ${formatBand(value)}. Modelled annual cost of this tool, ${formatBand(cost)}.`}
      >
        <title>Modelled annual value against modelled annual cost</title>
        <desc>
          The value band spans {spread === null ? 'an unbounded' : spread.toFixed(1)} orders of
          magnitude and overlaps the cost band. The model therefore does not support a confident
          return figure in either direction.
        </desc>

        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={x(tick)}
              x2={x(tick)}
              y1={16}
              y2={112}
              stroke="var(--graphite-faint)"
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
          fill="var(--band)"
          stroke="var(--band-edge)"
          strokeWidth="1"
        />
        {/* An open marker for the midpoint: computed, and explicitly not a claim. */}
        <line
          x1={x(midpoint)}
          x2={x(midpoint)}
          y1={14}
          y2={60}
          stroke="var(--graphite)"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
        <circle
          cx={x(midpoint)}
          cy={37}
          r={4}
          fill="var(--ground)"
          stroke="var(--graphite)"
          strokeWidth="1"
        />
        <text x={x(midpoint) + 8} y={41} className="mkt__axis-label">
          midpoint — not evidence
        </text>

        {/* The cost of the tool itself, on the same axis. */}
        <rect
          x={x(cost.low)}
          y={74}
          width={Math.max(x(cost.high) - x(cost.low), 2)}
          height={20}
          fill="var(--baseline)"
        />
        <text x={x(cost.low)} y={108} className="mkt__axis-label">
          modelled cost of this tool
        </text>
      </svg>

      <dl className="mkt__band">
        <div className="mkt__band-item">
          <dt className="u-micro">Value band / year</dt>
          <dd className="mkt__band-value mkt__band-value--band">{formatBand(value)}</dd>
        </div>
        <div className="mkt__band-item">
          <dt className="u-micro">Cost band / year</dt>
          <dd className="mkt__band-value mkt__band-value--cost">{formatBand(cost)}</dd>
        </div>
        <div className="mkt__band-item">
          <dt className="u-micro">Band span</dt>
          <dd className="mkt__band-value">
            {spread === null ? 'unbounded' : `${spread.toFixed(2)} orders of magnitude`}
          </dd>
        </div>
        <div className="mkt__band-item">
          <dt className="u-micro">Reading</dt>
          <dd className={`mkt__verdict mkt__verdict--${unresolved ? 'unresolved' : 'narrow'}`}>
            {unresolved ? 'Unresolved' : 'Narrow enough to quote'}
          </dd>
        </div>
      </dl>

      <p className="mkt__note">
        {unresolved
          ? 'Two of the four inputs have never been observed on a real deployment, so the value band spans more than an order of magnitude and overlaps the cost of the tool. The model does not support a confident return figure in either direction, and the midpoint is not evidence. Two retrospective numbers from one real team would narrow it more than any further modelling.'
          : 'The band is narrow enough to quote with its assumptions attached.'}
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
    <div className="mkt__ladder" role="list" aria-label="Evidence ladder">
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
                {state === 'current' ? 'we are here' : state === 'ahead' ? 'not reached' : 'passed'}
              </span>
            </div>
            <p className="mkt__rung-def">{level.definition}</p>
            {state === 'current' && (
              <p className="mkt__rung-requires">
                <span className="u-micro">Required to claim this</span> {level.requires}
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
          <span className="u-micro">Market position · strategy hypothesis, pre-validation</span>
          <h1 className="mkt__title">AI applications need a release gate</h1>
        </div>
        <div className="mkt__plate mkt__plate--right">
          <span className="u-micro">Rubric target</span>
          <span className="mkt__score">
            {totalTargetScore()}
            <span className="mkt__score-denom">/{MAX_TOTAL}</span>
          </span>
          <span className="u-micro">evidence-backed, pre-validation</span>
        </div>
      </header>

      {/* The disclosure is a block, not a footnote. It is the first thing read. */}
      <section className="mkt__disclosure" aria-label="Zero-traction disclosure">
        <span className="mkt__tag mkt__tag--none">No data</span>
        <p className="mkt__disclosure-text">{ZERO_TRACTION_DISCLOSURE}</p>
      </section>

      {/* ---------------------------------------------------------- traction -- */}
      <section className="mkt__block mkt__block--traction" aria-label="Traction">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">Traction</h2>
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
          A dash means <em>not measured</em>, not <em>measured zero</em>. The two are different
          claims and only the first is true here.
        </p>
      </section>

      {/* ------------------------------------------------------------ ladder -- */}
      <section className="mkt__block mkt__block--ladder" aria-label="Proof ladder">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">Progress is a state, not a count</h2>
          <SourceTag id="target" />
        </div>
        <p className="mkt__lede">
          A shipped product is not a pilot, and a pilot is not a customer. The honest way to report
          progress before revenue is to say which rung of the ladder we are standing on — currently{' '}
          <strong>{current.label}</strong>, with <strong>{remaining} rungs</strong> between here and
          a first paying customer.
        </p>
        <ProofLadder />
      </section>

      {/* --------------------------------------------------------------- ROI -- */}
      <section className="mkt__block mkt__block--roi" aria-label="Return on investment">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">Return, as a band</h2>
          <SourceTag id="assumption" />
        </div>
        <p className="mkt__lede">
          Annual value is one avoided bad release, multiplied by how many happen and how many this
          tool would catch. Four inputs, and every one of them is a guess, so the answer is an
          interval: {formatBand(value)} per year. It is adjustable below, so a reader can substitute
          their own numbers rather than argue with ours.
        </p>
        <RoiStrip />
        <table className="record mkt__assumptions">
          <caption className="visually-hidden">ROI model inputs, with their basis</caption>
          <thead>
            <tr>
              <th scope="col">Input</th>
              <th scope="col">Low</th>
              <th scope="col">High</th>
              <th scope="col">Basis</th>
              <th scope="col">Replaced by</th>
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
                  <span className={`mkt__basis mkt__basis--${input.basis}`}>{input.basis}</span>
                </td>
                <td className="mkt__input-detail">{input.would_measure_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* ----------------------------------------------------------- pricing -- */}
      <section className="mkt__block" aria-label="Pricing hypothesis">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">Pricing hypothesis</h2>
          <SourceTag id="target" />
        </div>
        <p className="mkt__lede">
          No price on this surface has been quoted to anyone, let alone paid. These are the shapes
          we intend to test, with the reasoning attached so the reasoning can be attacked instead of
          the number.
        </p>
        <div className="mkt__prices">
          {PRICING.map((rung) => (
            <article className="mkt__price" key={rung.id}>
              <div className="mkt__price-head">
                <h3 className="mkt__price-name">{rung.name}</h3>
                <span className={`mkt__basis mkt__basis--${rung.basis}`}>{rung.basis}</span>
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
          <span className="u-micro">Falsifier</span> {PRICING_FALSIFIER}
        </p>
      </section>

      {/* --------------------------------------------------------------- GTM -- */}
      <section className="mkt__block" aria-label="Go to market">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">Ninety days, from zero</h2>
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
                <dt className="u-micro">Goal</dt>
                <dd>{stage.goal}</dd>
                <dt className="u-micro">Artifact</dt>
                <dd>{stage.artifact}</dd>
                <dt className="u-micro">Kill condition</dt>
                <dd className="mkt__kill">{stage.kill}</dd>
              </dl>
            </li>
          ))}
        </ol>
      </section>

      {/* -------------------------------------------------------------- moat -- */}
      <section className="mkt__block" aria-label="Moat">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">The moat, layer by layer</h2>
          <SourceTag id="assumption" />
        </div>
        <p className="mkt__lede">
          Claiming a single moat would be the easy version. The layers are genuinely different, and
          one of them is not a defence at all.
        </p>
        <div className="mkt__moat">
          {MOAT.map((layer) => (
            <article className="mkt__moat-layer" key={layer.id}>
              <div className="mkt__moat-head">
                <h3 className="mkt__moat-name">{layer.name}</h3>
                <span className={`mkt__strength mkt__strength--${layer.strength}`}>
                  {layer.strength}
                </span>
              </div>
              <p className="mkt__moat-claim">{layer.claim}</p>
              <p className="mkt__note">{layer.why}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------- criteria -- */}
      <section className="mkt__block" aria-label="Competition scorecard">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">Five criteria, 20 points each</h2>
          <SourceTag id="assumption" />
        </div>
        <p className="mkt__lede">
          A team scoring itself is the weakest evidence in the submission. These are our own marks,
          with the confidence we hold them at, and the exact actions that would move each one.
        </p>

        <div className="mkt__attribution">
          <span className="u-micro">Run attributed to this panel</span>
          <span className="mkt__run">
            {measured?.runLabel ?? 'none — the panel is rendering on its own'}
          </span>
          {measured && measured.confirmed !== undefined && (
            <span className="mkt__run-figures">
              {measured.confirmed ? 'confirmed regression' : 'no verdict recorded'}
              {measured.meanDifference !== undefined &&
                ` · mean ${measured.meanDifference.toFixed(3)}`}
              {measured.ciLow !== undefined &&
                measured.ciHigh !== undefined &&
                ` · 95% CI ${measured.ciLow.toFixed(3)} to ${measured.ciHigh.toFixed(3)}`}
              {measured.threshold !== undefined &&
                ` · threshold ${measured.threshold.toFixed(3)}`}
            </span>
          )}
        </div>

        <table className="record mkt__criteria">
          <caption className="visually-hidden">Self-assessed competition scorecard</caption>
          <thead>
            <tr>
              <th scope="col">Criterion</th>
              <th scope="col">Self</th>
              <th scope="col">Max</th>
              <th scope="col">Confidence</th>
              <th scope="col">Target</th>
              <th scope="col">Gap</th>
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
                      {criterion.confidence}
                    </span>
                  </td>
                  <td className="u-num">{criterion.target}</td>
                  <td className={`u-num mkt__gap${gap >= 5 ? ' mkt__gap--wide' : ''}`}>{gap}</td>
                </tr>
              )
            })}
            <tr>
              <td className="u-label">Total</td>
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
                  <span className="u-micro">Evidence</span> {criterion.evidence}
                </p>
                <p className="mkt__note">
                  <span className="u-micro">Gap</span> {criterion.gap}
                </p>
                <ol className="mkt__action-list">
                  {criterion.actions.map((action) => (
                    <li className="mkt__action" key={action.id}>
                      <span className="mkt__action-id">{action.id}</span>
                      <div className="mkt__action-body">
                        <p>{action.what}</p>
                        <p className="mkt__action-verify">
                          <span className="u-micro">Verified by</span> {action.verification}
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
            <span className="u-label">Demonstrated, on our own corpus</span>
            <ul className="mkt__list">
              {POSITION.demonstrated.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="mkt__ledger mkt__ledger--missing">
            <span className="u-label">Missing, entirely</span>
            <ul className="mkt__list">
              {POSITION.missing.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- workspace -- */}
      <section className="mkt__block" aria-label="Investigation workspace">
        <div className="mkt__block-head">
          <h2 className="mkt__block-title">The product, on the run beside it</h2>
          <SourceTag id="fixture" />
        </div>
        <p className="mkt__lede">
          This block is where the host page mounts its own investigation surface. It is injected
          rather than imported, so this feature can sit beside a workspace without depending on it.
        </p>
        {renderWorkspace ? (
          renderWorkspace()
        ) : (
          <p className="mkt__placeholder">
            No workspace injected. Pass <code>renderWorkspace</code> to mount one here.
          </p>
        )}
      </section>

      <footer className="mkt__footer">
        <p className="mkt__footer-text">
          {POSITION.headline} Every commercial figure on this surface is an assumption, a target, or
          a range; every product figure is labelled as measured or as fixture. If a later revision
          reports traction, the number must name the counterparty, or it does not go in.
        </p>
      </footer>
    </div>
  )
}
