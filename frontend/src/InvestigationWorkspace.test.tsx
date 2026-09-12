import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InvestigationWorkspace } from './InvestigationWorkspace'
import { MockInvestigationTransport } from './mockInvestigationTransport'
import {
  counterfactualVerdictLabel,
  decisionVerdictLabel,
  riskLevelLabel,
  stepKindLabel,
} from './i18n/labels'
import { MOCK_RECALLED_INCIDENT_ID } from './i18n/mockScript'

/**
 * The workspace's own tests. They pin the three things a rendering assertion
 * catches and a data test cannot:
 *
 *   1. root-cause rendering — the decision, the before/after scores and the
 *      derived "would restore" reading reach the screen;
 *   2. the download path — the report is written out of the transport's own
 *      text, and the endpoint named beside the button is not a dead one;
 *   3. that the surface shows *structured actions*, never reasoning.
 *
 * The assertions are written against the Chinese labels the workspace prints,
 * resolved through `i18n/labels` rather than typed in as literals — so a change
 * to a status word fails one place, not twelve. Where a value is an invariant
 * of the record (a scenario id, an evidence id, a tool name) the assertion
 * still names the English string, because that is what the console must keep
 * showing unchanged.
 *
 * `cleanup` is called explicitly rather than relied on from the global setup.
 * The setup file clears `document.body` between tests, which unmounts nothing:
 * React keeps its tree, so the previous test's markers stay in the DOM and a
 * `getByText` finds two.
 */
afterEach(cleanup)

const RUN_ID = 'a4f1c8e2-7d35-4b90-8e21-5f6a9c3d0b47'

/**
 * Drive the workspace to a finished investigation, in real time.
 *
 * The follow loop polls at 500 ms and the mock advances one stage per poll, so
 * a full investigation takes about 2.5 s of wall clock. That is deliberate: the
 * workspace has no time-travel seam, and adding one purely for tests would mean
 * the test no longer exercises the loop it is meant to cover.
 *
 * The wait is on `currentStage` rather than on a piece of text, because the
 * decision *heading* renders one poll before the investigation is actually
 * `completed` — the record and the bundle are read together, but the mock's
 * stage only advances on the next read. Waiting on the text alone leaves the
 * report endpoint still 409ing.
 */
async function startWorkspace(): Promise<MockInvestigationTransport> {
  const transport = new MockInvestigationTransport()
  render(<InvestigationWorkspace transport={transport} runId={RUN_ID} />)
  await userEvent.click(screen.getByRole('button', { name: /启动自主调查/ }))
  await waitFor(() => expect(transport.currentStage).toBe(5), { timeout: 10_000 })
  await waitFor(() => expect(document.querySelector('.decision__word')).not.toBeNull())
  return transport
}

describe('InvestigationWorkspace — intake', () => {
  it('prefills the objective from the run context and offers the start action', () => {
    render(
      <InvestigationWorkspace
        transport={new MockInvestigationTransport()}
        runId={RUN_ID}
        runContext={{
          baselineVersion: 'v1.0-baseline',
          candidateVersion: 'v1.1-candidate',
          matchedCases: 26,
        }}
      />,
    )
    const field = screen.getByLabelText(/发布目标/) as HTMLTextAreaElement
    expect(field.value).toContain('v1.1-candidate')
    expect(field.value).toContain('26 个匹配场景')
    expect(screen.getByRole('button', { name: /启动自主调查/ })).toBeEnabled()
  })

  it('names its data source, so a mock is never read as a real investigation', () => {
    render(<InvestigationWorkspace transport={new MockInvestigationTransport()} runId={RUN_ID} />)
    expect(screen.getByText(/确定性模拟调查/)).toBeInTheDocument()
    expect(screen.getByText(/本次调查中的每个数字都是预置模拟数据/)).toBeInTheDocument()
  })

  it('will not start with an empty objective', async () => {
    render(<InvestigationWorkspace transport={new MockInvestigationTransport()} runId={RUN_ID} />)
    await userEvent.clear(screen.getByLabelText(/发布目标/))
    expect(screen.getByRole('button', { name: /启动自主调查/ })).toBeDisabled()
  })
})

describe('InvestigationWorkspace — root-cause rendering', () => {
  it('renders the release decision, its blocking evidence and its actions', async () => {
    await startWorkspace()

    const decision = screen.getByRole('region', { name: /发布裁决/ })
    expect(
      within(decision).getByRole('heading', { name: decisionVerdictLabel('block') }),
    ).toBeInTheDocument()
    expect(within(decision).getByText(riskLevelLabel('critical'))).toBeInTheDocument()
    expect(within(decision).getByText(/不要将 v1\.1-candidate 发布到企业支持试点/)).toBeInTheDocument()
    // Each blocking finding is a citable evidence id, not a count — and the id
    // is an invariant of the record, so it stays in English.
    expect(within(decision).getByText('ev-prompt-injection-password-replay')).toBeInTheDocument()
  })

  it('renders before/after scores and the derived break-even reading per scenario', async () => {
    await startWorkspace()

    const panel = screen.getByRole('region', { name: /反事实根因/ })
    // Scenario ids and intervention names are identifiers, not prose.
    expect(within(panel).getByText('escalation-path')).toBeInTheDocument()
    expect(within(panel).getAllByText('compression_disabled').length).toBeGreaterThan(0)

    // The credential leak is the clearest before/after on the surface: the
    // candidate scores nothing and the guarded build scores full marks.
    const passwordGroup = within(panel).getByText('prompt-injection-password').closest('article')!
    // Both replays ran on this scenario, one per intervention, so this is the
    // one group where a before/after pair and its counter-pair sit together:
    // compression off changes nothing (0.00 → 0.00) and the guard restores the
    // refusal (0.00 → 1.00).
    expect(within(passwordGroup).getAllByText('compression_disabled').length).toBeGreaterThan(0)
    expect(within(passwordGroup).getByText('security_guard_enabled')).toBeInTheDocument()
    expect(within(passwordGroup).getAllByText('0.00').length).toBeGreaterThan(0)
    expect(within(passwordGroup).getAllByText('1.00').length).toBeGreaterThan(0)
    expect(
      within(passwordGroup).getAllByText(counterfactualVerdictLabel('no_effect')).length,
    ).toBeGreaterThan(0)

    // The break-even reading is a derivation, and it says so and carries its
    // margin rather than asserting a winner.
    expect(within(panel).getAllByText(/可恢复至/).length).toBeGreaterThan(0)
    expect(within(panel).getAllByText(/领先次优干预/).length).toBeGreaterThan(0)
  })

  it('labels every replay verdict in words, not colour alone', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /反事实根因/ })
    expect(
      within(panel).getAllByText(counterfactualVerdictLabel('root_cause')).length,
    ).toBeGreaterThan(0)
    expect(
      within(panel).getAllByText(counterfactualVerdictLabel('partial')).length,
    ).toBeGreaterThan(0)
    expect(
      within(panel).getAllByText(counterfactualVerdictLabel('no_effect')).length,
    ).toBeGreaterThan(0)
    expect(
      within(panel).getAllByText(counterfactualVerdictLabel('inconclusive')).length,
    ).toBeGreaterThan(0)
  })

  it('renders the recalled incidents with their match reasons and terms', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /召回的历史事故/ })
    // Incident ids are record identifiers; the prose around them is Chinese.
    expect(within(panel).getByText(MOCK_RECALLED_INCIDENT_ID.escalation)).toBeInTheDocument()
    expect(within(panel).getByText(MOCK_RECALLED_INCIDENT_ID.credential)).toBeInTheDocument()
    expect(within(panel).getByText(/只保留了前者/)).toBeInTheDocument()
    expect(within(panel).getByText('紧急热线')).toBeInTheDocument()
  })
})

describe('InvestigationWorkspace — timeline as structured actions', () => {
  it('renders the tree with hypotheses, probes, replays and the decision', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /调查时间线/ })
    expect(within(panel).getAllByText(stepKindLabel('risk')).length).toBeGreaterThanOrEqual(5)
    expect(within(panel).getAllByText(stepKindLabel('probe')).length).toBeGreaterThan(0)
    expect(within(panel).getAllByText(stepKindLabel('counterfactual')).length).toBeGreaterThan(0)
    expect(within(panel).getByText(/发布裁决：阻断/)).toBeInTheDocument()
  })

  it('opens a step into a structured action, never a transcript', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /调查时间线/ })
    await userEvent.click(within(panel).getByText(/memory\.recall —— 升级条款回归/))

    const detail = screen.getByRole('region', { name: /步骤详情/ })
    // The tool call is printed as a named action with its arguments and artefact
    // — there is no field here a reasoning transcript could occupy. The tool
    // name and the artefact URI are identifiers and stay as the record has them.
    expect(within(detail).getByText('动作')).toBeInTheDocument()
    expect(within(detail).getByText('memory.recall')).toBeInTheDocument()
    expect(within(detail).getByText('memory://incidents?tags=escalation')).toBeInTheDocument()
    // And the evidence it wrote is listed by id so it can be drilled into.
    expect(within(detail).getByText('ev-fingerprint-compression')).toBeInTheDocument()
  })

  it('collapses a subtree on demand', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /调查时间线/ })
    expect(within(panel).getByText(/发布裁决：阻断/)).toBeInTheDocument()
    await userEvent.click(
      within(panel).getByRole('button', { name: /折叠 发布目标与范围/ }),
    )
    expect(within(panel).queryByText(/发布裁决：阻断/)).not.toBeInTheDocument()
  })
})

describe('InvestigationWorkspace — report download', () => {
  it('writes the transport’s own Markdown out, and names no dead endpoint', async () => {
    const created: string[] = []
    const realCreate = URL.createObjectURL
    const realRevoke = URL.revokeObjectURL
    URL.createObjectURL = vi.fn(() => {
      const url = `blob:mock/${created.length}`
      created.push(url)
      return url
    }) as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL

    try {
      await startWorkspace()

      // A mock has no report endpoint, and the workspace says so rather than
      // printing a URL that would 404.
      expect(
        screen.getByText(/无端点 —— 模拟报告在本地生成/),
      ).toBeInTheDocument()

      await userEvent.click(screen.getByRole('button', { name: /下载 report\.md/ }))
      await waitFor(() => expect(created).toHaveLength(1))
      expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
      expect(URL.revokeObjectURL).toHaveBeenCalledWith(created[0])
      // The button reports what it read, so a silent failure is not possible.
      expect(await screen.findByText(/已写入 \d+ 行/)).toBeInTheDocument()
    } finally {
      URL.createObjectURL = realCreate
      URL.revokeObjectURL = realRevoke
    }
  })
})
