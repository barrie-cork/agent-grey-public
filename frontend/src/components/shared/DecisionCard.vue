<template>
  <div
    :class="cardClasses"
    role="article"
    :aria-label="`${reviewerName}'s decision: ${decision.decision}`"
  >
    <div class="flex items-center justify-between mb-3">
      <h5 class="text-deep-navy font-semibold text-lg">
        {{ reviewerName }}
      </h5>
      <StatusBadge
        :status="decision.decision"
        variant="decision"
        size="small"
      />
    </div>

    <div v-if="decision.exclusion_reason" class="text-sm text-cool-grey mb-2">
      <strong class="text-deep-navy">Reason:</strong> {{ decision.exclusion_reason }}
    </div>

    <div v-if="decision.notes" class="text-sm text-cool-grey mb-3">
      <strong class="text-deep-navy">Notes:</strong> {{ decision.notes }}
    </div>

    <div class="flex items-center justify-between text-xs text-cool-grey-dark">
      <time :datetime="decision.decided_at">
        {{ formattedDate }}
      </time>
      <span v-if="decision.confidence_level" class="inline-flex items-center">
        Confidence: {{ confidenceText }}
      </span>
    </div>

    <div v-if="showMetadata" class="mt-3 pt-3 border-t border-cool-grey-light">
      <div class="grid grid-cols-2 gap-2 text-xs text-cool-grey">
        <div v-if="decision.time_spent_seconds">
          <strong>Time spent:</strong> {{ formattedTimeSpent }}
        </div>
        <div v-if="decision.report_accessed !== undefined">
          <strong>Report accessed:</strong> {{ decision.report_accessed ? 'Yes' : 'No' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import type { ReviewerDecision, DecisionType } from '@/types'
import StatusBadge from './StatusBadge.vue'

interface Props {
  decision: ReviewerDecision
  isBlinded?: boolean
  showMetadata?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isBlinded: false,
  showMetadata: false
})

// Runtime validation to ensure blinding is explicitly considered
onMounted(() => {
  // Development-only: throw error to catch issues early
  if (import.meta.env.DEV && props.isBlinded === undefined) {
    console.error(
      'DecisionCard: isBlinded prop must be explicitly set to ensure PRISMA 2020 compliance. ' +
      'Always specify isBlinded={true|false} based on session blinding status. ' +
      'This will become a runtime error in a future version.'
    );
  }

  // Production: warn but don't break
  if (!import.meta.env.DEV && props.isBlinded === undefined) {
    console.warn(
      'DecisionCard: isBlinded prop should be explicitly set to ensure PRISMA 2020 compliance.'
    );
  }
})

const cardClasses = computed(() => {
  const borderColors: Record<DecisionType, string> = {
    'INCLUDE': 'border-decision-include',
    'EXCLUDE': 'border-decision-exclude',
    'MAYBE': 'border-decision-maybe'
  }

  const borderColor = borderColors[props.decision.decision] || 'border-cool-grey'

  return `bg-white rounded-card shadow-card p-card-padding border-l-4 ${borderColor}`
})

const reviewerName = computed(() => {
  if (props.isBlinded) {
    return 'Blinded Reviewer'
  }
  const user = props.decision.reviewer
  if (user.first_name || user.last_name) {
    return `${user.first_name} ${user.last_name}`.trim()
  }
  return user.username
})

const formattedDate = computed(() => {
  const date = new Date(props.decision.decided_at)
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
})

const confidenceText = computed(() => {
  const levels: Record<string, string> = {
    'LOW': 'Low',
    'MEDIUM': 'Medium',
    'HIGH': 'High'
  }
  return levels[props.decision.confidence_level] || props.decision.confidence_level
})

const formattedTimeSpent = computed(() => {
  if (!props.decision.time_spent_seconds) return ''

  const seconds = props.decision.time_spent_seconds
  if (seconds < 60) {
    return `${seconds}s`
  }

  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60

  if (minutes < 60) {
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
  }

  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`
})
</script>
