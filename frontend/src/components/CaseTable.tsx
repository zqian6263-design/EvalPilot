import { useMemo, useState } from 'react'
import type { TestCaseCategory, TestCaseStatus } from '../api/types'
import type { CaseOutcome, Scenario } from '../fixtures/scenarios'
import { formatScore, formatSignedScore } from '../lib/format'

interface Props {
  scenario: Scenario
  selectedCaseId: string | null
  onSelectCase: (caseId: string) => void
}

type StatusFilter = TestCaseStatus | 'all'
type CategoryFilter = TestCaseCategory | 'all'
type SortKey = 'case' | 'difficulty' | 'delta' | 'title'

const CATEGORIES: ReadonlyArray<CategoryFilter> = [
  'all',
  'normal',
  'boundary',
  'adversarial',
  'regression',
]
const STATUSES: ReadonlyArray<StatusFilter> = ['all', 'passed', 'failed', 'error']

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
          <span className="u-micro">Category</span>
          <div className="rocker" role="group" aria-label="Filter by category">
            {CATEGORIES.map((value) => (
              <button
                key={value}
                type="button"
                className="rocker__pos"
                aria-pressed={category === value}
                onClick={() => setCategory(value)}
              >
                {value === 'all' ? 'All' : value}
              </button>
            ))}
          </div>
        </div>

        <div className="filters__group">
          <span className="u-micro">Status</span>
          <div className="rocker" role="group" aria-label="Filter by status">
            {STATUSES.map((value) => (
              <button
                key={value}
                type="button"
                className="rocker__pos"
                aria-pressed={status === value}
                onClick={() => setStatus(value)}
              >
                {value === 'all' ? 'All' : value}
              </button>
            ))}
          </div>
        </div>

        <div className="filters__group">
          <span className="u-micro">Sort</span>
          <label className="visually-hidden" htmlFor="sort-key">
            Sort the record by
          </label>
          <select
            id="sort-key"
            className="ctl"
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
            style={{ padding: 'var(--s1) var(--s2)' }}
          >
            <option value="case">Case number</option>
            <option value="difficulty">Difficulty</option>
            <option value="delta">Largest regression</option>
            <option value="title">Title</option>
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
            Regressions only ({regressedCount})
          </button>
        </div>

        <span className="u-micro" style={{ marginLeft: 'auto' }}>
          {rows.length} of {scenario.outcomes.length} cases
        </span>
      </div>

      <div className="scroll-x">
        <table className="record">
          <caption className="visually-hidden">
            Matched test cases with the score each version received and the change between them
          </caption>
          <thead>
            <tr>
              <th scope="col" className="record__num">
                No
              </th>
              <th scope="col">Case</th>
              <th scope="col">Category</th>
              <th scope="col">Diff.</th>
              <th scope="col" className="record__score-col">
                {scenario.baselineVersion}
              </th>
              <th scope="col" className="record__score-col">
                {scenario.candidateVersion}
              </th>
              <th scope="col" className="record__score-col">
                Change
              </th>
              <th scope="col">Status</th>
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
                        <span className="chip chip--fail">regressed</span>
                      </>
                    )}
                  </td>
                  <td>
                    <span className="u-micro">{outcome.spec.category}</span>
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
                      {outcome.candidateStatus}
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
          No case matches the current filters. Widen the category or status selection to see rows.
        </p>
      )}
    </div>
  )
}
