import type { RunDetail, Transport, TransportInfo } from './transport'
import { ApiError } from './transport'
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

const API_BASE = '/api'

/**
 * Talks to the EvalPilot FastAPI service through the Vite dev proxy.
 *
 * Every method is a thin pass-through: the adapter's job is to normalise
 * transport concerns (JSON parsing, error shape, the events stream) and
 * nothing else. No caching, no retries, no field renaming.
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
    const raw = await this.json<Run & Partial<RunDetail>>(`/runs/${encodeURIComponent(runId)}`)
    // The contract says the detail response carries cases and evidence
    // summaries; tolerate a lean response rather than crashing the console.
    return { ...raw, test_cases: raw.test_cases ?? [], evidence: raw.evidence ?? [] }
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
