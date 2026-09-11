import type {
  CreateRunRequest,
  DemoContext,
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

  /**
   * Optional: resolve the demo entry into a project and a run that actually
   * exist on the backend.
   *
   * `GET /demo/seed` is side-effect free by contract, so it cannot create
   * anything. Only a transport that can write implements this; the console
   * treats its absence as "not available here" and falls back to the seed
   * metadata plus bundled fixtures rather than inventing a run id.
   */
  getDemoContext?(): Promise<DemoContext>
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

/**
 * `GET /runs/{run_id}` — a Run plus its cases, evidence, and counts.
 *
 * The counts are the backend's own tally, not `array.length`. The live service
 * returns them inside the response envelope, and a detail payload that is
 * missing one reports `0` only because the backend said nothing — deriving a
 * count locally would let a truncated case list read as a complete run.
 */
export interface RunDetail extends Run {
  test_cases: TestCase[]
  evidence: Evidence[]
  evidence_count: number
  finding_count: number
  event_count: number
}

/**
 * The live backend's `GET /runs/{run_id}` response, before normalisation.
 *
 * `docs/INTERFACES.md` describes the endpoint as "`Run` with test cases and
 * evidence summaries" without fixing the field layout, and the running service
 * wraps the run in this envelope. Naming it here is an adapter-local decision
 * recorded in `frontend/TRANSPORT.md`; the contract itself is untouched.
 *
 * Every field but `run` is optional so a lean response still normalises.
 */
export interface RunDetailEnvelope {
  run: Run
  test_cases?: TestCase[]
  evidence?: Evidence[]
  evidence_count?: number
  finding_count?: number
  event_count?: number
}

/**
 * What `GET /runs/{run_id}` actually puts on the wire, in either layout.
 *
 * The service returns the envelope; a backend that flattens it — or
 * `MockTransport` — returns the detail. The normaliser discriminates on `run`,
 * and this alias is the honest type of "either one" without pretending a
 * response carries both shapes' fields at once.
 */
export type RunDetailPayload = RunDetailEnvelope | RunDetail

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
