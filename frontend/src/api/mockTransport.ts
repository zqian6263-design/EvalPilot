import { ApiError } from './transport'
import type { RunDetail, Transport, TransportInfo } from './transport'
import type {
  CreateRunRequest,
  DemoSeed,
  Health,
  ProgressEvent,
  Project,
  Report,
  Run,
  TestCase,
} from './types'
import { EVIDENCE, FINDINGS, REPORT } from '../fixtures/findings'
import { RUN_SUMMARY } from '../fixtures/metrics'
import { at, PROJECT_ID, REPORT_A_ID, RUN_A_ID } from '../fixtures/ids'
import { PRIMARY, SCENARIOS, scenarioById, type ScenarioId } from '../fixtures/scenarios'
import { timelineFor } from '../fixtures/timeline'

/**
 * Serves the bundled fixtures through the same interface as the real backend.
 *
 * Two jobs. First, the console must be demonstrable end to end with no backend
 * running — that is a competition requirement, not a convenience. Second, the
 * fixtures are what the view tests drive, so the UI has a stable, reproducible
 * subject that does not depend on a network.
 *
 * It is deterministic by construction: every value comes from literals in
 * `src/fixtures`, and the only clock is the frozen `BASE_TIME`.
 */
export class MockTransport implements Transport {
  describe(): TransportInfo {
    return MockTransport.describeStatic()
  }

  static describeStatic(): TransportInfo {
    return {
      kind: 'mock',
      live: false,
      label: 'offline demo — bundled fixtures',
      baseUrl: null,
    }
  }

  async health(): Promise<Health> {
    return { status: 'ok', version: 'mock-0.1.0' }
  }

  async listProjects(): Promise<Project[]> {
    return [this.project()]
  }

  async getProject(projectId: string): Promise<Project> {
    if (projectId !== PROJECT_ID) {
      throw new ApiError(`unknown project ${projectId}`, 404, `mock://projects/${projectId}`)
    }
    return this.project()
  }

  async listRuns(): Promise<Run[]> {
    return SCENARIOS.map((scenario) => this.runFor(scenario.id))
  }

  async getRun(runId: string): Promise<RunDetail> {
    const scenario = this.scenarioForRun(runId)
    const baselineCases: TestCase[] = scenario.outcomes.map((outcome) => ({
      id: `${outcome.caseId}-b`,
      run_id: RUN_A_ID,
      title: outcome.spec.title,
      category: outcome.spec.category,
      input: { question: outcome.spec.question, source: outcome.spec.source },
      expected: outcome.spec.expected as unknown as Record<string, unknown>,
      difficulty: outcome.spec.difficulty,
      status: outcome.baselineStatus,
      version: 'baseline',
      output: { text: outcome.baseline.text, citations: [...outcome.baseline.citations] },
    }))
    const candidateCases: TestCase[] = scenario.outcomes.map((outcome) => ({
      id: `${outcome.caseId}-c`,
      run_id: RUN_A_ID,
      title: outcome.spec.title,
      category: outcome.spec.category,
      input: { question: outcome.spec.question, source: outcome.spec.source },
      expected: outcome.spec.expected as unknown as Record<string, unknown>,
      difficulty: outcome.spec.difficulty,
      status: outcome.candidateStatus,
      version: 'candidate',
      output: { text: outcome.candidate.text, citations: [...outcome.candidate.citations] },
    }))

    return {
      ...this.runFor(scenario.id),
      test_cases: [...baselineCases, ...candidateCases],
      evidence: [...EVIDENCE],
      // The counts are the fixture corpus' own totals, so the offline console
      // reports the same tallies the live one reads out of the envelope.
      evidence_count: EVIDENCE.length,
      finding_count: FINDINGS.length,
      event_count: timelineFor(scenario.id).length,
    }
  }

  async createRun(body: CreateRunRequest): Promise<Run> {
    return {
      ...this.runFor('citation-regression'),
      baseline_version: body.baseline_version,
      candidate_version: body.candidate_version,
    }
  }

  async startRun(): Promise<Run> {
    return this.runFor('citation-regression')
  }

  async cancelRun(runId: string): Promise<Run> {
    return { ...this.scenarioRun(runId), status: 'cancelled' }
  }

  async getReport(runId: string): Promise<Report> {
    if (runId !== RUN_A_ID) {
      // Non-primary scenarios share the headline report's shape; the console
      // only renders the primary report view today.
      return { ...REPORT, run_id: runId }
    }
    return { ...REPORT, metrics: { ...RUN_SUMMARY.metrics } }
  }

  async getDemoSeed(): Promise<DemoSeed> {
    return {
      project: this.project(),
      runs: SCENARIOS.map((scenario) => this.runFor(scenario.id)),
      scenarios: SCENARIOS.map((scenario) => ({
        id: scenario.id,
        label: scenario.label,
        note: scenario.note,
        change: scenario.change,
      })),
    }
  }

  async *streamEvents(runId: string): AsyncIterable<ProgressEvent> {
    const scenarioId = this.scenarioIdForRun(runId)
    // Replay the frozen transcript with no delay: the fixture stream is a
    // record of a finished run, and pacing it would fake liveness the mock
    // transport does not have.
    for (const entry of timelineFor(scenarioId)) {
      yield entry.event
    }
  }

  // ------------------------------------------------------------- internals --

  private project(): Project {
    return {
      id: PROJECT_ID,
      name: 'kb-assistant',
      scenario: 'Enterprise knowledge-base QA assistant',
      created_at: at(-86400),
    }
  }

  private runFor(id: ScenarioId): Run {
    const scenario = scenarioById(id)
    const runId =
      id === 'citation-regression'
        ? RUN_A_ID
        : `0000${id === 'unchanged' ? 'b7e2' : 'c9d4'}-0000-4000-8000-000000000000`
    return {
      id: runId,
      project_id: PROJECT_ID,
      baseline_version: scenario.baselineVersion,
      candidate_version: scenario.candidateVersion,
      status: 'completed',
      created_at: at(0),
      completed_at: at(232),
    }
  }

  private scenarioRun(runId: string): Run {
    return this.runFor(this.scenarioIdForRun(runId))
  }

  private scenarioIdForRun(runId: string): ScenarioId {
    if (runId === RUN_A_ID) return 'citation-regression'
    const match = SCENARIOS.find((scenario) => this.runFor(scenario.id).id === runId)
    return match ? match.id : PRIMARY.id
  }

  private scenarioForRun(runId: string) {
    return scenarioById(this.scenarioIdForRun(runId))
  }
}

export { FINDINGS, REPORT_A_ID }
