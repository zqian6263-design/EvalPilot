import { useMemo, useState } from 'react'
import type { TestCaseCategory, TestCaseStatus } from '../api/types'
import type { CaseOutcome, Scenario } from '../fixtures/scenarios'
import { formatScore, formatSignedScore } from '../lib/format'
import {
  CASE_CATEGORY_ORDER,
  CASE_STATUS_ORDER,
  caseCategoryLabel,
  caseStatusLabel,
} from '../i18n/labels'

interface Props {
  scenario: Scenario
  selectedCaseId: string | null
  onSelectCase: (caseId: string) => void
}

type StatusFilter = TestCaseStatus | 'all'
type CategoryFilter = TestCaseCategory | 'all'
type SortKey = 'case' | 'difficulty' | 'delta' | 'title'

/**
 * The filter sets come from the label module, so the buttons offered are exactly
 * the union members the contract defines — not a list this view curated.
 */
const CATEGORIES: ReadonlyArray<CategoryFilter> = ['all', ...CASE_CATEGORY_ORDER]
const STATUSES: ReadonlyArray<StatusFilter> = ['all', ...CASE_STATUS_ORDER]

function deltaClass(delta: number): string {
  if (delta < 0) return 'record__delta record__delta--down'
  if (delta > 0) return 'record__delta record__delta--up'
  return 'record__delta'
}

/**
 * The tabulated record: every matched case, both versions, one row each.
 *
 * The row is the unit of the record. Selecting one opens its evidence packet
 * rather than navigating away, so a reviewer never loses their place in the
 * table while checking a claim.
 */
export function CaseTable({ scenario, selectedCaseId, onSelectCase }: Props): React.JSX.Element {
  const [status, setStatus] = useState<StatusFilter>('all')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [sort, setSort] = useState<SortKey>('case')
  const [regressionsOnly, setRegressionsOnly] = useState(false)

  const rows = useMemo(() => {
    let list: CaseOutcome[] = [...scenario.outcomes]

    if (status !== 'all') {
      list = list.filter(
        (o) => o.baselineStatus === status || o.candidateStatus === status,
      )
    }
    if (category !== 'all') list = list.filter((o) => o.spec.category === category)
    if (regressionsOnly) list = list.filter((o) => o.regression)

    list.sort((a, b) => {
      switch (sort) {
        case 'difficulty':
          return b.spec.difficulty - a.spec.difficulty
        case 'delta':
          return a.delta - b.delta
        case 'title':
          return a.spec.title.localeCompare(b.spec.title)
        default:
          return a.spec.n - b.spec.n
      }
    })
    return list
  }, [scenario, status, category, sort, regressionsOnly])

  const regressedCount = scenario.outcomes.filter((o) => o.regression).length

  return (
    <div className="record-wrap">
      <div className="filters">
        <div className="filters__group">
          <span className="u-micro">类别</span>
          <div className="rocker" role="group" aria-label="按类别筛选">
            {CATEGORIES.map((value) => (
              <button
                key={value}
                type="button"
                className="rocker__pos"
                aria-pressed={category === value}
                onClick={() => setCategory(value)}
              >
                {value === 'all' ? '全部' : caseCategoryLabel(value)}
              </button>
            ))}
          </div>
        </div>

        <div className="filters__group">
          <span className="u-micro">状态</span>
          <div className="rocker" role="group" aria-label="按状态筛选">
            {STATUSES.map((value) => (
              <button
                key={value}
                type="button"
                className="rocker__pos"
                aria-pressed={status === value}
                onClick={() => setStatus(value)}
              >
                {value === 'all' ? '全部' : caseStatusLabel(value)}
              </button>
            ))}
          </div>
        </div>

        <div className="filters__group">
          <span className="u-micro">排序</span>
          <label className="visually-hidden" htmlFor="sort-key">
            排序方式
          </label>
          <select
            id="sort-key"
            className="ctl"
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
            style={{ padding: 'var(--s1) var(--s2)' }}
          >
            <option value="case">场景编号</option>
            <option value="difficulty">难度</option>
            <option value="delta">回归幅度</option>
            <option value="title">标题</option>
          </select>
        </div>

        <div className="filters__group">
          <button
            type="button"
            className="rocker__pos"
            aria-pressed={regressionsOnly}
            onClick={() => setRegressionsOnly((value) => !value)}
            style={{ border: 'var(--rule-ink)' }}
          >
            只看回归（{regressedCount}）
          </button>
        </div>

        <span className="u-micro" style={{ marginLeft: 'auto' }}>
          {rows.length} / {scenario.outcomes.length} 个场景
        </span>
      </div>

      <div className="scroll-x">
        <table className="record">
          <caption className="visually-hidden">
            匹配的测试场景，以及每个版本在该场景上的得分和两者的变化
          </caption>
          <thead>
            <tr>
              <th scope="col" className="record__num">
                编号
              </th>
              <th scope="col">场景</th>
              <th scope="col">类别</th>
              <th scope="col">难度</th>
              <th scope="col" className="record__score-col">
                {scenario.baselineVersion}
              </th>
              <th scope="col" className="record__score-col">
                {scenario.candidateVersion}
              </th>
              <th scope="col" className="record__score-col">
                变化
              </th>
              <th scope="col">状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((outcome) => {
              const selected = selectedCaseId === outcome.caseId
              return (
                <tr key={outcome.caseId} aria-selected={selected}>
                  <td className="record__num record__case-no">
                    {String(outcome.spec.n).padStart(2, '0')}
                  </td>
                  <td className="record__title-cell">
                    <button
                      type="button"
                      className="record__open"
                      onClick={() => onSelectCase(outcome.caseId)}
                    >
                      {outcome.spec.title}
                    </button>
                    {outcome.regression && (
                      <>
                        {' '}
                        <span className="chip chip--fail">已回归</span>
                      </>
                    )}
                  </td>
                  <td>
                    <span className="u-micro">{caseCategoryLabel(outcome.spec.category)}</span>
                  </td>
                  <td className="u-num">{outcome.spec.difficulty.toFixed(2)}</td>
                  <td className="u-num">{formatScore(outcome.baselineVerdict.total)}</td>
                  <td
                    className={`u-num ${outcome.regression ? 'record__score--down' : ''}`}
                  >
                    {formatScore(outcome.candidateVerdict.total)}
                  </td>
                  <td className={`u-num ${deltaClass(outcome.delta)}`}>
                    {formatSignedScore(outcome.delta)}
                  </td>
                  <td>
                    <span
                      className={`chip chip--${
                        outcome.candidateStatus === 'passed'
                          ? 'pass'
                          : outcome.candidateStatus === 'error'
                            ? 'error'
                            : 'fail'
                      }`}
                    >
                      {caseStatusLabel(outcome.candidateStatus)}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {rows.length === 0 && (
        <p className="u-micro" style={{ padding: 'var(--s4)' }}>
          当前筛选条件下没有匹配的场景。放宽类别或状态筛选即可看到记录。
        </p>
      )}
    </div>
  )
}
