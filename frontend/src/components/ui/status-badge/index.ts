import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as StatusBadge } from './StatusBadge.vue'

export const statusBadgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-md border font-medium',
  {
    variants: {
      status: {
        // Lowercase versions (Phase 04 standard)
        conflict: 'bg-[color:var(--color-status-escalated-light)] text-[color:var(--color-status-escalated-dark)] border-[color:var(--color-status-escalated)]',
        proposal: 'bg-[color:var(--color-status-discussion-light)] text-[color:var(--color-status-discussion-dark)] border-[color:var(--color-status-discussion)]',
        decision: 'bg-[color:var(--color-decision-include-light)] text-[color:var(--color-decision-include-dark)] border-[color:var(--color-decision-include)]',
        include: 'bg-[color:var(--color-decision-include-light)] text-[color:var(--color-decision-include-dark)] border-[color:var(--color-decision-include)]',
        exclude: 'bg-[color:var(--color-decision-exclude-light)] text-[color:var(--color-decision-exclude-dark)] border-[color:var(--color-decision-exclude)]',
        maybe: 'bg-[color:var(--color-decision-maybe-light)] text-[color:var(--color-decision-maybe-dark)] border-[color:var(--color-decision-maybe)]',
        pending: 'bg-[color:var(--color-status-pending-light)] text-[color:var(--color-status-pending-dark)] border-[color:var(--color-status-pending)]',
        active: 'bg-[color:var(--color-accent)] text-white border-[color:var(--color-accent)]',
        inactive: 'bg-[color:var(--color-neutral-200)] text-[color:var(--color-neutral-600)] border-[color:var(--color-neutral-400)]',

        // Uppercase versions (backward compatibility with shared StatusBadge)
        // Decision types
        INCLUDE: 'bg-[color:var(--color-decision-include-light)] text-[color:var(--color-decision-include-dark)] border-[color:var(--color-decision-include)]',
        EXCLUDE: 'bg-[color:var(--color-decision-exclude-light)] text-[color:var(--color-decision-exclude-dark)] border-[color:var(--color-decision-exclude)]',
        MAYBE: 'bg-[color:var(--color-decision-maybe-light)] text-[color:var(--color-decision-maybe-dark)] border-[color:var(--color-decision-maybe)]',

        // Conflict statuses
        PENDING: 'bg-[color:var(--color-status-pending-light)] text-[color:var(--color-status-pending-dark)] border-[color:var(--color-status-pending)]',
        IN_DISCUSSION: 'bg-[color:var(--color-status-discussion-light)] text-[color:var(--color-status-discussion-dark)] border-[color:var(--color-status-discussion)]',
        RESOLVED: 'bg-[color:var(--color-status-resolved-light)] text-[color:var(--color-status-resolved-dark)] border-[color:var(--color-status-resolved)]',
        ESCALATED: 'bg-[color:var(--color-status-escalated-light)] text-[color:var(--color-status-escalated-dark)] border-[color:var(--color-status-escalated)]',

        // Proposal statuses
        PROPOSED: 'bg-[color:var(--color-status-pending-light)] text-[color:var(--color-status-pending-dark)] border-[color:var(--color-status-pending)]',
        ACCEPTED: 'bg-[color:var(--color-status-discussion-light)] text-[color:var(--color-status-discussion-dark)] border-[color:var(--color-status-discussion)]',
        IN_PROGRESS: 'bg-[color:var(--color-accent)] text-white border-[color:var(--color-accent)]',
        COMPLETED: 'bg-[color:var(--color-status-resolved-light)] text-[color:var(--color-status-resolved-dark)] border-[color:var(--color-status-resolved)]',
        REJECTED: 'bg-[color:var(--color-status-escalated-light)] text-[color:var(--color-status-escalated-dark)] border-[color:var(--color-status-escalated)]',
        EXPIRED: 'bg-[color:var(--color-neutral-200)] text-[color:var(--color-neutral-600)] border-[color:var(--color-neutral-400)]'
      },
      size: {
        // New compact sizes
        sm: 'text-xs px-2 py-0.5',
        md: 'text-sm px-2.5 py-1',
        lg: 'text-base px-3 py-1.5',
        // Backward compatibility with old component
        small: 'text-xs px-2.5 py-0.5',
        medium: 'text-sm px-3 py-1',
        large: 'text-base px-4 py-1.5'
      }
    },
    defaultVariants: {
      status: 'pending',
      size: 'md'
    }
  }
)

export type StatusBadgeVariants = VariantProps<typeof statusBadgeVariants>

export type StatusType = NonNullable<StatusBadgeVariants['status']>
export type SizeType = NonNullable<StatusBadgeVariants['size']>
