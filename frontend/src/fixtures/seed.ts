/**
 * Deterministic pseudo-random source for the bundled fixtures.
 *
 * Fixtures must be byte-identical on every load, so nothing in `src/fixtures`
 * may call `Math.random` or `Date.now`. This generator is seeded from a
 * literal and produces the same stream forever; `tsconfig.app.json` does not
 * ban those globals automatically, so the discipline is enforced by the
 * fixture tests instead (see `src/fixtures/fixtures.test.ts`).
 */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return function next(): number {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Rounded to `places` decimals, so serialised fixtures stay stable. */
export function round(value: number, places = 3): number {
  const factor = 10 ** places
  return Math.round(value * factor) / factor
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
