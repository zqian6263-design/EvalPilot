import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { InvestigationWorkspace } from './InvestigationWorkspace'
import { MockInvestigationTransport } from './mockInvestigationTransport'

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
 * `cleanup` is called explicitly rather than relied on from the global setup.
 * The setup file clears `document.body` between tests, which unmounts nothing:
 * React keeps its tree, so the previous test's markers stay in the DOM and a
 * `getByText(/^block$/)` finds two.
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
  await userEvent.click(screen.getByRole('button', { name: /start autonomous investigation/i }))
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
    const field = screen.getByLabelText(/release objective/i) as HTMLTextAreaElement
    expect(field.value).toContain('v1.1-candidate')
    expect(field.value).toContain('26 matched scenarios')
    expect(screen.getByRole('button', { name: /start autonomous investigation/i })).toBeEnabled()
  })

  it('names its data source, so a mock is never read as a real investigation', () => {
    render(<InvestigationWorkspace transport={new MockInvestigationTransport()} runId={RUN_ID} />)
    expect(screen.getByText(/deterministic mock investigation/i)).toBeInTheDocument()
    expect(
      screen.getByText(/Every figure in this investigation is seeded mock data/i),
    ).toBeInTheDocument()
  })

  it('will not start with an empty objective', async () => {
    render(<InvestigationWorkspace transport={new MockInvestigationTransport()} runId={RUN_ID} />)
    await userEvent.clear(screen.getByLabelText(/release objective/i))
    expect(screen.getByRole('button', { name: /start autonomous investigation/i })).toBeDisabled()
  })
})

describe('InvestigationWorkspace — root-cause rendering', () => {
  it('renders the release decision, its blocking evidence and its actions', async () => {
    await startWorkspace()

    const decision = screen.getByRole('region', { name: /release decision/i })
    expect(within(decision).getByRole('heading', { name: /^block$/i })).toBeInTheDocument()
    expect(within(decision).getByText(/critical risk/i)).toBeInTheDocument()
    expect(within(decision).getByText(/Do not ship v1\.1-candidate/i)).toBeInTheDocument()
    // Each blocking finding is a citable evidence id, not a count.
    expect(within(decision).getByText('ev-prompt-injection-password-replay')).toBeInTheDocument()
  })

  it('renders before/after scores and the derived break-even reading per scenario', async () => {
    await startWorkspace()

    const panel = screen.getByRole('region', { name: /counterfactual root causes/i })
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
    expect(within(passwordGroup).getAllByText('no effect').length).toBeGreaterThan(0)

    // The break-even reading is a derivation, and it says so and carries its
    // margin rather than asserting a winner.
    expect(within(panel).getAllByText(/would restore/i).length).toBeGreaterThan(0)
    expect(within(panel).getAllByText(/ahead of the next intervention/i).length).toBeGreaterThan(0)
  })

  it('labels every replay verdict in words, not colour alone', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /counterfactual root causes/i })
    expect(within(panel).getAllByText('root cause').length).toBeGreaterThan(0)
    expect(within(panel).getAllByText('partial').length).toBeGreaterThan(0)
    expect(within(panel).getAllByText('no effect').length).toBeGreaterThan(0)
    expect(within(panel).getAllByText('inconclusive').length).toBeGreaterThan(0)
  })

  it('renders the recalled incidents with their match reasons and terms', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /recalled incidents/i })
    expect(within(panel).getByText('ESC-2214')).toBeInTheDocument()
    expect(within(panel).getByText('SEC-3310')).toBeInTheDocument()
    expect(within(panel).getByText(/brevity pass kept only the first/i)).toBeInTheDocument()
    expect(within(panel).getByText('emergency hotline')).toBeInTheDocument()
  })
})

describe('InvestigationWorkspace — timeline as structured actions', () => {
  it('renders the tree with hypotheses, probes, replays and the decision', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /investigation timeline/i })
    expect(within(panel).getAllByText('risk').length).toBeGreaterThanOrEqual(5)
    expect(within(panel).getAllByText('probe').length).toBeGreaterThan(0)
    expect(within(panel).getAllByText('counterfactual').length).toBeGreaterThan(0)
    expect(within(panel).getByText(/Release decision: block/i)).toBeInTheDocument()
  })

  it('opens a step into a structured action, never a transcript', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /investigation timeline/i })
    await userEvent.click(within(panel).getByText(/memory\.recall — escalation clause regressions/i))

    const detail = screen.getByRole('region', { name: /step detail/i })
    // The tool call is printed as a named action with its arguments and artefact
    // — there is no field here a reasoning transcript could occupy.
    expect(within(detail).getByText('action')).toBeInTheDocument()
    expect(within(detail).getByText('memory.recall')).toBeInTheDocument()
    expect(within(detail).getByText('memory://incidents?tags=escalation')).toBeInTheDocument()
    // And the evidence it wrote is listed by id so it can be drilled into.
    expect(within(detail).getByText('ev-fingerprint-compression')).toBeInTheDocument()
  })

  it('collapses a subtree on demand', async () => {
    await startWorkspace()
    const panel = screen.getByRole('region', { name: /investigation timeline/i })
    expect(within(panel).getByText(/Release decision: block/i)).toBeInTheDocument()
    await userEvent.click(
      within(panel).getByRole('button', { name: /collapse Release objective and scope/i }),
    )
    expect(within(panel).queryByText(/Release decision: block/i)).not.toBeInTheDocument()
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
        screen.getByText(/no endpoint — the mock report is generated locally/i),
      ).toBeInTheDocument()

      await userEvent.click(screen.getByRole('button', { name: /download report\.md/i }))
      await waitFor(() => expect(created).toHaveLength(1))
      expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
      expect(URL.revokeObjectURL).toHaveBeenCalledWith(created[0])
      // The button reports what it read, so a silent failure is not possible.
      expect(await screen.findByText(/lines written/i)).toBeInTheDocument()
    } finally {
      URL.createObjectURL = realCreate
      URL.revokeObjectURL = realRevoke
    }
  })
})
