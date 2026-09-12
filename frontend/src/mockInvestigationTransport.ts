/**
 * Serves the deterministic mock investigation through the same interface as the
 * real service.
 *
 * Two jobs, the same two `MockTransport` has in `../../api/mockTransport.ts`.
 * First, the workspace must be demonstrable end to end with no backend running
 * — a competition requirement, not a convenience. Second, this is what the view
 * tests drive, so the UI has a stable, reproducible subject that does not
 * depend on a network.
 *
 * Unlike the V1 mock, this one has a *lifecycle*: `createInvestigation` returns
 * a queued record and `startInvestigation` advances it. That is deliberate. The
 * workspace's whole first act — intake, press start, watch the tree fill — is
 * only testable if the transport can be caught mid-flight, and a mock that
 * always returned a finished investigation would let a broken start button pass
 * every test.
 *
 * It is deterministic by construction: every value comes from literals in
 * `./mockInvestigation`, the only clock is `MOCK_BASE_TIME`, and `Math.random`
 * and `Date.now` appear nowhere.
 */

import { ApiError } from './api/investigation'
import type {
  CounterfactualExperiment,
  CreateInvestigationRequest,
  IncidentLibrary,
  Investigation,
  InvestigationBundle,
  InvestigationEvent,
  InvestigationRequestOptions,
  InvestigationStatus,
  InvestigationStep,
  InvestigationTransport,
  InvestigationTransportInfo,
  ReleaseDecision,
} from './api/investigation'
import {
  MOCK_INVESTIGATION_ID,
  MOCK_RUN_ID,
  buildMockBundle,
  buildMockCounterfactuals,
  buildMockDecision,
  buildMockEvents,
  buildMockIncidentLibrary,
  buildMockInvestigation,
  buildMockReport,
  buildMockSteps,
  mockAt,
} from './mockInvestigation'

/** Statuses the start sequence steps through, in order. */
const LIFECYCLE: readonly InvestigationStatus[] = [
  'queued',
  'planning',
  'investigating',
  'replaying',
  'deciding',
  'completed',
]

export interface MockInvestigationOptions {
  /**
   * How long `streamInvestigation` pauses between events, in ms.
   *
   * Zero by default: the mock's event list is a record of a finished
   * investigation, and pacing a record would fake a liveness the mock does not
   * have. A caller that wants to watch the tree fill sets this and reads the
   * bundle after each event.
   */
  eventDelayMs?: number
}

export class MockInvestigationTransport implements InvestigationTransport {
  /** How far through the start sequence this mock has been driven. */
  private stage = 0
  /** The run this mock's investigation was opened against. */
  private runId = MOCK_RUN_ID
  private readonly eventDelayMs: number

  constructor(options: MockInvestigationOptions = {}) {
    this.eventDelayMs = options.eventDelayMs ?? 0
  }

  static describeStatic(): InvestigationTransportInfo {
    return {
      kind: 'mock',
      live: false,
      label: '离线 — 确定性模拟调查',
      baseUrl: null,
    }
  }

  describe(): InvestigationTransportInfo {
    return MockInvestigationTransport.describeStatic()
  }

  async createInvestigation(request: CreateInvestigationRequest): Promise<Investigation> {
    this.stage = 0
    this.runId = request.run_id || MOCK_RUN_ID
    return {
      ...buildMockInvestigation(),
      run_id: this.runId,
      objective: request.objective,
      status: 'queued',
      summary: '',
      risk_level: 'low',
      decision_verdict: 'review',
      completed_at: null,
    }
  }

  /**
   * Advance one stage of the lifecycle.
   *
   * A second call moves on rather than restarting, which is what lets a test
   * catch the workspace mid-investigation. Calling start on a finished
   * investigation is a `409`, the same conflict the real service raises, so the
   * workspace's "already finished, opening as it stands" path is reachable
   * offline too.
   */
  async startInvestigation(id: string): Promise<void> {
    if (id !== MOCK_INVESTIGATION_ID) {
      throw new ApiError(`unknown investigation ${id}`, 404, 'mock://investigations/start')
    }
    if (this.stage >= LIFECYCLE.length - 1) {
      throw new ApiError('investigation is already completed', 409, 'mock://investigations/start')
    }
    this.stage += 1
  }

  private status(): InvestigationStatus {
    return LIFECYCLE[this.stage]!
  }

  /**
   * The bundle as it stands at the current stage.
   *
   * Partially-progressed states are honest: at `planning` the timeline holds
   * only the objective and the risk hypotheses, at `replaying` the probes have
   * landed but no replay has, and the decision appears only once the
   * investigation reaches `deciding`. That is what the tree looks like while it
   * is being built, and a mock that skipped straight to `completed` would hide
   * every loading state the workspace has.
   */
  async getInvestigation(id: string): Promise<InvestigationBundle> {
    if (id !== MOCK_INVESTIGATION_ID) {
      throw new ApiError(`unknown investigation ${id}`, 404, `mock://investigations/${id}`)
    }
    const full = buildMockBundle()

    if (this.stage >= LIFECYCLE.length - 1) {
      return { ...full, investigation: { ...full.investigation, run_id: this.runId } }
    }
    const status = this.status()

    return {
      investigation: {
        ...buildMockInvestigation(),
        run_id: this.runId,
        status,
        summary: status === 'queued' ? '' : full.investigation.summary,
        risk_level: this.stage >= 2 ? 'critical' : 'low',
        decision_verdict: this.stage >= 4 ? 'block' : 'review',
        completed_at: null,
      },
      steps: this.visibleSteps(),
      memory_matches: this.stage >= 2 ? full.memory_matches : [],
      counterfactuals: this.stage >= 3 ? full.counterfactuals : [],
      decision: this.stage >= 4 ? full.decision : null,
    }
  }

  private visibleSteps(): InvestigationStep[] {
    const steps = buildMockSteps()
    if (this.stage <= 0) return []
    if (this.stage === 1) return steps.filter((step) => step.kind === 'risk')
    if (this.stage === 2) {
      return steps.filter(
        (step) => step.kind === 'risk' || step.kind === 'probe' || step.kind === 'tool' || step.kind === 'observation',
      )
    }
    if (this.stage === 3) {
      // Everything except the decision: the replays are in, the call is not.
      return steps.filter((step) => step.kind !== 'decision')
    }
    return steps
  }

  async *streamInvestigation(
    _id: string,
    options?: InvestigationRequestOptions,
  ): AsyncIterable<InvestigationEvent> {
    const delay = this.eventDelayMs
    for (const event of buildMockEvents()) {
      if (options?.signal?.aborted) return
      if (delay > 0) await new Promise((resolve) => setTimeout(resolve, delay))
      yield event
    }
  }

  async listIncidents(query?: string, tag?: string): Promise<IncidentLibrary> {
    return buildMockIncidentLibrary(query, tag)
  }

  async getReport(_id: string): Promise<string> {
    if (this.stage < LIFECYCLE.length - 1) {
      // A report exists only when the investigation has decided. The service
      // answers `409` here; the workspace reads that as "not yet written".
      throw new ApiError('report is not available until the investigation completes', 409, 'mock://report.md')
    }
    return buildMockReport()
  }

  // ------------------------------------------------------ test affordances --

  /**
   * Step the mock's lifecycle on by one stage.
   *
   * The V2 mock's stand-in for the scheduler the real service has behind it:
   * a live investigation advances on its own and the client finds out by
   * reading, so a mock whose reads never change state cannot be caught
   * mid-investigation. The workspace's follow loop detects this method and
   * calls it before each read; `false` means the lifecycle is finished.
   */
  advanceMockStage(): boolean {
    if (this.stage >= LIFECYCLE.length - 1) return false
    this.stage += 1
    return true
  }

  /** The stage the mock has been driven to, for a test that wants to assert on it. */
  get currentStage(): number {
    return this.stage
  }

  /** Jump straight to a stage, for a test that wants a specific partial state. */
  setStage(stage: number): void {
    this.stage = Math.max(0, Math.min(stage, LIFECYCLE.length - 1))
  }

  /** The counterfactual the mock ran on one scenario, for assertions. */
  experimentsFor(scenarioId: string): CounterfactualExperiment[] {
    return buildMockCounterfactuals().filter(
      (experiment) => experiment.scenario_id === scenarioId,
    )
  }

  decisions(): ReleaseDecision {
    return buildMockDecision()
  }

  /** The timestamp the mock's clock starts at, so a test can assert on it. */
  static get baseTime(): string {
    return mockAt(0)
  }
}
