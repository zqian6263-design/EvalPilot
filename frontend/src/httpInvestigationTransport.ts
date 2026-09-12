/**
 * The V2 service, through the Vite `/api` proxy.
 *
 * Mirrors `HttpTransport` in `./httpTransport.ts`: every method is a thin
 * pass-through, and the adapter's whole job is to normalise transport concerns
 * (JSON parsing, the error shape, the events stream, the report as text) and
 * nothing else. No caching, no retries, no field renaming.
 *
 * The one piece of real work is the events stream. `docs/V2_INTERFACES.md` says
 * the endpoint reuses the run-event envelope, which in V1 may arrive as SSE or
 * as NDJSON. The reader below splits on newlines — which handles either framing
 * — and strips a leading `data:` only when the content type says SSE, exactly
 * as the V1 reader does.
 *
 * `report.md` returns `text/markdown`, not JSON, so it is the one method that
 * does not go through `json()`.
 */

import { ApiError, type InvestigationRequestOptions, type InvestigationTransport, type InvestigationTransportInfo } from './api/investigation'
import {
  normalizeIncidentLibrary,
  normalizeInvestigation,
  normalizeInvestigationBundle,
  normalizeInvestigationEvent,
} from './api/investigation'
import type {
  CreateInvestigationRequest,
  IncidentLibrary,
  Investigation,
  InvestigationBundle,
  InvestigationBundlePayload,
  InvestigationEvent,
} from './api/investigation'

const API_BASE = '/api'

/**
 * `RequestInit` with the signal only present when there is one.
 *
 * `exactOptionalPropertyTypes` is on and `RequestInit.signal` is
 * `AbortSignal | null`, so `{ signal: options?.signal }` — which is
 * `AbortSignal | undefined` — is a type error rather than an omitted field.
 * Spreading the key in only when it exists says exactly what is meant: no
 * signal was given, so none is passed, rather than a signal of `undefined`
 * being handed to `fetch`.
 */
function initWith(options: InvestigationRequestOptions | undefined, init: RequestInit = {}): RequestInit {
  return options?.signal ? { ...init, signal: options.signal } : init
}

export class HttpInvestigationTransport implements InvestigationTransport {
  constructor(
    private readonly baseUrl: string = API_BASE,
    private readonly fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {}

  describe(): InvestigationTransportInfo {
    return {
      kind: 'http',
      live: true,
      label: '实时后端 — 调查服务',
      baseUrl: this.baseUrl,
    }
  }

  async createInvestigation(
    request: CreateInvestigationRequest,
    options?: InvestigationRequestOptions,
  ): Promise<Investigation> {
    const raw = await this.json<unknown>(
      '/investigations',
      initWith(options, { method: 'POST', body: JSON.stringify(request) }),
    )
    return normalizeInvestigation(raw)
  }

  /**
   * `POST /investigations/{id}/start` answers `202 Accepted` with no body the
   * workspace needs, so the response is discarded rather than parsed. The
   * caller re-reads the record to see what the start did.
   */
  async startInvestigation(id: string, options?: InvestigationRequestOptions): Promise<void> {
    const url = `${this.baseUrl}/investigations/${encodeURIComponent(id)}/start`
    const response = await this.fetchImpl(
      url,
      initWith(options, { method: 'POST', headers: { 'Content-Type': 'application/json' } }),
    )
    if (!response.ok) {
      throw new ApiError(`request failed: ${response.statusText}`, response.status, url)
    }
  }

  async getInvestigation(
    id: string,
    options?: InvestigationRequestOptions,
  ): Promise<InvestigationBundle> {
    const raw = await this.json<InvestigationBundlePayload>(
      `/investigations/${encodeURIComponent(id)}`,
      initWith(options),
    )
    return normalizeInvestigationBundle(raw)
  }

  async *streamInvestigation(
    id: string,
    options?: InvestigationRequestOptions,
  ): AsyncIterable<InvestigationEvent> {
    const url = `${this.baseUrl}/investigations/${encodeURIComponent(id)}/events`
    const response = await this.fetchImpl(
      url,
      initWith(options, {
        headers: { Accept: 'text/event-stream, application/x-ndjson, application/json' },
      }),
    )
    if (!response.ok || !response.body) {
      throw new ApiError(`events stream failed: ${response.statusText}`, response.status, url)
    }

    const contentType = response.headers.get('content-type') ?? ''
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          const event = parseEventLine(line, contentType)
          if (event) yield event
        }
      }
      const tail = parseEventLine(buffer, contentType)
      if (tail) yield tail
    } finally {
      // A consumer that stops early — the workspace unmounts, or the user
      // starts a second investigation — must release the stream rather than
      // leave the connection reading into a buffer nobody drains.
      reader.releaseLock()
    }
  }

  /**
   * `GET /investigations/{id}/report.md` serves Markdown, not JSON.
   *
   * A report that does not exist yet is a `409`, which the workspace treats as
   * "not written yet" rather than as a failure; that decision is the caller's,
   * so this surfaces the status the service gave rather than swallowing it.
   */
  async getReport(id: string, options?: InvestigationRequestOptions): Promise<string> {
    const url = `${this.baseUrl}/investigations/${encodeURIComponent(id)}/report.md`
    const response = await this.fetchImpl(
      url,
      initWith(options, { headers: { Accept: 'text/markdown, text/plain, */*' } }),
    )
    if (!response.ok) {
      throw new ApiError(`report request failed: ${response.statusText}`, response.status, url)
    }
    return response.text()
  }

  async listIncidents(
    query?: string,
    tag?: string,
    options?: InvestigationRequestOptions,
  ): Promise<IncidentLibrary> {
    const params = new URLSearchParams()
    if (query) params.set('query', query)
    if (tag) params.set('tag', tag)
    const suffix = params.toString() ? `?${params.toString()}` : ''
    const raw = await this.json<unknown>(`/memory/incidents${suffix}`, initWith(options))
    return normalizeIncidentLibrary(raw)
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

function parseEventLine(line: string, contentType: string): InvestigationEvent | null {
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

function safeParse(raw: string): InvestigationEvent | null {
  try {
    return normalizeInvestigationEvent(JSON.parse(raw))
  } catch {
    // A malformed frame must not kill the stream; skip it.
    return null
  }
}
