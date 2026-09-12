import type { JSX } from 'react'
import type { Scenario } from '../fixtures/scenarios'

interface Props {
  scenario: Scenario
  /** Case currently open in the evidence drawer, if any. */
  selectedCaseNumber: number | null
  onSelectCase: (caseId: string) => void
}

/* Geometry. One viewBox, aspect preserved; a squeezed chart is a lying chart. */
const W = 1000
const H = 300
const PAD_L = 62
const PAD_R = 22
const PAD_T = 48
const PAD_B = 46
const PLOT_W = W - PAD_L - PAD_R
const PLOT_H = H - PAD_T - PAD_B

/** The pre-printed tolerance band, in score units, either side of the baseline. */
const TOLERANCE = 0.05

const xAt = (index: number, count: number): number =>
  count <= 1 ? PAD_L : PAD_L + ((index - 1) / (count - 1)) * PLOT_W

const yAt = (value: number): number => PAD_T + (1 - value) * PLOT_H

/**
 * The first case where the candidate leaves the band and stays out — the
 * departure the tag callout points at. One case outside is a wobble; two in a
 * row in the same direction is a departure.
 */
function findDeparture(outcomes: Scenario['outcomes']): number | null {
  for (let i = 0; i < outcomes.length; i += 1) {
    const here = outcomes[i]!
    const next = outcomes[i + 1]
    const outside = (o: (typeof outcomes)[number]): boolean =>
      Math.abs(o.candidateVerdict.total - o.baselineVerdict.total) > TOLERANCE
    if (!outside(here)) continue
    if (!next || !outside(next)) continue
    const sameSign =
      Math.sign(here.candidateVerdict.total - here.baselineVerdict.total) ===
      Math.sign(next.candidateVerdict.total - next.baselineVerdict.total)
    if (sameSign) return i
  }
  return null
}

function pathFor(values: readonly number[], count: number): string {
  return values
    .map((value, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i + 1, count)} ${yAt(value)}`)
    .join(' ')
}

/**
 * The candidate trace, split where it leaves the tolerance band.
 *
 * This is the thesis of the whole surface made literal: the trace is drawn in a
 * muted ink while it is inside tolerance and in full vermilion where it departs.
 * The colour is not a label attached to the version, it is the measurement.
 */
function departureSegments(
  candidate: readonly number[],
  bandTopValue: number,
  bandBottomValue: number,
  count: number,
): string[] {
  const outside = (value: number): boolean => value > bandTopValue || value < bandBottomValue
  const segments: string[] = []
  for (let i = 1; i < candidate.length; i += 1) {
    const a = candidate[i - 1]!
    const b = candidate[i]!
    if (outside(a) || outside(b)) {
      segments.push(`M ${xAt(i, count)} ${yAt(a)} L ${xAt(i + 1, count)} ${yAt(b)}`)
    }
  }
  return segments
}

export function Tape({ scenario, selectedCaseNumber, onSelectCase }: Props): JSX.Element {
  const outcomes = scenario.outcomes
  const count = outcomes.length

  const baselineValues = outcomes.map((o) => o.baselineVerdict.total)
  const candidateValues = outcomes.map((o) => o.candidateVerdict.total)
  const baselineMean = baselineValues.reduce((a, b) => a + b, 0) / Math.max(count, 1)

  const departure = findDeparture(outcomes)
  const departureIndex = departure === null ? null : departure + 1

  const bandTopValue = Math.min(baselineMean + TOLERANCE, 1)
  const bandBottomValue = Math.max(baselineMean - TOLERANCE, 0)
  const bandTop = yAt(bandTopValue)
  const bandBottom = yAt(bandBottomValue)
  const departures = departureSegments(candidateValues, bandTopValue, bandBottomValue, count)

  const isRegression = scenario.verdict === 'regression'

  return (
    <section className="tape" aria-label="各匹配场景上基线版本与候选版本的得分轨迹">
      <div className="tape__chassis">
        <div className="tape__chassis-group">
          <div className="tape__plate">
            <span className="tape__plate-label">记录</span>
            <span className="tape__plate-value">
              {scenario.baselineVersion} vs {scenario.candidateVersion}
            </span>
          </div>
          <span className="tape__divider" aria-hidden="true" />
          <div className="tape__plate">
            <span className="tape__plate-label">通道 A</span>
            <span className="tape__plate-value">{scenario.baselineVersion} · 基线</span>
          </div>
          <div className="tape__plate">
            <span className="tape__plate-label">通道 B</span>
            <span className="tape__plate-value">{scenario.candidateVersion} · 候选</span>
          </div>
          <span className="tape__divider" aria-hidden="true" />
          <div className="tape__plate">
            <span className="tape__plate-label">时基</span>
            <span className="tape__plate-value">{count} 个匹配场景 · 3 次重复采样</span>
          </div>
        </div>

        <div className="tape__chassis-group">
          <span className="tape__plate-label">走纸速度</span>
          <span className="tape__plate-value">{count} 个场景 / 次运行</span>
        </div>
      </div>

      <div className="tape__paper">
        <span className="tape__watermark">
          {isRegression
            ? '容差带 — 基线 ± 0.05'
            : '容差带 ± 0.05 · 无偏离'}
        </span>

        <div className="tape__scroll">
          <svg
            className="tape__svg"
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label={`${count} 个匹配场景的得分轨迹。${scenario.verdictText}。${scenario.summary}`}
          >
            <title>基线版本与候选版本的得分轨迹</title>
            <desc>{scenario.summary}</desc>

            <defs>
              <clipPath id="plot-clip">
                <rect x={PAD_L} y={PAD_T} width={PLOT_W} height={PLOT_H} />
              </clipPath>
            </defs>

            {/* --- pre-printed graticule ------------------------------------ */}
            {[0, 0.25, 0.5, 0.75, 1].map((value) => (
              <line
                key={`h${value}`}
                x1={PAD_L}
                x2={W - PAD_R}
                y1={yAt(value)}
                y2={yAt(value)}
                stroke={value === 0 || value === 1 ? 'var(--plot-grid)' : 'var(--plot-grid-faint)'}
                strokeWidth="1"
              />
            ))}
            {outcomes.map((_, i) =>
              i % 2 === 0 ? (
                <line
                  key={`v${i}`}
                  x1={xAt(i + 1, count)}
                  x2={xAt(i + 1, count)}
                  y1={PAD_T}
                  y2={PAD_T + PLOT_H}
                  stroke="var(--plot-grid-faint)"
                  strokeWidth="1"
                  strokeDasharray={i % 6 === 0 ? undefined : '2 3'}
                />
              ) : null,
            )}

            {/* --- y axis labels -------------------------------------------- */}
            {[1, 0.75, 0.5, 0.25, 0].map((value) => (
              <text
                key={`ylabel${value}`}
                x={PAD_L - 8}
                y={yAt(value) + 4}
                textAnchor="end"
                className="tape__axis-label"
              >
                {value.toFixed(2)}
              </text>
            ))}
            <text x={PAD_L - 8} y={PAD_T - 8} textAnchor="end" className="tape__axis-label">
              得分
            </text>

            {/* --- the tolerance band --------------------------------------- */}
            <rect
              x={PAD_L}
              y={bandTop}
              width={PLOT_W}
              height={Math.max(bandBottom - bandTop, 1)}
              fill="var(--plot-band)"
              stroke="var(--plot-band-edge)"
              strokeWidth="1"
            />

            {/* --- traces --------------------------------------------------- */}
            <g clipPath="url(#plot-clip)">
              <path
                d={pathFor(baselineValues, count)}
                fill="none"
                stroke="var(--plot-baseline)"
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {/* Muted while inside tolerance... */}
              <path
                d={pathFor(candidateValues, count)}
                fill="none"
                stroke="var(--plot-candidate-dim)"
                strokeWidth="1.5"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {/* ...full ink where it departs. */}
              {departures.map((segment, index) => (
                <path
                  key={index}
                  d={segment}
                  fill="none"
                  stroke="var(--plot-candidate)"
                  strokeWidth="3"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              ))}
            </g>

            {/* --- case markers. A departure is a filled marker; a case inside
                    tolerance is an open one. --------------------------------- */}
            {outcomes.map((outcome, i) => {
              const x = xAt(i + 1, count)
              const selected = selectedCaseNumber === outcome.spec.n
              const outside =
                candidateValues[i]! > bandTopValue || candidateValues[i]! < bandBottomValue
              return (
                <g key={outcome.spec.n}>
                  <circle
                    cx={x}
                    cy={yAt(baselineValues[i]!)}
                    r={selected ? 3.5 : 2}
                    fill="var(--plot-baseline)"
                  />
                  <circle
                    cx={x}
                    cy={yAt(candidateValues[i]!)}
                    r={selected ? 4 : 2.5}
                    fill={outside ? 'var(--plot-candidate)' : 'var(--plot-empty)'}
                    stroke={outside ? 'var(--plot-candidate)' : 'var(--plot-baseline-dim)'}
                    strokeWidth={outside ? 2 : 1}
                  />
                </g>
              )
            })}

            {/* --- the departure, tagged. The callout sits in the margin above
                    the plot and a leader line drops to the trace, so it never
                    collides with the data it is pointing at. -------------- */}
            {departureIndex !== null && (
              <g>
                <line
                  x1={xAt(departureIndex, count)}
                  x2={xAt(departureIndex, count)}
                  y1={PAD_T - 22}
                  y2={PAD_T + PLOT_H}
                  stroke="var(--plot-candidate)"
                  strokeWidth="1"
                  strokeDasharray="4 3"
                />
                <text
                  x={xAt(departureIndex, count) + 5}
                  y={PAD_T - 26}
                  className="tape__tag"
                >
                  {`T-${String(departureIndex).padStart(2, '0')} 偏离`}
                </text>
              </g>
            )}
          </svg>
        </div>

        {/* --- the tick margin. A character lattice that doubles as the
                directly-keyed case index (raised from the teletext hand). -- */}
        <div className="tape__ticks" role="group" aria-label="场景索引">
          {outcomes.map((outcome) => (
            <button
              key={outcome.spec.n}
              type="button"
              className={`tick${outcome.regression ? ' tick--down' : ''}${
                selectedCaseNumber === outcome.spec.n ? ' tick--on' : ''
              }`}
              aria-pressed={selectedCaseNumber === outcome.spec.n}
              onClick={() => onSelectCase(caseIdFor(scenario, outcome.spec.n))}
              title={`场景 ${outcome.spec.n} — ${outcome.spec.title}`}
            >
              {String(outcome.spec.n).padStart(2, '0')}
            </button>
          ))}
        </div>
      </div>

      <div className="legend">
        <span className="legend__item">
          <span className="legend__swatch legend__swatch--baseline" aria-hidden="true" />
          <span className="u-micro">{scenario.baselineVersion} 基线</span>
        </span>
        <span className="legend__item">
          <span className="legend__swatch legend__swatch--candidate" aria-hidden="true" />
          <span className="u-micro">{scenario.candidateVersion} 候选 —— 偏离处用实色绘制</span>
        </span>
        <span className="legend__item">
          <span className="legend__swatch legend__swatch--muted" aria-hidden="true" />
          <span className="u-micro">在容差带内</span>
        </span>
        <span className="legend__item">
          <span className="legend__swatch legend__swatch--band" aria-hidden="true" />
          <span className="u-micro">容差带 ±0.05</span>
        </span>
        <span className="legend__item">
          <span className="u-micro">实心标记 = 稳定回归</span>
        </span>
        <span className="legend__item" style={{ marginLeft: 'auto' }}>
          <span className="u-micro">
            {departureIndex === null
              ? '容差带外无偏离'
              : `首次偏离出现在场景 ${String(departureIndex).padStart(2, '0')}`}
          </span>
        </span>
      </div>
    </section>
  )
}

/**
 * A case's id, resolved through the outcome the tape already holds. The tape
 * addresses cases by number because that is what the chart plots.
 */
function caseIdFor(scenario: Scenario, n: number): string {
  return scenario.outcomes.find((outcome) => outcome.spec.n === n)?.caseId ?? ''
}
