import type { InvestigationStep, StepTreeNode } from './api/investigation'
import { probeTargets } from './api/investigation'
import { formatClock } from './lib/format'

interface Props {
  node: StepTreeNode
  selectedStepId: string | null
  onSelectStep: (stepId: string) => void
  /** Step ids whose subtree is folded away. */
  collapsed: ReadonlySet<string>
  onToggleCollapse: (stepId: string) => void
}

/** Fold the tree into the rows to print, honouring the collapsed set. */
export function visibleRows(
  nodes: readonly StepTreeNode[],
  collapsed: ReadonlySet<string>,
): StepTreeNode[] {
  const rows: StepTreeNode[] = []
  const walk = (list: readonly StepTreeNode[]): void => {
    for (const node of list) {
      rows.push(node)
      if (!collapsed.has(node.step.id)) walk(node.children)
    }
  }
  walk(nodes)
  return rows
}

export function stepStatusClass(status: InvestigationStep['status']): string {
  if (status === 'completed') return 'step__status step__status--done'
  if (status === 'running') return 'step__status step__status--running'
  if (status === 'failed') return 'step__status step__status--failed'
  return 'step__status step__status--pending'
}

const STATUS_MARK: Record<InvestigationStep['status'], string> = {
  completed: '✔',
  running: '▶',
  failed: '✘',
  pending: '·',
}

/**
 * One row of the investigation tree.
 *
 * The status is a labelled chip plus a mark, never colour alone — the same rule
 * the record table's status column follows. The sequence number is printed in
 * the device face because it is a machine-assigned address, and the indentation
 * is a printed rule in the margin rather than a cosmetic inset, so a child reads
 * as *beneath* its parent on the paper.
 */
export function StepRow({
  node,
  selectedStepId,
  onSelectStep,
  collapsed,
  onToggleCollapse,
}: Props): React.JSX.Element {
  const { step, depth, children } = node
  const isCollapsed = collapsed.has(step.id)
  const targets = probeTargets(step)
  const isSelected = selectedStepId === step.id

  return (
    <li className="step" data-kind={step.kind} data-depth={depth}>
      <div
        className={`step__row${isSelected ? ' step__row--on' : ''}`}
        style={{ paddingLeft: `calc(var(--s3) + ${depth} * var(--s4))` }}
      >
        {children.length > 0 ? (
          <button
            type="button"
            className="step__twist"
            aria-expanded={!isCollapsed}
            aria-label={`${isCollapsed ? 'Expand' : 'Collapse'} ${step.title}`}
            onClick={() => onToggleCollapse(step.id)}
          >
            {isCollapsed ? '+' : '−'}
          </button>
        ) : (
          <span className="step__twist step__twist--none" aria-hidden="true">
            ·
          </span>
        )}

        <button
          type="button"
          className="step__open"
          aria-current={isSelected ? 'true' : undefined}
          onClick={() => onSelectStep(step.id)}
        >
          <span className="step__seq u-device">{String(step.sequence).padStart(2, '0')}</span>
          <span className="step__kind">{step.kind}</span>
          <span className="step__title">{step.title}</span>
          {targets.length > 0 && (
            <span className="step__targets u-device">{targets.length} scenario(s)</span>
          )}
        </button>

        <span className={stepStatusClass(step.status)}>
          <span aria-hidden="true">{STATUS_MARK[step.status]}</span> {step.status}
        </span>
        <span className="step__time u-device">{formatClock(step.created_at)}</span>
      </div>
    </li>
  )
}
