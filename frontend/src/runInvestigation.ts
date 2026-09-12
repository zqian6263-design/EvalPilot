/**
 * Driving an investigation from the workspace: create, start, follow, settle.
 *
 * This is `../../api/runLifecycle.ts` for the V2 endpoints, and it exists as a
 * separate module for the same reason: the sequence has real failure modes the
 * UI must not paper over. An investigation that 409s because it already ran, a
 * start that succeeds but leaves the investigation moving, a poll that outlives
 * its budget — each is handled as the fact it is, and each message names what
 * happened rather than retrying silently until something gives.
 *
 * The one departure from the V1 lifecycle is that `investigation.events` is not
 * what advances the state. The events endpoint is part of the contract and the
 * transport implements it, but a *mock* transport that replayed its whole event
 * list instantly would show a finished investigation no matter how partial the
 * bundle actually was. Reading the bundle until it settles is the honest
 * mechanism: the tree the workspace renders is the tree the service reports,
 * never a client-side guess at how far along it is.
 */

import {
  isInvestigationTerminal,
  type Investigation,
  type InvestigationBundle,
  type InvestigationTransport,
  type SteppableInvestigationTransport,
} from './api/investigation'
import { ApiError } from './api/transport'

/** What the workspace knows while a run is in flight. */
export interface InvestigationRun {
  /** The record as last read from the service. */
  investigation: Investigation
  /** The whole bundle as last read, or `null` before the first successful read. */
  bundle: InvestigationBundle | null
  /**
   * True when the poll budget ran out with the investigation still moving.
   * Not an error and not a success: the workspace renders the partial tree and
   * says the investigation is still running.
   */
  settled: boolean
  /** True when the investigation was already finished when the start was asked for. */
  adopted: boolean
  /** A reason worth showing, when a step failed. */
  error: string | null
}

export interface RunInvestigationArgs {
  transport: InvestigationTransport
  objective: string
  /** The existing evaluation run this investigation is opened against. */
  runId: string
  /** Called after every state change, so the view follows the investigation live. */
  onUpdate?: ((run: InvestigationRun) => void) | undefined
  timeoutMs?: number
  intervalMs?: number
  /** Injectable clock and sleep, so the follow loop is testable without real time. */
  now?: () => number
  sleep?: (ms: number) => Promise<void>
  signal?: AbortSignal | undefined
}

const defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Raised when the caller aborted. Kept distinct from a request failure so the
 * follow loop can let an abort out rather than recording it as an error: a
 * viewer who started a second investigation did not hit a problem with the
 * first.
 */
export class AbortedError extends Error {
  constructor() {
    super('investigation run aborted')
    this.name = 'AbortedError'
  }
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw new AbortedError()
}

/**
 * Create an investigation, start it, and follow it until it settles.
 *
 * The sequence:
 *
 *   1. `POST /investigations` — a queued record;
 *   2. read the bundle, so the workspace has something to render before the
 *      first start lands;
 *   3. `POST /investigations/{id}/start` — a `409` here means the investigation
 *      already ran, which is an answer rather than a failure, so the run is
 *      marked `adopted` and followed as it stands;
 *   4. read the bundle on an interval until it reaches a terminal status or the
 *      budget runs out.
 *
 * `onUpdate` fires after every one of those reads, which is what lets the tree
 * fill in front of the viewer instead of appearing finished.
 */
export async function runInvestigation({
  transport,
  objective,
  runId,
  onUpdate,
  timeoutMs = 60_000,
  intervalMs = 500,
  now = () => Date.now(),
  sleep = defaultSleep,
  signal,
}: RunInvestigationArgs): Promise<InvestigationRun> {
  throwIfAborted(signal)

  const created = await transport.createInvestigation({ run_id: runId, objective })
  throwIfAborted(signal)

  let run: InvestigationRun = {
    investigation: created,
    bundle: null,
    settled: false,
    adopted: false,
    error: null,
  }
  onUpdate?.(run)

  // Read before starting, so a start that fails still leaves the workspace with
  // the record the service created rather than an empty pane.
  try {
    const bundle = await transport.getInvestigation(created.id, { signal })
    run = { ...run, investigation: bundle.investigation, bundle }
    onUpdate?.(run)
  } catch (cause) {
    if (cause instanceof AbortedError) throw cause
    run = { ...run, error: describe(cause) }
    onUpdate?.(run)
  }

  if (created.status === 'queued' || run.investigation.status === 'queued') {
    try {
      await transport.startInvestigation(created.id, { signal })
    } catch (cause) {
      if (cause instanceof AbortedError) throw cause
      // A conflict means the service already has this investigation moving or
      // finished. Adopt it: the honest response is to open it as it stands, not
      // to swallow the conflict and show a spinner over something not moving.
      if (cause instanceof ApiError && cause.status === 409) {
        run = { ...run, adopted: true }
        onUpdate?.(run)
      } else {
        run = { ...run, error: describe(cause) }
        onUpdate?.(run)
        return run
      }
    }
  } else {
    run = { ...run, adopted: true }
    onUpdate?.(run)
  }

  return follow({ transport, run, timeoutMs, intervalMs, now, sleep, onUpdate, signal })
}

interface FollowArgs {
  transport: InvestigationTransport
  run: InvestigationRun
  timeoutMs: number
  intervalMs: number
  now: () => number
  sleep: (ms: number) => Promise<void>
  onUpdate?: ((run: InvestigationRun) => void) | undefined
  signal?: AbortSignal | undefined
}

async function follow({
  transport,
  run: initial,
  timeoutMs,
  intervalMs,
  now,
  sleep,
  onUpdate,
  signal,
}: FollowArgs): Promise<InvestigationRun> {
  const deadline = now() + timeoutMs
  let run = initial
  // The real service has a scheduler behind it and advances on its own. The
  // deterministic mock has none, so its reads would return the same partial
  // state forever and the follow loop would always time out. Detection, not
  // assumption: a transport that can step says so, and one that cannot is left
  // alone.
  const steppable = transport as Partial<SteppableInvestigationTransport>

  while (!isInvestigationTerminal(run.investigation.status)) {
    if (now() >= deadline) {
      run = { ...run, settled: false }
      onUpdate?.(run)
      return run
    }
    await sleep(intervalMs)
    throwIfAborted(signal)
    steppable.advanceMockStage?.()

    try {
      const bundle = await transport.getInvestigation(run.investigation.id, { signal })
      run = { ...run, investigation: bundle.investigation, bundle, error: null }
    } catch (cause) {
      if (cause instanceof AbortedError) throw cause
      run = { ...run, error: describe(cause) }
    }
    onUpdate?.(run)

    if (now() >= deadline && !isInvestigationTerminal(run.investigation.status)) {
      run = { ...run, settled: false }
      onUpdate?.(run)
      return run
    }
  }

  run = { ...run, settled: true }
  onUpdate?.(run)
  return run
}

function describe(cause: unknown): string {
  if (cause instanceof Error) return cause.message
  return 'request failed'
}

/**
 * The objective the intake field starts from, given the run it is opened
 * against. Prefilled because a reviewer's first action should be to edit a
 * sentence, not to write one — and the sentence names the versions, so it
 * cannot go stale against the run the way a hard-coded default would.
 *
 * The fields are `| undefined` because the project builds with
 * `exactOptionalPropertyTypes` and the caller passes a context object whose
 * members are themselves optional.
 */
export function defaultObjective(context: {
  candidateVersion?: string | undefined
  baselineVersion?: string | undefined
  matchedCases?: number | undefined
}): string {
  const candidate = context.candidateVersion ?? 'the candidate'
  const baseline = context.baselineVersion ?? 'the baseline'
  const cases =
    typeof context.matchedCases === 'number' ? `${context.matchedCases} matched scenarios` : 'the matched scenarios'
  return `Decide whether ${candidate} may ship, given that ${baseline} passed all ${cases} and ${candidate} failed the regressed ones.`
}
