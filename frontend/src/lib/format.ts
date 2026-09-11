import type { MetricValue, Severity } from '../api/types'

/**
 * A metric's `unit` is `''` when the value is a 0..1 ratio and a suffix like
 * `' ms'` when it is already in display units. Ratios render as percentages;
 * everything else renders with its own unit.
 */
export function formatMetricValue(metric: MetricValue, value: number): string {
  if (metric.unit === '') return `${Math.round(value * 100)}%`
  return `${Math.round(value)}${metric.unit}`
}

export type MoveDirection = 'better' | 'worse' | 'flat'

export function moveDirection(metric: MetricValue, baseline: number, candidate: number): MoveDirection {
  const raw = candidate - baseline
  if (Math.abs(raw) < 1e-9) return 'flat'
  const improved = metric.direction === 'lower' ? raw < 0 : raw > 0
  return improved ? 'better' : 'worse'
}

/** Signed change in display units. Ratios are reported in percentage points. */
export function formatMetricDelta(metric: MetricValue, baseline: number, candidate: number): string {
  const raw = candidate - baseline
  const sign = raw > 0 ? '+' : raw < 0 ? '−' : ''
  if (metric.unit === '') return `${sign}${Math.abs(Math.round(raw * 100))} pp`
  return `${sign}${Math.abs(Math.round(raw))}${metric.unit.trim()}`
}

/** Score on the 0..1 scale, always two decimals so columns align. */
export function formatScore(value: number): string {
  return value.toFixed(2)
}

export function formatSignedScore(value: number): string {
  if (Math.abs(value) < 1e-9) return '0.00'
  return `${value > 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}`
}

export function formatPercent(value: number, places = 0): string {
  return `${(value * 100).toFixed(places)}%`
}

/** `2026-09-11T08:12:04.000Z` -> `08:12:04Z`. The tape records UTC. */
export function formatClock(iso: string): string {
  const match = /T(\d{2}:\d{2}:\d{2})/.exec(iso)
  return match ? `${match[1]}Z` : iso
}

/** `2026-09-11T08:12:04Z` -> `2026-09-11 08:12:04Z`. */
export function formatStamp(iso: string): string {
  return iso.replace('T', ' ').replace(/\.\d{3}Z$/, 'Z')
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

export const SEVERITY_ORDER: readonly Severity[] = ['critical', 'high', 'medium', 'low', 'info']

export function severityRank(severity: Severity): number {
  return SEVERITY_ORDER.indexOf(severity)
}

/** `candidate` -> `v1.5.0-rc1` style label is supplied by the scenario; this
 * only shortens a long version string for a narrow column. */
export function shortVersion(version: string): string {
  return version.length > 12 ? `${version.slice(0, 11)}…` : version
}
