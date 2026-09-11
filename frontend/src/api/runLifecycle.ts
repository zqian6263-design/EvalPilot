/**
 * Driving a live run from the console: create-or-adopt, start, wait, read.
 *
 * The console is not a dashboard over an existing database — it is a tool that
 * produces a run and then shows it. That sequence has real failure modes the
 * UI must not paper over: a start that 409s because the run already ran, a
 * report that 409s because the run has not finished, a poll that outlives its
 * budget. Each is handled as the fact it is, and each message names what
 * happened rather than retrying silently until something gives.
 */

import type { Transport } from './transport'
import { ApiError } from './transport'
import type { DemoContext, Report, Run, RunStatus } from './types'

/** Statuses after which a run will not change again. */
const TERMINAL: ReadonlySet<RunStatus> = new Set<RunStatus>([
  'completed',
  'failed',
  'cancelled',
])

export function isTerminal(status: RunStatus): boolean {
  return TERMINAL.has(status)
}

export interface EnsureRunArgs {
  transport: Transport
  /** The run to adopt and start, when the caller already has one. */
  run: Run | null
  /** How to obtain a run when the caller has none. */
  create: () => Promise<Run>
}

/**
 * Get a run into a started state, or explain why it could not be.
 *
 * Four cases, all of them normal:
 *
 *   - no run yet → create one, then start it;
 *   - a run still queued → start it;
 *   - a run already started or finished → **do not start it again**. The
 *     backend answers a second start with 409, and the honest response is to
 *     open the run as it stands, not to swallow the conflict and show a
 *     spinner over a run that is not moving;
 *   - a terminal run → open it as it stands.
 */
export async function ensureRunStarted({
  transport,
  run,
  create,
}: EnsureRunArgs): Promise<{ run: Run; started: boolean; note: string | null }> {
  const target = run ?? (await create())

  if (target.status !== 'queued') {
    return {
      run: target,
      started: false,
      note: isTerminal(target.status)
        ? `run is ${target.status}; opening its recorded results`
        : `run is already ${target.status}; not starting it again`,
    }
  }

  const started = await transport.startRun(target.id)
  return { run: started, started: true, note: null }
}

export interface WaitArgs {
  transport: Transport
  runId: string
  /** Give up after this many ms and return the run as it stands. */
  timeoutMs?: number
  /** Gap between polls. */
  intervalMs?: number
  /** Injectable clock and sleep, so the wait is testable without real time. */
  now?: () => number
  sleep?: (ms: number) => Promise<void>
  /** Called after each poll, for callers that surface progress. */
  onTick?: (run: Run) => void
}

export interface WaitResult {
  run: Run
  /** False when the budget ran out with the run still moving. */
  settled: boolean
}

const defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Poll a run until it reaches a terminal status or the budget runs out.
 *
 * A timed-out poll is not an error and not a success: `settled: false` says
 * the run is still moving, and the caller renders the partial state with that
 * stated. Reporting it as finished would be the lie a spinner makes.
 */
export async function waitForRun({
  transport,
  runId,
  timeoutMs = 60_000,
  intervalMs = 500,
  now = () => Date.now(),
  sleep = defaultSleep,
  onTick,
}: WaitArgs): Promise<WaitResult> {
  const deadline = now() + timeoutMs
  let current = await transport.getRun(runId)

  while (!isTerminal(current.status)) {
    if (now() >= deadline) return { run: current, settled: false }
    await sleep(intervalMs)
    current = await transport.getRun(runId)
    onTick?.(current)
    if (now() >= deadline && !isTerminal(current.status)) {
      return { run: current, settled: false }
    }
  }

  return { run: current, settled: true }
}

/**
 * Read the report for a run that has one.
 *
 * A run that has not finished has no report, and the service says so with a
 * 409. That is an answer, not a failure: this returns `null` so the caller
 * renders the partial run, and returns `null` for any other error too while
 * surfacing the reason, because a console that shows the run without its
 * report is more useful than one that shows an error page.
 */
export async function readReport(
  transport: Transport,
  runId: string,
): Promise<{ report: Report | null; error: string | null }> {
  try {
    return { report: await transport.getReport(runId), error: null }
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 409) {
      return { report: null, error: null }
    }
    return {
      report: null,
      error: cause instanceof Error ? cause.message : 'report request failed',
    }
  }
}

/**
 * Resolve the demo entry to a run that exists, when the transport can.
 *
 * Returns `null` when it cannot — an offline transport, or one without a
 * writable demo path. The caller falls back to bundled fixtures in that case
 * and labels the data accordingly; it must not substitute a fixture run id for
 * a real one.
 */
export async function resolveDemoContext(transport: Transport): Promise<DemoContext | null> {
  if (!transport.getDemoContext) return null
  try {
    return await transport.getDemoContext()
  } catch {
    // A backend that answers `/health` but cannot seed a demo is still usable
    // against fixtures; the console is one click from a demo either way.
    return null
  }
}
