/**
 * The market surface's model.
 *
 * One rule governs everything here, and it is the same rule the fixtures live
 * by (`src/fixtures/seed.ts`): nothing in this file may call `Math.random` or
 * `Date.now`, and every displayed number must be *derived* from the data in
 * `marketFixtures.ts` rather than typed into a component. A market panel is
 * the easiest place in a product to make a number up; deriving it is what
 * stops that happening by accident.
 *
 * `PROOF_LADDER` is the spine. It is a ladder of evidence — a shipped product
 * is not a pilot, a pilot is not a customer — and the panel's honest job is to
 * point at the rung we are actually standing on. Everything else on the
 * surface (the headline counts, the disclosure strip) is read off that rung
 * rather than asserted next to it.
 *
 * No React, no DOM, no transport: this module is deliberately pure so the
 * tests can pin the derivations without a renderer.
 */

// ---------------------------------------------------------------- evidence --

/** The rungs, weakest first. Order is load-bearing: `PROOF_LADDER` is indexed by it. */
export type ProofLevelId =
  | 'idea'
  | 'prototype'
  | 'internal_validation'
  | 'design_partner'
  | 'pilot'
  | 'paid_pilot'
  | 'paying_customers'

export interface ProofLevel {
  id: ProofLevelId
  /** As printed on the ladder. */
  label: string
  /** One line a judge can hold us to. */
  definition: string
  /** What has to be true for this rung to be claimed. */
  requires: string
  /** True only for the rung we are standing on. Exactly one entry may set this. */
  current: boolean
}

/**
 * The rungs, in climbing order.
 *
 * `internal_validation` is the rung this build occupies: the comparison engine
 * runs end to end and reports a confirmed regression across the 26-scenario
 * corpus the project ships with — but that corpus is the team's own, built by
 * the team, and every one of the eight regressed scenarios was put there
 * deliberately. That is real validation of the *product* and zero validation
 * of the *market*. Marking it anything higher would be the specific dishonesty
 * this surface exists to prevent.
 */
export const PROOF_LADDER: readonly ProofLevel[] = [
  {
    id: 'idea',
    label: '构想',
    definition: '一份关于“谁有这个问题”的书面假设。',
    requires: '一份文档。',
    current: false,
  },
  {
    id: 'prototype',
    label: '原型',
    definition: '能在合成数据上跑起来，受众是团队自己。',
    requires: '一个不会崩溃的演示。',
    current: false,
  },
  {
    id: 'internal_validation',
    label: '内部验证',
    definition:
      '闭环端到端跑通，并在一份由团队自己构建、且预埋了自身已知缺陷的语料上完成核对。',
    requires: '一次可复现的测量 —— 以及坦承这份语料出自编写该工具的同一个人之手的诚实。',
    current: true,
  },
  {
    id: 'design_partner',
    label: '设计伙伴',
    definition: '有一个外部团队同意在他们自己的系统、自己的数据上运行它。',
    requires: '一个有名字的合作方和一份已签署的协议，即便没有资金往来。',
    current: false,
  },
  {
    id: 'pilot',
    label: '试点',
    definition: '该团队已把它用在一个真实发布上，并依据它的结论采取了行动。',
    requires: '一个真的有人做出的发布决策，且依据的是本工具的建议。',
    current: false,
  },
  {
    id: 'paid_pilot',
    label: '付费',
    definition: '有一个团队为它付过费，或已为第二次合作划拨预算。',
    requires: '一张已付款的发票。',
    current: false,
  },
  {
    id: 'paying_customers',
    label: '多个付费客户',
    definition: '两个或以上付费客户，其续约决策已定或待定。',
    requires: '可重复的收入。',
    current: false,
  },
]

export function currentProofLevel(): ProofLevel {
  const found = PROOF_LADDER.find((level) => level.current)
  // A ladder with no current rung would silently render the whole surface as
  // "not started"; fail loudly instead, because that is a code error, not data.
  if (!found) throw new Error('PROOF_LADDER has no current rung')
  return found
}

/** How many rungs remain between us and a paying-customer claim. */
export function rungsToRevenue(): number {
  const currentIndex = PROOF_LADDER.findIndex((level) => level.current)
  const revenueIndex = PROOF_LADDER.findIndex((level) => level.id === 'paid_pilot')
  return revenueIndex - currentIndex
}

// ----------------------------------------------------------------- traction --

/**
 * The commercial numbers, all zero.
 *
 * These are typed as literals rather than computed, because the only correct
 * change to this object is a real signed counterparty — at which point the
 * value changes *and* `current` moves up a rung above. The panel renders these
 * as dashes, not as `0`: "we have none" and "we measured zero" are different
 * claims, and only the first is true.
 */
export interface Counted {
  /** Null means "not measured", which is distinct from a measured zero. */
  value: number | null
  /** What the count would mean if it were not zero. */
  note: string
}

export interface Traction {
  paying_customers: Counted
  active_pilots: Counted
  external_users: Counted
  design_partners: Counted
  external_conversations: Counted
  revenue_ytd_cny: Counted
}

export type TractionKey = keyof Traction

export const TRACTION: Traction = {
  paying_customers: { value: null, note: '从未有任何人为此产品付费。' },
  active_pilots: { value: null, note: '没有任何外部团队在他们自己的系统上运行过它。' },
  external_users: { value: null, note: '本仓库之外没有人使用过这个控制台。' },
  design_partners: { value: null, note: '不存在任何协议、意向书或口头共识。' },
  external_conversations: {
    value: null,
    note: '并非政策上为零 —— 只是尚未开展。',
  },
  revenue_ytd_cny: { value: null, note: '没有任何收入，任何币种，任何时间。' },
}

/** The single sentence the surface must never stop printing. */
export const ZERO_TRACTION_DISCLOSURE =
  '目前没有任何外部客户、试点或用户。这仍然是一份尚未验证的战略：商业数字都是假设，ROI 是一个区间，此处任何内容都不代表客户牵引力。'

// --------------------------------------------------------------------- ROI --

/**
 * An ROI reading is always a *band*, never a point.
 *
 * Every input is an assumption with a low and a high, so the output has to be
 * a range. Collapsing it to a single seductive number is the classic way a
 * pre-validation market slide lies; the type deliberately makes that awkward.
 */
export interface RoiInput {
  id: string
  label: string
  /** Rendered small, under the label. */
  detail: string
  low: number
  high: number
  unit: string
  /**
   * Why this input is trustworthy or not. `assumption` is the default and the
   * honest state for every input in this build.
   */
  basis: 'assumption' | 'target' | 'measured'
  /** What would replace this assumption with a measurement. */
  would_measure_by: string
}

export interface RoiBand {
  low: number
  high: number
}

/** A model input that scales the whole result, kept separate from the counts. */
const ROI_INPUTS: readonly RoiInput[] = [
  {
    id: 'releases_per_year',
    label: '每年发布次数',
    detail: '可能造成回归的版本变更：模型、提示词、检索、工具。',
    low: 24,
    high: 104,
    unit: '/年',
    basis: 'assumption',
    would_measure_by: '统计一个设计伙伴的发布日志。',
  },
  {
    id: 'p_bad_release',
    label: '其中造成回归的比例',
    detail: '这些发布中真正让质量变差的比例。',
    low: 0.05,
    high: 0.2,
    unit: '',
    basis: 'assumption',
    would_measure_by: '对一个真实团队最近 20 次发布做一次复盘。',
  },
  {
    id: 'p_detected',
    label: '及时拦下的比例',
    detail:
      '本工具能在上线前拦下的真实回归比例。其上限由引擎在客户语料上的统计功效决定 —— 而不是由愿望决定。',
    low: 0.3,
    high: 0.7,
    unit: '',
    basis: 'assumption',
    would_measure_by: '用已知有问题的发布回放本工具，统计命中数。',
  },
  {
    id: 'cost_of_bad_release',
    label: '一次糟糕发布的代价',
    detail:
      '排查与紧急修复工时、支持升级、被推迟的发布本身，以及任何合规成本。通常只有前两项能被量化。',
    low: 50_000,
    high: 500_000,
    unit: ' 元',
    basis: 'assumption',
    would_measure_by: '一次带数字的事后复盘。',
  },
  {
    id: 'seats',
    label: '席位数',
    detail: '推进者加复核者，并设下限，以免单席位订单卡住。',
    low: 3,
    high: 10,
    unit: '',
    basis: 'target',
    would_measure_by: '第一份合同中的席位数。',
  },
  {
    id: 'seat_price',
    label: '席位单价',
    detail: '按年、按席位。',
    low: 8_000,
    high: 25_000,
    unit: ' 元/年',
    basis: 'target',
    would_measure_by: '一次报价，然后是一次实际付款。',
  },
  {
    id: 'cost_per_comparison',
    label: '单次对比成本',
    detail: '主要来自运行本身消耗的模型推理。',
    low: 20,
    high: 200,
    unit: ' 元',
    basis: 'assumption',
    would_measure_by: '开启 token 计量跑一次实时运行。',
  },
]

export const ROI_INPUT_BY_ID: ReadonlyMap<string, RoiInput> = new Map(
  ROI_INPUTS.map((input) => [input.id, input]),
)

/** The narrative band: what one avoided bad release is worth per year. */
export function roiValueBand(): RoiBand {
  const input = (id: string): RoiInput => {
    const found = ROI_INPUT_BY_ID.get(id)
    if (!found) throw new Error(`unknown ROI input: ${id}`)
    return found
  }
  const value = (multiplier: number): number =>
    input('releases_per_year')[multiplier === 0 ? 'low' : 'high'] *
    input('p_bad_release')[multiplier === 0 ? 'low' : 'high'] *
    input('p_detected')[multiplier === 0 ? 'low' : 'high'] *
    input('cost_of_bad_release')[multiplier === 0 ? 'low' : 'high']
  return { low: value(0), high: value(1) }
}

/**
 * The cost of the tool itself, as a band.
 *
 * `comparisonsPerYear` defaults to the *low* release estimate: buying a
 * release gate does not mean every release is gated on day one, and pricing
 * the tool against the most optimistic usage would flatter the comparison.
 */
export function roiCostBand(comparisonsPerYear?: number): RoiBand {
  const seats = ROI_INPUT_BY_ID.get('seats')!
  const seatPrice = ROI_INPUT_BY_ID.get('seat_price')!
  const perComparison = ROI_INPUT_BY_ID.get('cost_per_comparison')!
  const releases = ROI_INPUT_BY_ID.get('releases_per_year')!
  const comparisons = comparisonsPerYear ?? releases.low
  return {
    low: seats.low * seatPrice.low + comparisons * perComparison.low,
    high: seats.high * seatPrice.high + comparisons * perComparison.high,
  }
}

/**
 * How many orders of magnitude the value band spans.
 *
 * This is the honesty metric of the whole model and it is rendered on the
 * surface: a band that spans two orders of magnitude cannot support a
 * confident ROI claim, and a reader who is told the span will not be fooled by
 * the midpoint. A `null` low (a zero anywhere in the multiplicands) has no
 * meaningful ratio.
 */
export function roiBandSpread(): number | null {
  const band = roiValueBand()
  if (band.low <= 0) return null
  return Math.log10(band.high / band.low)
}

/** True when the band is too wide for a point estimate to mean anything. */
export function roiIsUnresolved(spread = roiBandSpread()): boolean {
  return spread !== null && spread > 1
}

// ----------------------------------------------------------------- pricing --

export interface PriceRung {
  id: string
  name: string
  /** The number as it would appear on a quote — a range, or a single figure. */
  shape: string
  low: number | null
  high: number | null
  unit: string
  /** What the customer gets. */
  includes: readonly string[]
  /** Why the shape is what it is. */
  rationale: string
  /**
   * How this price has been arrived at: `hypothesis` for every rung in this
   * build, since none has been quoted to anyone.
   */
  basis: 'hypothesis' | 'quoted' | 'paid'
}

export const PRICING: readonly PriceRung[] = [
  {
    id: 'pilot',
    name: '试点合作',
    shape: '¥30k–80k，固定费用',
    low: 30_000,
    high: 80_000,
    unit: ' 单次合作',
    includes: [
      '一个应用、一份语料，针对客户自己的端点完成配置。',
      '在该语料上做一次基线／候选对比。',
      '一份客户可以拿去自己内部评审的发布门禁报告。',
    ],
    rationale:
      '把触发事件转化成采购订单，而不必先要一个平台级的决策。它同时也是第一次合作真正成本 —— 集成工作 —— 的资金来源。',
    basis: 'hypothesis',
  },
  {
    id: 'subscription',
    name: '团队订阅',
    shape: '¥8k–25k 每席位每年',
    low: 8_000,
    high: 25_000,
    unit: ' / 席位 / 年',
    includes: [
      '推进者和复核者都需要访问权，因此设 3–5 席位的下限。',
      '运行历史，以及累积的回归记忆。',
      '反事实重放引擎。',
    ],
    rationale:
      '订阅是锚点。纯按用量计费会让价格随客户的变更频率浮动，恰好惩罚了产品希望鼓励的行为。',
    basis: 'hypothesis',
  },
  {
    id: 'usage',
    name: '对比用量',
    shape: '¥20–200 每次执行的对比',
    low: 20,
    high: 200,
    unit: ' / 次对比',
    includes: [
      '按「匹配场景 × 重复次数 × 版本数」计量。',
      '定价低于运行本身消耗的推理成本。',
    ],
    rationale:
      '这是针对失控运行的护栏，而不是利润中心。一旦定价高于推理成本，工具就会被读成「使用税」。',
    basis: 'hypothesis',
  },
]

/**
 * What would falsify the pricing shape — stated on the surface, because a
 * price with no falsification criterion is a wish.
 */
export const PRICING_FALSIFIER =
  '如果在十次有明确意向的沟通之后，仍没有一位推进者能说出这笔钱该从哪条预算里出，那么错的是定价形态，而不是价格。先重新推导形态，再动数字。'

// ---------------------------------------------------------------------- GTM --

export interface GtmStage {
  n: number
  name: string
  window: string
  goal: string
  artifact: string
  /** The condition under which we stop and rethink rather than push on. */
  kill: string
}

export const GTM_PLAN: readonly GtmStage[] = [
  {
    n: 1,
    name: '证伪用户画像',
    window: '第 0–30 天',
    goal: '与十支正在交付知识库或客服助手的团队各谈一次。',
    artifact: '十份书面记录，外加一份统计：其中多少家近期触发了该事件。',
    kill: '十家里不到四家在过去六个月内出现过被阻断、被推迟或被回滚的发布。触发假设不成立；先重写它，再谈其他。',
  },
  {
    n: 2,
    name: '一份真实语料',
    window: '第 31–60 天',
    goal: '把工具配置到一位设计伙伴的助手和他们自己的文档上。',
    artifact: '对他们已经发布过的一次发布做事后诊断 —— 无论结论是否一致。',
    kill: '到第 45 天仍未签约伙伴，或集成超过五个工程师日。两者都说明当前形态的产品还卖不出去。',
  },
  {
    n: 3,
    name: '为一次真实发布把门',
    window: '第 61–90 天',
    goal: '把它作为一次即将到来的变更的发布门禁，并让团队依据结论采取行动。',
    artifact: '一个真的有人做出的发布决策，以及它替代掉的工时。',
    kill: '建议被生成后又被无视。无论报告写了什么，产品都还没有承重能力。',
  },
]

/** The one thing this plan is trying to buy. */
export const GTM_SUCCESS_DEFINITION =
  '成功不是「工具能跑」。而是：一个有名字的团队在真实数据上运行了它，依据它的结论对一次真实发布采取了行动，并且能用一句话说清它替代了什么。'

// --------------------------------------------------------------------- moat --

export interface MoatLayer {
  id: string
  name: string
  /** What the layer actually is. */
  claim: string
  /** How strong it is today: `none` is a real answer and is used here. */
  strength: 'none' | 'weak' | 'building' | 'strong'
  /** Why — specifically, why a competitor could or could not copy it. */
  why: string
}

/**
 * The moat, stated as three layers with three different strengths.
 *
 * Reporting a single "our moat is X" claim would be the easy version. The
 * layers are genuinely different: the mechanism is not defensible at all, the
 * memory is defensible but empty, and only the discipline is defensible today
 * — and discipline is a team property, not a product feature.
 */
export const MOAT: readonly MoatLayer[] = [
  {
    id: 'mechanism',
    name: '对比机制',
    claim:
      '匹配场景、重复采样、自助法不确定性 —— 让真实回归与「测试集变难了」可分。',
    strength: 'weak',
    why: '这是教科书级别的统计方法。开源评估框架早已提供基础原语，任何一支称职的团队都能在一个冲刺内拼出这套设计。它是产品的实质，但它不是壁垒。',
  },
  {
    id: 'memory',
    name: '回归记忆',
    claim:
      '每一次运行都在累积事故指纹和反事实重放，让下一位工程师在排查之前就知道是哪个开关导致了哪种失败。',
    strength: 'building',
    why: '这是唯一会复利的一层，也是随时间推移越来越难被复制的一层。目前它只在预置事故上得到演示，因此它在真实历史记录上的价值仍属假设而非事实。',
  },
  {
    id: 'discipline',
    name: '证据纪律',
    claim:
      '每条发现都带有证据 ID 和判断理由；聚合结论允许返回「无法判定」；模型不得覆盖测量结果。',
    strength: 'building',
    why: '做评分面板的竞争者很难照搬，因为照搬就意味着承认自己分不清。但它是团队属性，其次才是产品特性；一个有同样纪律的竞争者拥有同样的护城河。',
  },
]

// ------------------------------------------------------------------ sources --

/**
 * Honesty labels. Every number on the surface carries one of these, and
 * `measured` is defined narrowly on purpose — a fixture the team authored is
 * not a measurement of the market, however precisely it is computed.
 */
export interface SourceLabel {
  id: 'measured' | 'fixture' | 'target' | 'assumption' | 'none'
  text: string
  /** Rendered with the label so the word is never decorative. */
  meaning: string
}

export const SOURCE_LABELS: readonly SourceLabel[] = [
  {
    id: 'measured',
    text: '实测',
    meaning:
      '由本仓库计算得出，运行其测试即可复现。说的是产品 —— 从不说市场。',
  },
  {
    id: 'fixture',
    text: '夹具数据',
    meaning: '由团队编写的预置数据，其中包含它要检出的那些缺陷。',
  },
  {
    id: 'target',
    text: '目标',
    meaning: '团队打算达到的数字。不是观测结果。',
  },
  {
    id: 'assumption',
    text: '假设',
    meaning: '一种尚无任何证据支持或反对的信念。此处每一个商业数字都是这样。',
  },
  {
    id: 'none',
    text: '无数据',
    meaning: '未测量。与「测量结果为零」不同，渲染为一个短横线。',
  },
]

// ---------------------------------------------------------------- formatting --

/** A count, or a dash. Null is never rendered as `0`. */
export function formatCount(counted: Counted): string {
  return counted.value === null ? '—' : String(counted.value)
}

/** Compact money for a chart axis: 18 000 → `18k`, 7 300 000 → `7.3M`. */
export function formatCompact(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${round1(value / 1_000_000)}M`
  if (abs >= 1_000) return `${round1(value / 1_000)}k`
  return String(Math.round(value))
}

function round1(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

/** A band as it appears in prose: `¥18k – ¥7.3M`. */
export function formatBand(band: RoiBand, prefix = '¥'): string {
  return `${prefix}${formatCompact(band.low)} – ${prefix}${formatCompact(band.high)}`
}

/**
 * The log10 position of a value inside a band, 0 at the low end and 1 at the
 * high end. Log scale because the bands here span orders of magnitude; a
 * linear axis would draw every interesting reading as a dot at the left edge.
 */
export function bandPosition(value: number, band: RoiBand): number {
  const spread = roiSpreadOf(band)
  if (spread === 0) return 0
  return clamp01((Math.log10(value) - Math.log10(band.low)) / spread)
}

function roiSpreadOf(band: RoiBand): number {
  if (band.low <= 0 || band.high <= 0) return 0
  return Math.log10(band.high) - Math.log10(band.low)
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}
