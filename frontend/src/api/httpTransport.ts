import type {
  RunDetail,
  RunDetailEnvelope,
  RunDetailPayload,
  Transport,
  TransportInfo,
} from './transport'
import { ApiError } from './transport'
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

const API_BASE = '/api'

/**
 * Talks to the EvalPilot FastAPI service through the Vite dev proxy.
 *
 * Every method is a thin pass-through: the adapter's job is to normalise
 * transport concerns (JSON parsing, error shape, the events stream) and
 * nothing else. No caching, no retries, no field renaming.
 *
 * Two exceptions, both documented in `frontend/TRANSPORT.md`: `getRun`
 * flattens the response envelope, and `getDemoContext` turns the read-only
 * demo metadata into a project and run that really exist.
 */
export class HttpTransport implements Transport {
  constructor(
    private readonly baseUrl: string = API_BASE,
    private readonly fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {}

  describe(): TransportInfo {
    return { kind: 'http', live: true, label: 'live backend', baseUrl: this.baseUrl }
  }

  health(): Promise<Health> {
    return this.json<Health>('/health')
  }

  listProjects(): Promise<Project[]> {
    return this.json<Project[]>('/projects')
  }

  getProject(projectId: string): Promise<Project> {
    return this.json<Project>(`/projects/${encodeURIComponent(projectId)}`)
  }

  listRuns(): Promise<Run[]> {
    return this.json<Run[]>('/runs')
  }

  async getRun(runId: string): Promise<RunDetail> {
    const raw = await this.json<RunDetailPayload>(`/runs/${encodeURIComponent(runId)}`)
    return normalizeRunDetail(raw)
  }

  createRun(body: CreateRunRequest): Promise<Run> {
    return this.json<Run>('/runs', { method: 'POST', body: JSON.stringify(body) })
  }

  startRun(runId: string): Promise<Run> {
    return this.json<Run>(`/runs/${encodeURIComponent(runId)}/start`, { method: 'POST' })
  }

  cancelRun(runId: string): Promise<Run> {
    return this.json<Run>(`/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' })
  }

  getReport(runId: string): Promise<Report> {
    return this.json<Report>(`/runs/${encodeURIComponent(runId)}/report`)
  }

  getDemoSeed(): Promise<DemoSeed> {
    return this.json<DemoSeed>('/demo/seed')
  }

  /**
   * Resolve the demo into a project and a run that exist on the backend.
   *
   * `GET /demo/seed` describes the demo but is contractually side-effect free,
   * so it hands back version strings and a seed and nothing that has a uuid.
   * This method bridges that gap without inventing an identity:
   *
   *   1. read the seed metadata for the versions, seed and case count;
   *   2. adopt the demo project if `GET /projects` already has it;
   *   3. adopt an existing run for those exact versions, else create one.
   *
   * Step 3 is what makes the entry idempotent. Clicking "Start demo run" twice
   * opens the same run twice rather than accumulating near-identical runs, and
   * a run that already exists is returned untouched — including a completed
   * one, whose evidence is the reason to open it.
   */
  async getDemoContext(): Promise<DemoContext> {
    const seed = await this.getDemoSeed()
    const baselineVersion = seed.baseline_version ?? 'baseline'
    const candidateVersion = seed.candidate_version ?? 'candidate'
    const caseCount = typeof seed.case_count === 'number' ? seed.case_count : null
    const seedValue = typeof seed.seed === 'number' ? seed.seed : null

    // The seed names the project but not its id; match on name, the same key
    // the backend's own `ensure_demo_project` uses.
    const projects = await this.listProjects()
    const existingProject = seed.project?.name
      ? projects.find((project) => project.name === seed.project?.name)
      : undefined
    const project =
      existingProject ??
      (await this.json<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify({
          name: seed.project?.name ?? 'Enterprise Knowledge Base QA',
          scenario: seed.project?.scenario ?? seed.scenario ?? 'kb-qa',
        }),
      }))

    const runs = await this.listRuns()
    const existingRun = runs.find(
      (run) =>
        run.project_id === project.id &&
        run.baseline_version === baselineVersion &&
        run.candidate_version === candidateVersion &&
        (caseCount === null || run.case_count === caseCount),
    )
    const run =
      existingRun ??
      (await this.createRun({
        project_id: project.id,
        baseline_version: baselineVersion,
        candidate_version: candidateVersion,
        ...(caseCount === null ? {} : { case_count: caseCount }),
        ...(seedValue === null ? {} : { seed: seedValue }),
      }))

    return {
      project,
      run,
      created: existingRun === undefined,
      baselineVersion,
      candidateVersion,
      seed: seedValue,
      caseCount,
    }
  }

  async *streamEvents(runId: string): AsyncIterable<ProgressEvent> {
    const url = `${this.baseUrl}/runs/${encodeURIComponent(runId)}/events`
    const response = await this.fetchImpl(url, {
      headers: { Accept: 'text/event-stream, application/x-ndjson, application/json' },
    })
    if (!response.ok || !response.body) {
      throw new ApiError(`events stream failed: ${response.statusText}`, response.status, url)
    }

    const contentType = response.headers.get('content-type') ?? ''
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE frames are blank-line separated; NDJSON frames are newline
      // separated. Splitting on newlines handles both, and the `data:` strip
      // is a no-op for NDJSON.
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        const event = parseEventLine(line, contentType)
        if (event) yield event
      }
    }
    const tail = parseEventLine(buffer, contentType)
    if (tail) yield tail
  }

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${path}`
    const response = await this.fetchImpl(url, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
    if (!response.ok) {
      throw new ApiError(`request failed: ${response.statusText}`, response.status, url)
    }
    return (await response.json()) as T
  }
}

/**
 * Flatten `GET /runs/{run_id}` into the `RunDetail` the console renders.
 *
 * The live service wraps the run in an envelope; `MockTransport` already
 * returns a flattened detail. Detecting which one arrived — rather than
 * assuming — is what lets both transports feed the same views, and it means a
 * backend that adopts the flattened shape later keeps working unchanged.
 *
 * Counts come from the envelope when present and default to `0`, never to
 * `array.length`: the arrays are paged by nothing today, but a count the
 * backend omitted is still an omission, and reporting it as a measured length
 * would be the console asserting something it was not told.
 */
export function normalizeRunDetail(raw: RunDetailPayload): RunDetail {
  if ('run' in raw && raw.run) {
    const envelope = raw as RunDetailEnvelope
    return {
      ...envelope.run,
      test_cases: envelope.test_cases ?? [],
      evidence: envelope.evidence ?? [],
      evidence_count: envelope.evidence_count ?? 0,
      finding_count: envelope.finding_count ?? 0,
      event_count: envelope.event_count ?? 0,
    }
  }

  const flat = raw as RunDetail & Partial<RunDetailEnvelope>
  return {
    ...flat,
    test_cases: flat.test_cases ?? [],
    evidence: flat.evidence ?? [],
    evidence_count: flat.evidence_count ?? 0,
    finding_count: flat.finding_count ?? 0,
    event_count: flat.event_count ?? 0,
  }
}

function parseEventLine(line: string, contentType: string): ProgressEvent | null {
  const trimmed = line.trim()
  if (!trimmed) return null
  if (contentType.includes('event-stream')) {
    if (!trimmed.startsWith('data:')) return null
    const body = trimmed.slice('data:'.length).trim()
    if (!body || body === '[DONE]') return null
    return safeParse(body)
  }
  return safeParse(trimmed)
}

function safeParse(raw: string): ProgressEvent | null {
  try {
    return JSON.parse(raw) as ProgressEvent
  } catch {
    // A malformed frame must not kill the stream; skip it.
    return null
  }
}

export type { Evidence, TestCase }
