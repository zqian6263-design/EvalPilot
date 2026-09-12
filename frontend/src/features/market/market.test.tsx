import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { MarketImpactPanel } from './MarketImpactPanel'
import {
  MOAT,
  PRICING,
  PROOF_LADDER,
  ROI_INPUT_BY_ID,
  TRACTION,
  ZERO_TRACTION_DISCLOSURE,
  bandPosition,
  currentProofLevel,
  formatBand,
  formatCount,
  roiBandSpread,
  roiCostBand,
  roiIsUnresolved,
  roiValueBand,
  rungsToRevenue,
} from './marketModel'
import {
  CRITERIA,
  MAX_TOTAL,
  TRACTION_ROWS,
  totalSelfScore,
  totalTargetScore,
} from './marketFixtures'

/**
 * `cleanup` is called explicitly rather than relied on from the global setup.
 * The setup file clears `document.body` between tests, which unmounts nothing:
 * React keeps its tree, so a previous test's markers stay in the DOM and a
 * `getByText` finds two.
 */
afterEach(cleanup)

/**
 * The model derivations.
 *
 * These are the tests that matter most. A market panel fails by being
 * *plausible* — a number that looks like a result, printed without the label
 * that would tell a reader it is a guess. The assertions below are written
 * against the properties that make the surface honest, not against the
 * strings it happens to print.
 *
 * Every model and fixture value on this surface is Chinese prose about the
 * market, so the reference expectations above (`MOAT`, `PRICING`,
 * `ZERO_TRACTION_DISCLOSURE`, `TRACTION_ROWS`) stay the source of truth: the
 * rendering assertions below compare against those values, not against
 * literals retyped into the test.
 */
describe('market model — the derivations', () => {
  it('occupies exactly one rung of the evidence ladder', () => {
    const marked = PROOF_LADDER.filter((level) => level.current)
    expect(marked).toHaveLength(1)
    expect(marked[0]!.id).toBe('internal_validation')
  })

  it('places us strictly below a pilot, and several rungs from revenue', () => {
    const index = (id: string): number => PROOF_LADDER.findIndex((level) => level.id === id)
    expect(index('internal_validation')).toBeLessThan(index('design_partner'))
    expect(index('design_partner')).toBeLessThan(index('pilot'))
    expect(rungsToRevenue()).toBeGreaterThan(0)
  })

  it('reports every traction count as unmeasured rather than zero', () => {
    for (const row of TRACTION_ROWS) {
      expect(TRACTION[row.key].value).toBeNull()
    }
    // The distinction the whole surface rests on: a dash is not a zero.
    expect(formatCount(TRACTION.paying_customers)).toBe('—')
    expect(formatCount({ value: 0, note: '' })).toBe('0')
  })

  it('states the zero-traction disclosure in words, not in the absence of a number', () => {
    expect(ZERO_TRACTION_DISCLOSURE).toMatch(/没有任何外部客户/)
    expect(ZERO_TRACTION_DISCLOSURE).toMatch(/尚未验证/)
  })

  it('bands the ROI rather than pointing it', () => {
    const band = roiValueBand()
    expect(band.low).toBeGreaterThan(0)
    expect(band.high).toBeGreaterThan(band.low)
  })

  it('admits the band is too wide to resolve a verdict', () => {
    const spread = roiBandSpread()
    expect(spread).not.toBeNull()
    // Four assumptions multiplied together cannot produce a tight interval.
    expect(spread!).toBeGreaterThan(1)
    expect(roiIsUnresolved()).toBe(true)
  })

  it('prices the tool against the low release estimate, not the flattering one', () => {
    const cost = roiCostBand()
    const cheapestSeats = ROI_INPUT_BY_ID.get('seats')!
    expect(cost.low).toBe(
      cheapestSeats.low * ROI_INPUT_BY_ID.get('seat_price')!.low +
        ROI_INPUT_BY_ID.get('releases_per_year')!.low *
          ROI_INPUT_BY_ID.get('cost_per_comparison')!.low,
    )
  })

  it('marks every ROI input as an assumption or a target — never as measured', () => {
    for (const input of ROI_INPUT_BY_ID.values()) {
      expect(input.basis).not.toBe('measured')
      // Every assumption has to name what would replace it, or it is just a guess.
      expect(input.would_measure_by.length).toBeGreaterThan(0)
    }
  })

  it('quotes no price and marks every pricing rung as a hypothesis', () => {
    expect(PRICING.length).toBeGreaterThan(0)
    for (const rung of PRICING) {
      expect(rung.basis).toBe('hypothesis')
      expect(rung.high).toBeGreaterThan(rung.low!)
    }
  })

  it('names a layer of the moat that is not a defence at all', () => {
    // A moat section with three strong layers is marketing. Ours has a weak one.
    expect(MOAT.some((layer) => layer.strength === 'weak')).toBe(true)
    expect(MOAT.every((layer) => layer.why.length > 0)).toBe(true)
  })

  it('maps a value onto a band on a log axis, clamped at both ends', () => {
    const band = { low: 100, high: 10_000 }
    expect(bandPosition(100, band)).toBe(0)
    expect(bandPosition(10_000, band)).toBe(1)
    expect(bandPosition(1_000, band)).toBeCloseTo(0.5, 6)
    expect(bandPosition(1, band)).toBe(0)
    expect(bandPosition(1e9, band)).toBe(1)
  })

  it('formats a band compactly enough for an axis and honestly enough for prose', () => {
    expect(formatBand({ low: 18_000, high: 7_280_000 })).toBe('¥18k – ¥7.3M')
  })
})

describe('market fixtures — the scorecard', () => {
  it('carries the five official criteria at 20 points each', () => {
    expect(CRITERIA).toHaveLength(5)
    for (const criterion of CRITERIA) {
      expect(criterion.max).toBe(20)
    }
    expect(MAX_TOTAL).toBe(100)
  })

  it('uses the official criterion names, not paraphrases', () => {
    const official = CRITERIA.map((criterion) => criterion.official)
    expect(official).toEqual([
      '技术可行性 — Technical feasibility',
      '市场可行性 — Market feasibility',
      '综合创新性 — Comprehensive innovation',
      'AI大模型融合 — AI large-model integration',
      '赛道维度评估 — Track-dimension assessment',
    ])
  })

  it('scores the market far below the product, which is the honest shape', () => {
    const byId = new Map(CRITERIA.map((criterion) => [criterion.id, criterion]))
    const market = byId.get('market')!
    for (const id of ['technical', 'innovation', 'llm', 'track'] as const) {
      expect(market.selfScore).toBeLessThan(byId.get(id)!.selfScore)
    }
    // The lowest confidence in the table, on the lowest score.
    expect(market.confidence).toBe('very-low')
  })

  it('never scores above the maximum, and never targets a regression', () => {
    for (const criterion of CRITERIA) {
      expect(criterion.selfScore).toBeLessThanOrEqual(criterion.max)
      expect(criterion.selfScore).toBeGreaterThanOrEqual(0)
      expect(criterion.target).toBeGreaterThanOrEqual(criterion.selfScore)
    }
    expect(totalSelfScore()).toBeLessThanOrEqual(MAX_TOTAL)
    expect(totalTargetScore()).toBeGreaterThan(totalSelfScore())
  })

  it('gives every criterion a verifiable action, not an aspiration', () => {
    for (const criterion of CRITERIA) {
      expect(criterion.actions.length).toBeGreaterThan(0)
      for (const action of criterion.actions) {
        expect(action.what.length).toBeGreaterThan(0)
        // An action nobody can check is not a plan, it is a wish.
        expect(action.verification.length).toBeGreaterThan(0)
      }
    }
  })
})

/**
 * The rendering.
 *
 * A data test cannot catch the failure mode this surface exists to prevent:
 * a correct number shown without the word that says what kind of number it is.
 *
 * The region names and headings below are the Chinese the panel prints; the
 * expectations that reference a model value (`currentProofLevel().label`,
 * `formatBand(...)`, `TRACTION_ROWS.length`) read it from the model, so this
 * file never restates a number or a sentence the surface already owns.
 */
describe('MarketImpactPanel — honesty on screen', () => {
  it('renders with no props at all', () => {
    render(<MarketImpactPanel />)
    expect(
      screen.getByRole('heading', { name: /AI 应用需要一个发布门禁/ }),
    ).toBeInTheDocument()
  })

  it('leads with the zero-traction disclosure', () => {
    render(<MarketImpactPanel />)
    expect(screen.getByText(ZERO_TRACTION_DISCLOSURE)).toBeInTheDocument()
  })

  it('renders every traction count as a dash with its reason', () => {
    render(<MarketImpactPanel />)
    const traction = screen.getByRole('region', { name: /^牵引力$/ })
    // Six labelled counts, six dashes.
    expect(within(traction).getAllByText('—')).toHaveLength(TRACTION_ROWS.length)
    for (const row of TRACTION_ROWS) {
      expect(within(traction).getByText(row.label)).toBeInTheDocument()
    }
    expect(
      within(traction).getByText(TRACTION.paying_customers.note),
    ).toBeInTheDocument()
  })

  it('marks the current rung and labels the rungs ahead as not reached', () => {
    render(<MarketImpactPanel />)
    const ladder = screen.getByRole('list', { name: /证据阶梯/ })
    expect(within(ladder).getAllByText(/我们在这里/)).toHaveLength(1)
    expect(within(ladder).getAllByText(/尚未达到/).length).toBeGreaterThan(0)
    expect(within(ladder).getAllByText(currentProofLevel().label).length).toBeGreaterThan(0)
  })

  it('shows the ROI as a band and refuses to resolve it', () => {
    render(<MarketImpactPanel />)
    const roi = screen.getByRole('region', { name: /投资回报/ })
    expect(within(roi).getByText(formatBand(roiValueBand()))).toBeInTheDocument()
    // The band's width is stated as a number, not as a vibe.
    expect(
      within(roi).getByText(`${roiBandSpread()!.toFixed(2)} 个数量级`),
    ).toBeInTheDocument()
    expect(within(roi).getAllByText(/^无法判定$/).length).toBeGreaterThan(0)
    // Every model input is on screen with its basis, so a reader can adjust it.
    for (const input of ROI_INPUT_BY_ID.values()) {
      expect(within(roi).getByText(input.label)).toBeInTheDocument()
    }
  })

  it('carries the ROI chart as text as well, so nothing is chart-only', () => {
    render(<MarketImpactPanel />)
    const chart = screen.getByRole('img', { name: /年化价值/ })
    expect(chart).toBeInTheDocument()
    expect(within(chart).getByText(/年化价值与年化建模成本的对比/)).toBeInTheDocument()
  })

  it('labels pricing as a hypothesis and prints the falsifier', () => {
    render(<MarketImpactPanel />)
    const pricing = screen.getByRole('region', { name: /定价假设/ })
    expect(within(pricing).getAllByText('假设')).toHaveLength(PRICING.length)
    expect(within(pricing).getByText(/如果在十次有明确意向的沟通之后/)).toBeInTheDocument()
  })

  it('gives each of the five criteria its score, its gap and its actions', () => {
    render(<MarketImpactPanel />)
    const scorecard = screen.getByRole('region', { name: /赛道评分表/ })
    for (const criterion of CRITERIA) {
      expect(within(scorecard).getAllByText(criterion.official).length).toBeGreaterThan(0)
      for (const action of criterion.actions) {
        expect(within(scorecard).getAllByText(action.id).length).toBeGreaterThan(0)
      }
    }
    expect(within(scorecard).getByText(String(totalSelfScore()))).toBeInTheDocument()
  })

  it('says it has no run rather than borrowing a report’s authority', () => {
    render(<MarketImpactPanel />)
    expect(screen.getByText(/无 —— 本面板独立渲染/)).toBeInTheDocument()
  })

  it('attributes the report figures when it is mounted beside a run', () => {
    render(
      <MarketImpactPanel
        measured={{
          runLabel: 'v1.4.2 vs v1.5.0-rc1',
          confirmed: true,
          meanDifference: -0.173,
          ciLow: -0.288,
          ciHigh: -0.077,
          threshold: -0.05,
        }}
      />,
    )
    // The run label is a version pair, not prose, and stays as the run reports it.
    expect(screen.getByText('v1.4.2 vs v1.5.0-rc1')).toBeInTheDocument()
    // One text node, so the reading is not assembled out of separate spans.
    expect(
      screen.getByText(/已确认回归 · 均值 -0\.173 · 95% 置信区间 -0\.288 至 -0\.077 · 阈值 -0\.050/),
    ).toBeInTheDocument()
  })

  it('states plainly when a run has no verdict yet', () => {
    render(<MarketImpactPanel measured={{ runLabel: 'v1.0 vs v1.1', confirmed: false }} />)
    expect(screen.getByText(/无裁决记录/)).toBeInTheDocument()
  })

  it('explains itself when no workspace is injected', () => {
    render(<MarketImpactPanel />)
    expect(screen.getByText(/未注入工作区/)).toBeInTheDocument()
  })

  it('mounts an injected workspace rather than importing one', () => {
    render(
      <MarketImpactPanel
        renderWorkspace={() => <div data-testid="host-workspace">host surface</div>}
      />,
    )
    expect(screen.getByTestId('host-workspace')).toBeInTheDocument()
    expect(screen.queryByText(/未注入工作区/)).not.toBeInTheDocument()
  })

  it('keeps the market claim off the product’s evidence', () => {
    render(<MarketImpactPanel />)
    // The headline sentence a judge should be able to quote back at us.
    expect(screen.getByText(/比赛结果不等于市场结果/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /护城河/ })).toBeInTheDocument()
    expect(screen.getAllByText('假设').length).toBeGreaterThan(0)
  })
})
