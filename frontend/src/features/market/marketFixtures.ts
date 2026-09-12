/**
 * The market fixture — the market surface's data.
 *
 * This file is the *only* place commercial numbers are allowed to be typed.
 * A component that hard-codes one has made a claim the model cannot check, and
 * `marketFixtures.test.ts` fails on the numbers it can see.
 *
 * Everything here is either zero (traction), a hypothesis (pricing), or a
 * published position (the criteria). Nothing here is a result.
 */

import type { SourceLabel, TractionKey } from './marketModel'
import { SOURCE_LABELS } from './marketModel'

// ------------------------------------------------------------------ criteria --

/**
 * The five official competition criteria, verbatim from the brief.
 *
 * `max` is 20 for every criterion and the total is therefore 100. The type
 * pins it: a sixth criterion, or a different weight, would be a different
 * competition, and this surface must not quietly re-weight one.
 */
export interface Criterion {
  id: 'technical' | 'market' | 'innovation' | 'llm' | 'track'
  /** The criterion as published. Do not paraphrase. */
  official: string
  /** The question a judge is actually answering. */
  question: string
  max: 20
  /** The team's own score. Not a judge's. */
  selfScore: number
  /** How much the team trusts its own score. */
  confidence: 'high' | 'medium' | 'low' | 'very-low'
  /** What backs the score today. */
  evidence: string
  /** The distance to the target, in the terms of the actions below. */
  gap: string
  target: number
  /** The exact actions that would close the gap. */
  actions: readonly ImprovementAction[]
}

export interface ImprovementAction {
  id: string
  what: string
  /** How anyone can check it was done. */
  verification: string
}

export const CRITERIA: readonly Criterion[] = [
  {
    id: 'technical',
    official: '技术可行性 — Technical feasibility',
    question: '以现有的人力与时间，这件事能被做出来并演示出来吗？',
    max: 20,
    selfScore: 16,
    confidence: 'high',
    evidence:
      'MVP 可构建且各套件全绿：生产构建干净，前端 150 个测试通过，后端 115 个通过，并记录了一次 31/31 的端到端检查。场景被刻意收窄，演示在后端缺席时会回退到一份有明确标注的离线语料，而不是直接卡死。',
    gap:
      '提案中有三项断言没有工件支撑；并且在 `main` 的全新检出上，`typecheck` 脚本同样是坏的。没有任何第三方跑过冷启动检查清单。',
    target: 18,
    actions: [
      {
        id: 'T1',
        what: '修好 `typecheck` 脚本 —— 它把 `--noEmit false` 和 `allowImportingTsExtensions` 配在一起，根本不可能通过。不要用「在 `-b` 下兑现 `--noEmit`」的方式去修：那会生成同名的 `.js` 文件，Vite 随后会解析到生成的 `vite.config.js` 而不是真正的那个。',
        verification:
          '`npm --prefix frontend run typecheck` 退出码为 0，`npm run build` 仍为 0，且 `git status` 在 `src/` 下看不到多余的 `.js`。',
      },
      {
        id: 'T2',
        what: '要么删掉「跨重复运行可复现」这一断言，要么把同一次对比跑两遍并留下两份报告。',
        verification: '两份报告工件，可逐字节比较。',
      },
      {
        id: 'T3',
        what: '用一次已提交的测量来支撑后端 README 中的统计功效断言，或者把它删掉。',
        verification: '一条已提交的命令及其输出，或者一行被删除的内容。',
      },
      {
        id: 'T4',
        what: '在一台并非开发机的机器上运行冷启动检查清单。',
        verification: '运行记录，失败项保留。',
      },
    ],
  },
  {
    id: 'market',
    official: '市场可行性 — Market feasibility',
    question: '是否有人买单、有预算、有反复出现的需求，以及触达他们的路径？',
    max: 20,
    selfScore: 8,
    // The score is low and the confidence in it is the opposite of low: we are
    // certain there is no evidence, because there is none to be uncertain about.
    confidence: 'very-low',
    evidence:
      '一个可用的产品加一套结构化的战略假设：明确的目标客户画像、买单人、触发事件、替代方案分析、定价假设、可调节的 ROI 模型、GTM 节奏，以及一份带终止条件的 90 天计划。其中没有任何一项经过外部检验。',
    gap:
      '没有客户沟通、没有设计伙伴、没有试点、没有付费客户、没有收入、没有报价、没有任何一种经过验证的数字。没有任何工程动作能提高这一项的得分。',
    target: 13,
    actions: [
      {
        id: 'M1',
        what: '完成十次目标客户画像沟通，每次都问清楚：触发事件在过去六个月内是否出现过。',
        verification: '十份书面记录，每次沟通一份，并明确回答触发事件问题。',
      },
      {
        id: 'M2',
        what: '从这些沟通中提取两个事后数字：发布出现回归的频率，以及一次糟糕发布的代价。',
        verification: '两个真实数值替换掉 ROI 模型中的两个假设。',
      },
      {
        id: 'M3',
        what: '确认或证伪「预算科目」这一假设。',
        verification: '来自真实沟通的一个具名预算科目，或一份书面结论「不存在这样的科目」。',
      },
      {
        id: 'M4',
        what: '签下一位已经触发过该事件的设计伙伴。',
        verification: '一份写明应用与语料的已签署协议，即便价格为零。',
      },
      {
        id: 'M5',
        what: '在该伙伴已经发布过的那次发布上重跑本工具，并把结论与实际发生的情况对比。',
        verification: '一份事后诊断工件 —— 无论结论是否一致。结论不一致就是一个产品缺陷，也是一条发现。',
      },
    ],
  },
  {
    id: 'innovation',
    official: '综合创新性 — Comprehensive innovation',
    question: '核心想法是否并不显而易见，且它是产品的实质而非一层包装？',
    max: 20,
    selfScore: 14,
    confidence: 'medium',
    evidence:
      '以匹配场景做因果对比，且难度受控；把失败归因到具体干预的反事实重放；召回事故指纹；以及允许返回「无法判定」的聚合结论。每条发现都带有证据 ID 和判断理由。',
    gap:
      '机制本身是标准统计学，因此创新点在于设计纪律而不是新技术。反事实重放从未对着真实缺陷检验过，记忆资产里也没有真实历史。',
    target: 17,
    actions: [
      {
        id: 'I1',
        what: '对一次真实已发布的版本做事后诊断，并发布结果 —— 无论结论是否一致。',
        verification: '一份把工具结论与已知结果对照的工件。',
      },
      {
        id: 'I2',
        what: '在同一个候选版本和同一份语料上，与一个「聚合分数差值」类工具做一次正面对比并公开结果。',
        verification: '两个结论并排呈现，包括它们不一致的情形。',
      },
      {
        id: 'I3',
        what: '把创新性断言里的「因果」这个过度承载的词去掉，重述一遍，看看它是否还站得住。',
        verification: '提案中重写后的断言；如果它垮掉了，说明原提案一直在靠这个词撑着。',
      },
      {
        id: 'I4',
        what: '把引擎的统计功效上限作为一项明确的产品属性披露出来，并给出最小场景数的推导。',
        verification: '一个写明的最小 N 值及其推导过程。',
      },
    ],
  },
  {
    id: 'llm',
    official: 'AI大模型融合 — AI large-model integration',
    question: '模型是否在承担关键职责、其角色是否明确，以及缺席时是否能诚实降级？',
    max: 20,
    selfScore: 15,
    confidence: 'medium',
    evidence:
      '一个冻结的供应商接缝，使用 OpenAI 兼容端点与经 schema 校验的 JSON；三个具名角色 —— 规划器、裁判、报告叙述；每次生成的步骤都结构化记录 `source`、`model` 与调用 ID；显式的确定性回退，并记录原因；运行时端点从不返回密钥；不展示思维链。',
    gap:
      '没有一次对真实模型的成功调用记录，没有对着人类验证过的裁判，没有第二家供应商，也没有实测的 token 成本。仓库中所有形似大模型输出的内容都是夹具数据。',
    target: 18,
    actions: [
      {
        id: 'L1',
        what: '对真实端点记录一次实时运行，并提交产出的报告工件。',
        verification: '一份已提交的报告，其生成的步骤带有模型 ID 和调用 ID。',
      },
      {
        id: 'L2',
        what: '记录一次刻意制造的失败 —— 无效密钥或强制超时 —— 展示带原因的确定性回退。',
        verification: '工件中能看到回退原因。',
      },
      {
        id: 'L3',
        what: '显式处理「裁判与确定性检查不一致」：展示两种读数，而不是把它们合并。',
        verification: '一个两者不一致的夹具，渲染为两行。',
      },
      {
        id: 'L4',
        what: '测量一次完整对比的 token 用量与成本，并把该数字写进定价假设。',
        verification: '一个实测数字替换掉一个假设。',
      },
      {
        id: 'L5',
        what: '对第二家 OpenAI 兼容供应商运行同一次对比。',
        verification: '来自两家供应商、面向同一契约的两份工件。',
      },
    ],
  },
  {
    id: 'track',
    official: '赛道维度评估 — Track-dimension assessment',
    question: '该智能体是否能端到端自主执行，并留下可验证的交付物？',
    max: 20,
    selfScore: 14,
    confidence: 'medium',
    evidence:
      '调查闭环按「接单 → 规划 → 探针 → 反事实重放 → 裁决 → 报告」运行，不需要逐步的人工输入，展示的是结构化动作而不是推理过程。每条发现都关联到证据。交付物是一份可下载的报告。演示的聚合结论是一次实测并已确认的回归 —— 平均得分下降 0.173，95% 置信区间完全落在 −0.05 阈值之下。',
    gap:
      '要求的演示视频尚不存在。冷启动检查清单还没有由非作者运行过。自主性是在夹具上演示的，实时模型这条路径尚未跑通。',
    target: 17,
    actions: [
      {
        id: 'K1',
        what: '录制两到三分钟的演示视频并发布，确认在隐私窗口中无需登录即可播放。',
        verification: '该 URL，在登出状态下打开。',
      },
      {
        id: 'K2',
        what: '在一台不是开发机的机器上运行完整的冷启动检查清单。',
        verification: '运行记录，包含失败项。',
      },
      {
        id: 'K3',
        what: '在录制中捕捉实时模型运行，让运行时徽标显示为真实模式。',
        verification: '录制画面中可见的徽标。',
      },
      {
        id: 'K4',
        what: '在提案中说明聚合结论所要求的最小场景数。',
        verification: '一句话，附推导。',
      },
      {
        id: 'K5',
        what: '在一个干净的后端上验证两条演示者深链接。',
        verification: '两张截图。',
      },
    ],
  },
]

export const MAX_TOTAL = 100

export function totalSelfScore(): number {
  return CRITERIA.reduce((sum, criterion) => sum + criterion.selfScore, 0)
}

export function totalTargetScore(): number {
  return CRITERIA.reduce((sum, criterion) => sum + criterion.target, 0)
}

// ------------------------------------------------------------------ position --

export interface MarketPosition {
  /**
   * The single sentence the surface is built around. Kept here rather than in
   * the component so it can be asserted by a test.
   */
  headline: string
  /** What the demo proves, and what it does not. */
  demonstrated: readonly string[]
  /** The parts of a market pitch that do not exist yet. */
  missing: readonly string[]
}

export const POSITION: MarketPosition = {
  headline:
    '比赛结果不等于市场结果：机制已经实现，并在我们自己预置的语料上完成演示，而本仓库之外还没有人见过它。',
  demonstrated: [
    '一台可用的对比引擎，端到端跑通，覆盖 26 个场景的语料。',
    '在该语料上确认了一次聚合回归，配有配对置信区间，且对照场景未变动。',
    '与证据关联的发现，以及一份可下载的报告。',
    '一个诚实、可复现、并自行标注数据来源的演示。',
  ],
  missing: [
    '任何外部用户。',
    '任何设计伙伴或试点。',
    '任何付费客户或收入。',
    '任何报价或经过验证的 ROI 数字。',
    '一支公开的演示视频。',
  ],
}

// --------------------------------------------------------------- disclosure --

/**
 * The `SourceLabel` objects the surface renders beside each block, resolved by
 * id so a label can never be invented at a call site.
 */
export function sourceLabel(id: SourceLabel['id']): SourceLabel {
  const found = SOURCE_LABELS.find((label) => label.id === id)
  if (!found) throw new Error(`unknown source label: ${id}`)
  return found
}

/** The counts that must render as dashes, in the order they appear. */
export const TRACTION_ROWS: ReadonlyArray<{ key: TractionKey; label: string }> = [
  { key: 'paying_customers', label: '付费客户' },
  { key: 'active_pilots', label: '进行中的试点' },
  { key: 'design_partners', label: '设计伙伴' },
  { key: 'external_users', label: '外部用户' },
  { key: 'external_conversations', label: '外部沟通' },
  { key: 'revenue_ytd_cny', label: '年初至今收入' },
]
