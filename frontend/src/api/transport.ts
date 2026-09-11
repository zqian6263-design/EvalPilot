import type {
  CreateRunRequest,
  DemoSeed,
  Evidence,
  Health,
  ProgressEvent,
  Project,
  Report,
  Run,
  TestCase,
} from './types'

/**
 * Everything the console needs from a backend, in one interface.
 *
 * Two implementations satisfy it: `HttpTransport` (the real FastAPI service
 * behind the Vite proxy) and `MockTransport` (bundled fixtures). The UI is
 * written against this interface only, so it cannot tell them apart except by
 * asking `describe().live` — which is what the offline badge reads.
 */
export interface Transport {
  /** Identifies the transport for the UI's data-provenance badge. */
  describe(): TransportInfo

  health(): Promise<Health>
  listProjects(): Promise<Project[]>
  getProject(projectId: string): Promise<Project>
  listRuns(): Promise<Run[]>
  getRun(runId: string): Promise<RunDetail>
  createRun(body: CreateRunRequest): Promise<Run>
  startRun(runId: string): Promise<Run>
  cancelRun(runId: string): Promise<Run>
  getReport(runId: string): Promise<Report>
  getDemoSeed(): Promise<DemoSeed>
  /**
   * Progress events for a run. The contract permits SSE or newline-delimited
   * JSON; the adapter normalises whichever it gets into a plain async stream
   * so the UI renders one shape.
   */
  streamEvents(runId: string): AsyncIterable<ProgressEvent>
}

export interface TransportInfo {
  /** `http` when talking to a real backend, `mock` when serving fixtures. */
  kind: 'http' | 'mock'
  live: boolean
  /** Shown in the UI, e.g. "offline demo — bundled fixtures". */
  label: string
  /** Base URL for the http transport; null for mock. */
  baseUrl: string | null
}

/** `GET /runs/{run_id}` — a Run plus its cases and evidence summaries. */
export interface RunDetail extends Run {
  test_cases: TestCase[]
  evidence: Evidence[]
}

/** Raised for any non-2xx response or malformed body. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly url: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}
