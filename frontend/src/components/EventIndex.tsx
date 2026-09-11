import { useEffect, useMemo, useRef, useState } from 'react'
import type { ProgressEvent } from '../api/types'
import type { ScenarioId } from '../fixtures/scenarios'
import { timelineFor } from '../fixtures/timeline'
import { formatClock } from '../lib/format'

interface Props {
  scenarioId: ScenarioId
  /** Jump the record table to the case an event refers to. */
  onJumpToCase: (caseNumber: number) => void
  /** Case number currently highlighted by an external selection, if any. */
  activeCaseNumber: number | null
}

/** Replay pacing. Fast enough to be watched, slow enough to be read. */
const TICK_MS = 90
const EVENTS_PER_TICK = 3

const TYPE_CLASS: Record<ProgressEvent['type'], string> = {
  'run.started': '',
  'task.created': '',
  'task.started': '',
  'evidence.created': '',
  'task.completed': '',
  'finding.created': 'event--finding',
  'run.completed': 'event--complete',
  'run.failed': 'event--finding',
}

/**
 * The event index — the tick margin of the tape, made interactive.
 *
 * A raise from the teletext challenger: every event carries a keyed address
 * that can be pressed to jump straight to the case it names. The list is the
 * machine's record of the run, not a decoration beside it.
 */
export function EventIndex({ scenarioId, onJumpToCase, activeCaseNumber }: Props): React.JSX.Element {
  const all = useMemo(() => timelineFor(scenarioId), [scenarioId])
  const [shown, setShown] = useState(0)
  const [paused, setPaused] = useState(false)
  const listRef = useRef<HTMLOListElement>(null)

  // A new run restarts the transcript from the top.
  useEffect(() => {
    setShown(0)
    setPaused(false)
  }, [scenarioId])

  useEffect(() => {
    if (paused || shown >= all.length) return
    const timer = setTimeout(() => {
      setShown((current) => Math.min(current + EVENTS_PER_TICK, all.length))
    }, TICK_MS)
    return () => clearTimeout(timer)
  }, [shown, paused, all.length])

  const visible = all.slice(0, shown)
  const running = shown < all.length

  // Keep the newest entry in view without stealing the scroll from a reader.
  useEffect(() => {
    const node = listRef.current
    if (!node || paused) return
    node.scrollTop = node.scrollHeight
  }, [shown, paused])

  const last = visible[visible.length - 1]
  const elapsed = last ? last.offsetMs : 0
  const elapsedStamp = `00:${String(Math.floor(elapsed / 60000)).padStart(2, '0')}:${String(
    Math.floor((elapsed % 60000) / 1000),
  ).padStart(2, '0')}`

  return (
    <section className="events" aria-label="Run event stream">
      <div className="panel__title">
        <span className="u-label">Run progress</span>
        <span className="u-micro">
          {running ? `running · ${shown}/${all.length}` : `complete · ${all.length} events`}
        </span>
      </div>

      <div className="filters" style={{ paddingBlock: 'var(--s1)' }}>
        <button
          type="button"
          className="rocker__pos"
          style={{ border: 'var(--rule)' }}
          onClick={() => setPaused((value) => !value)}
          aria-pressed={paused}
        >
          {paused ? 'Resume' : 'Pause'}
        </button>
        <button
          type="button"
          className="rocker__pos"
          style={{ border: 'var(--rule)' }}
          onClick={() => {
            setShown(all.length)
            setPaused(false)
          }}
          disabled={!running}
        >
          Step to end
        </button>
        <span className="u-micro" style={{ marginLeft: 'auto' }}>
          t + {elapsedStamp}
        </span>
      </div>

      <ol className="events__list" ref={listRef}>
        {visible.map((entry) => {
          const data = entry.event.data
          const caseNumber =
            typeof data.case === 'string' ? Number(data.case) : typeof data.case === 'number' ? data.case : null
          const isActive = caseNumber !== null && caseNumber === activeCaseNumber
          return (
            <li
              key={`${entry.scenarioId}-${entry.event.sequence}`}
              className={`event ${TYPE_CLASS[entry.event.type]}`}
              style={isActive ? { background: 'var(--ground)' } : undefined}
            >
              {caseNumber === null ? (
                <span className="event__key event__key--none" aria-hidden="true">
                  —
                </span>
              ) : (
                <button
                  type="button"
                  className="event__key"
                  onClick={() => onJumpToCase(caseNumber)}
                  title={`Open case ${String(caseNumber).padStart(2, '0')}`}
                >
                  {String(caseNumber).padStart(2, '0')}
                </button>
              )}
              <span className="event__time">{formatClock(entry.event.created_at)}</span>
              <span className="event__type">{entry.event.type.replace('.', ' · ')}</span>
              <span className="event__message">{entry.event.message}</span>
            </li>
          )
        })}
      </ol>

      <div className="legend" style={{ borderTop: 'var(--rule-ink)' }}>
        <span className="u-micro">
          Events replay from the frozen transcript for this scenario. The keyed number on the left
          jumps the record to that case.
        </span>
      </div>
    </section>
  )
}
