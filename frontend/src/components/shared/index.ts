/**
 * Shared Vue 3 Components for Consensus Discussion Interface
 * Phase 6: Vue Component Library
 *
 * This file exports all shared components for easy importing:
 *
 * import { ConflictHeader, DecisionCard, StatusBadge } from '@/components/shared'
 */

// Utility Components
export { default as LoadingSpinner } from './LoadingSpinner.vue'
export { default as ErrorAlert } from './ErrorAlert.vue'
export { default as StatusBadge } from './StatusBadge.vue'

// Display Components
export { default as ConflictHeader } from './ConflictHeader.vue'
export { default as DecisionCard } from './DecisionCard.vue'

// Comment System Components
export { default as Comment } from './Comment.vue'
export { default as CommentForm } from './CommentForm.vue'
export { default as CommentThread } from './CommentThread.vue'

// Re-Vote Components
export { default as RevoteProposalCard } from './RevoteProposalCard.vue'
export { default as RevotePanel } from './RevotePanel.vue'

// Discussion Voting Components
export { default as VoteCard } from './VoteCard.vue'

// Dialog Components
export { default as RationaleDialog } from './RationaleDialog.vue'

// Feedback Widget
export { default as FeedbackWidget } from './FeedbackWidget.vue'

// Re-export Phase 04 LoadingState (preferred over deprecated LoadingSpinner)
export { LoadingState } from '@/components/ui/loading-state'
