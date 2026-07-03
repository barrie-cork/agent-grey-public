<script setup lang="ts">
import { computed } from 'vue'
import type { HTMLAttributes } from 'vue'
import { CheckCircle, XCircle, HelpCircle, Clock, AlertTriangle, Activity, CircleOff, MessageSquare, PlayCircle } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import { statusBadgeVariants, type StatusType, type SizeType } from '.'

interface Props {
  status?: StatusType
  size?: SizeType
  showIcon?: boolean
  class?: HTMLAttributes['class']
  /** @deprecated Use status prop directly. Kept for backward compatibility. */
  variant?: 'conflict' | 'proposal' | 'decision'
}

const props = withDefaults(defineProps<Props>(), {
  status: 'pending',
  size: 'md',
  showIcon: true
})

const iconComponent = computed(() => {
  const iconMap: Record<string, typeof CheckCircle> = {
    // Lowercase
    include: CheckCircle,
    exclude: XCircle,
    maybe: HelpCircle,
    conflict: AlertTriangle,
    pending: Clock,
    proposal: HelpCircle,
    decision: CheckCircle,
    active: Activity,
    inactive: CircleOff,
    // Uppercase decision types
    INCLUDE: CheckCircle,
    EXCLUDE: XCircle,
    MAYBE: HelpCircle,
    // Uppercase conflict statuses
    PENDING: Clock,
    IN_DISCUSSION: MessageSquare,
    RESOLVED: CheckCircle,
    ESCALATED: AlertTriangle,
    // Uppercase proposal statuses
    PROPOSED: Clock,
    ACCEPTED: MessageSquare,
    IN_PROGRESS: PlayCircle,
    COMPLETED: CheckCircle,
    REJECTED: AlertTriangle,
    EXPIRED: CircleOff
  }
  return iconMap[props.status as string] || Clock
})

const iconSize = computed(() => {
  const sizeMap: Record<string, number> = {
    sm: 12,
    md: 14,
    lg: 16,
    small: 12,
    medium: 14,
    large: 16
  }
  return sizeMap[props.size as string] || 14
})

const displayText = computed(() => {
  const textMap: Record<string, string> = {
    // Lowercase
    conflict: 'Conflict',
    proposal: 'Proposal',
    decision: 'Decision',
    include: 'Include',
    exclude: 'Exclude',
    maybe: 'Maybe',
    pending: 'Pending',
    active: 'Active',
    inactive: 'Inactive',
    // Uppercase decision types
    INCLUDE: 'Include',
    EXCLUDE: 'Exclude',
    MAYBE: 'Maybe',
    // Uppercase conflict statuses
    PENDING: 'Pending',
    IN_DISCUSSION: 'In Discussion',
    RESOLVED: 'Resolved',
    ESCALATED: 'Escalated',
    // Uppercase proposal statuses
    PROPOSED: 'Proposed',
    ACCEPTED: 'Accepted',
    IN_PROGRESS: 'In Progress',
    COMPLETED: 'Completed',
    REJECTED: 'Rejected',
    EXPIRED: 'Expired'
  }
  return textMap[props.status as string] || (props.status as string)
})

const ariaLabel = computed(() => `Status: ${displayText.value}`)
</script>

<template>
  <span
    :class="cn(statusBadgeVariants({ status, size }), props.class)"
    :aria-label="ariaLabel"
  >
    <component
      :is="iconComponent"
      v-if="showIcon"
      :size="iconSize"
      aria-hidden="true"
    />
    <slot>{{ displayText }}</slot>
  </span>
</template>
