/**
 * The Chinese label layer.
 *
 * EvalPilot's console is read by Chinese-speaking competition judges, so every
 * user-visible string on the surface is Chinese. The *data* is not: run statuses,
 * categories, severities, step kinds, decision verdicts and metric ids all stay
 * the English union members `docs/INTERFACES.md` fixes, because they are the
 * API's own vocabulary and the console's whole claim is that it shows what the
 * backend reported.
 *
 * So this module is the one place those two facts meet. A component renders
 * `label(run.status)` and gets 执行中; the href, the request body, the filter
 * comparison and the `data-*` attribute all still carry `executing`. Nothing
 * here mutates a value — every function takes the English member and returns a
 * Chinese string, and `labelOf` falls back to the raw value rather than to a
 * guess, so an enum member this build has not seen renders as itself instead of
 * as a confident mistranslation.
 *
 * The typed `Record<Enum, string>` tables below are exhaustive by construction:
 * adding a member to `RunStatus` breaks the build here rather than shipping a
 * blank chip.
 */

import type {
  EventType,
  EvidenceKind,
  RunStatus,
  Severity,
  TestCaseCategory,
  TestCaseStatus,
} from '../api/types'
import type {
  CounterfactualVerdict,
  DecisionVerdict,
  InvestigationStatus,
  InvestigationStepKind,
  InvestigationStepStatus,
  RiskLevel,
} from '../api/investigation'

// ------------------------------------------------------------ run lifecycle --

const RUN_STATUS: Record<RunStatus, string> = {
  queued: '排队中',
  planning: '规划中',
  executing: '执行中',
  evaluating: '评估中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export function runStatusLabel(status: RunStatus): string {
  return RUN_STATUS[status]
}

// ------------------------------------------------------------ investigation --

const INVESTIGATION_STATUS: Record<InvestigationStatus, string> = {
  queued: '排队中',
  planning: '规划中',
  investigating: '调查中',
  replaying: '反事实重放中',
  deciding: '裁决中',
  completed: '已完成',
  failed: '失败',
}

export function investigationStatusLabel(status: InvestigationStatus): string {
  return INVESTIGATION_STATUS[status]
}

const RISK_LEVEL: Record<RiskLevel, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '严重',
}

/** 严重 / 高风险 / 中风险 / 低风险. */
export function riskLevelLabel(level: RiskLevel): string {
  return RISK_LEVEL[level]
}

const RISK_LEVEL_SHORT: Record<RiskLevel, string> = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '严重',
}

/** The same level in two characters, for a chip in a fixed-width column. */
export function riskLevelShortLabel(level: RiskLevel): string {
  return RISK_LEVEL_SHORT[level]
}

const DECISION_VERDICT: Record<DecisionVerdict, string> = {
  allow: '允许发布',
  review: '人工复核',
  block: '阻断发布',
}

export function decisionVerdictLabel(verdict: DecisionVerdict): string {
  return DECISION_VERDICT[verdict]
}

const STEP_STATUS: Record<InvestigationStepStatus, string> = {
  pending: '待执行',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
}

export function stepStatusLabel(status: InvestigationStepStatus): string {
  return STEP_STATUS[status]
}

const STEP_KIND: Record<InvestigationStepKind, string> = {
  risk: '风险假设',
  memory: '事故召回',
  probe: '探针',
  counterfactual: '反事实重放',
  tool: '工具调用',
  observation: '观察',
  decision: '发布裁决',
}

export function stepKindLabel(kind: InvestigationStepKind): string {
  return STEP_KIND[kind]
}

const COUNTERFACTUAL_VERDICT: Record<CounterfactualVerdict, string> = {
  root_cause: '根因',
  partial: '部分根因',
  no_effect: '无影响',
  inconclusive: '无法判定',
}

export function counterfactualVerdictLabel(verdict: CounterfactualVerdict): string {
  return COUNTERFACTUAL_VERDICT[verdict]
}

// ------------------------------------------------------------------ records --

const CASE_STATUS: Record<TestCaseStatus, string> = {
  pending: '待执行',
  running: '执行中',
  passed: '通过',
  failed: '未通过',
  error: '错误',
}

export function caseStatusLabel(status: TestCaseStatus): string {
  return CASE_STATUS[status]
}

const CASE_CATEGORY: Record<TestCaseCategory, string> = {
  normal: '常规',
  boundary: '边界',
  adversarial: '对抗',
  regression: '回归',
}

export function caseCategoryLabel(category: TestCaseCategory): string {
  return CASE_CATEGORY[category]
}

const SEVERITY: Record<Severity, string> = {
  info: '提示',
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '严重',
}

/**
 * Severity and risk level share a vocabulary on purpose: 严重/高风险/中风险/低风险
 * is what the brief asks the console to print for both, and printing two
 * different words for the same judgement would read as two different judgements.
 */
export function severityLabel(severity: Severity): string {
  return SEVERITY[severity]
}

const EVIDENCE_KIND: Record<EvidenceKind, string> = {
  text: '文本',
  screenshot: '截图',
  log: '日志',
  citation: '引用',
  trace: '轨迹',
  metric: '指标',
}

export function evidenceKindLabel(kind: EvidenceKind): string {
  return EVIDENCE_KIND[kind]
}

const EVENT_TYPE: Record<EventType, string> = {
  'run.started': '运行开始',
  'task.created': '任务创建',
  'task.started': '任务开始',
  'evidence.created': '证据写入',
  'task.completed': '任务完成',
  'finding.created': '发现生成',
  'run.completed': '运行完成',
  'run.failed': '运行失败',
}

export function eventTypeLabel(type: EventType): string {
  return EVENT_TYPE[type]
}

// -------------------------------------------------------------------- market --

const FACT_BASIS: Record<string, string> = {
  assumption: '假设',
  target: '目标',
  measured: '实测',
  fixture: '夹具数据',
  none: '无数据',
  hypothesis: '假设',
  quoted: '已报价',
  paid: '已付费',
}

/**
 * The source tags the market surface prints beside a block, keyed by the
 * `SourceLabel.id` the model resolves them by — not by their English `text`,
 * which is prose and lives in the model.
 */
export const SOURCE_TAG_LABEL: Record<string, string> = {
  measured: '实测',
  fixture: '夹具数据',
  target: '目标',
  assumption: '假设',
  none: '无数据',
}

/** `assumption` → 假设. Used for ROI inputs, pricing rungs and source tags. */
export function factBasisLabel(basis: string): string {
  return FACT_BASIS[basis] ?? basis
}

const CONFIDENCE: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
  'very-low': '极低',
}

export function confidenceLabel(level: string): string {
  return CONFIDENCE[level] ?? level
}

const MOAT_STRENGTH: Record<string, string> = {
  none: '无',
  weak: '弱',
  building: '构建中',
  strong: '强',
}

export function moatStrengthLabel(strength: string): string {
  return MOAT_STRENGTH[strength] ?? strength
}

// ------------------------------------------------------------------- metrics --

/**
 * Metric ids the console knows how to render, keyed by the backend's own id.
 *
 * A live report supplies only the id; an offline fixture supplies a label too.
 * Where one is present it wins, so the fixture and the service describe the
 * same measurement the same way.
 */
const METRIC_LABEL: Record<string, string> = {
  task_success: '任务成功率',
  citation_coverage: '引用覆盖率',
  correct_refusal: '正确拒答率',
  format_compliance: '格式合规率',
  groundedness: '有据性（评分表）',
  latency_p50: '延迟 P50',
  answer_tokens: '回答长度（均值）',
}

export function metricLabel(id: string, fallback?: string): string {
  return METRIC_LABEL[id] ?? fallback ?? id
}

/** The five deterministic checks, by id. */
const CHECK_LABEL: Record<string, string> = {
  citation_coverage: '引用覆盖率',
  required_facts: '必需事实覆盖',
  refusal_correctness: '拒答正确性',
  format_compliance: '格式合规',
  length_budget: '长度预算',
}

export function checkLabel(id: string, fallback?: string): string {
  return CHECK_LABEL[id] ?? fallback ?? id
}

// -------------------------------------------------------------- provenance ----

/**
 * How the numbers on screen got there.
 *
 * `PROVENANCE` is not an enum the backend defines — it is the console's own
 * statement about its data source, and it is translated here so the header, the
 * console notice and the workspace's source plate cannot drift apart.
 */
export const PROVENANCE = {
  probing: '正在探测后端…',
  live: '实时后端',
  offline: '离线演示 — 内置夹具数据',
  fixtures: '夹具数据',
  backend: '后端服务',
  liveValues: (baseUrl: string): string => `${baseUrl} · 数值来自正在运行的服务`,
  offlineValues: '以下所有数字均为预置夹具数据，并非真实评估结果',
  pressStart: '点击下方「启动演示运行」探测后端',
  fixturesManual: '已手动切换到夹具数据 — 内置语料，并非真实运行。',
  backendUnseedable: '后端有响应，但无法解析出演示运行；改为展示夹具数据。',
  liveUnavailable: (reason: string): string =>
    `无法进行实时运行：${reason}。改为展示夹具数据。`,
  liveUnavailableNoReason: '无法进行实时运行。改为展示夹具数据。',
  stillRunning: (status: RunStatus, seconds: number): string =>
    `运行已持续 ${seconds} 秒，状态仍为「${runStatusLabel(status)}」；以下为目前已记录的内容。`,
  mockInvestigation: '本次调查中的每个数字都是预置模拟数据，不是真实调查。',
  mockInvestigationLive: (baseUrl: string): string => `${baseUrl} · 调查在服务上运行`,
} as const

// ---------------------------------------------------------- enum value sets ---

/**
 * The filter options, in the order the console prints them.
 *
 * These are the English union members, not labels: they are what the filter
 * state holds and compares against, and each one is rendered through the
 * `*Label` function above. Keeping them here rather than in the component is
 * what makes "the filter shows every status the contract defines" a fact about
 * the contract instead of about one view.
 */
export const RUN_STATUS_ORDER: readonly RunStatus[] = [
  'queued',
  'planning',
  'executing',
  'evaluating',
  'completed',
  'failed',
  'cancelled',
]

export const CASE_STATUS_ORDER: readonly TestCaseStatus[] = [
  'pending',
  'running',
  'passed',
  'failed',
  'error',
]

export const CASE_CATEGORY_ORDER: readonly TestCaseCategory[] = [
  'normal',
  'boundary',
  'adversarial',
  'regression',
]

export const EVIDENCE_KIND_ORDER: readonly EvidenceKind[] = [
  'text',
  'trace',
  'citation',
  'screenshot',
  'log',
  'metric',
]
