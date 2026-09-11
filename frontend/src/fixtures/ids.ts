/**
 * Fixed identifiers and timestamps for the bundled demo fixtures.
 *
 * Literals only. A fixture that reads the clock or a random source produces a
 * different demo on every reload, which breaks the reproducibility claim the
 * product is making. Every value here is frozen.
 */

export const PROJECT_ID = '3f8c1d20-5b47-4a9e-9c1f-2d6e7a8b0c11'
export const RUN_A_ID = 'a4f1c8e2-7d35-4b90-8e21-5f6a9c3d0b47'
export const RUN_B_ID = 'b7e2a5c9-1f48-4d63-9a07-3c8b5e2f6d94'
export const RUN_C_ID = 'c9d4b7a1-3e62-4f85-b1d0-7a2c6e9f4b58'
export const REPORT_A_ID = 'd1a7f3c5-9b24-4e78-8f16-2c5d9a7e3b60'
export const REPORT_B_ID = 'e3b9d5f7-2c46-4a81-9d37-6f1e8b4c2a95'
export const REPORT_C_ID = 'f5c1e7a9-8d63-4b29-a5f4-9e2b7d1c6a08'

/**
 * Per-case id prefixes. Each run gets its own prefix so a `TestCase.id` is
 * globally unique, as the contract implies by keying `Evidence` on it.
 */
export const PREFIX = {
  A: '1a',
  B: '2b',
  C: '3c',
} as const

/**
 * The demo's wall clock. Every `created_at` in the fixtures is this instant
 * plus an offset, so the whole run renders as one continuous ~2m40s session
 * and the timestamps never drift.
 */
export const BASE_TIME = '2026-09-11T08:12:04.000Z'

/** `BASE_TIME` + `seconds`, as an ISO-8601 UTC string. */
export function at(seconds: number): string {
  const base = Date.parse(BASE_TIME)
  const ms = base + Math.round(seconds * 1000)
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/**
 * UUID-shaped stable id for case `n` of run `prefix`.
 *
 * Shape-valid, not random, and reversible: `caseNumberFromId` reads the case
 * number back out of the last group. Case 3 and case 30 must not collide, so
 * the final group is padded rather than sliced.
 */
export function caseId(prefix: string, n: number): string {
  const padded = String(n).padStart(2, '0')
  return `${prefix}${padded}-4c7b-4e21-9f83-6a1d5b9e0c${padded}`
}

/** Inverse of `caseId`. Returns null when the id is not one of ours. */
export function caseNumberFromId(id: string): number | null {
  const match = /^[0-9a-f]{4}-4c7b-4e21-9f83-6a1d5b9e0c(\d{2})$/.exec(id)
  return match ? Number(match[1]) : null
}

export function evidenceId(prefix: string, n: number): string {
  const padded = String(n).padStart(2, '0')
  return `${prefix}${padded}-8e14-4d97-b2c5-3f7a1e6b9d${padded}`
}

export function findingId(n: number): string {
  const padded = String(n).padStart(2, '0')
  return `4b7e2a91-6c${padded}-4f36-8d05-9b3a7c2e5107`
}
