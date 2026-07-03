<template>
  <div
    :class="cardClasses"
    role="article"
    :aria-label="`Re-vote proposal by ${proposerName}`"
  >
    <!-- Header -->
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-deep-navy">
        📢 Fresh Assessment Proposed
      </h3>
      <StatusBadge
        :status="proposal.status"
        variant="proposal"
        size="small"
      />
    </div>

    <!-- Expiry Warning (if PROPOSED and not expired) -->
    <div
      v-if="proposal.status === 'PROPOSED' && !proposal.is_expired && timeUntilExpiry"
      class="mb-4"
    >
      <div class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-warning text-deep-navy">
        <svg class="w-4 h-4 mr-1.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/>
        </svg>
        Expires {{ timeUntilExpiry }}
      </div>
    </div>

    <!-- Expired Notice -->
    <div
      v-if="proposal.is_expired"
      class="mb-4 bg-muted border border-border rounded-lg p-3"
    >
      <p class="text-sm text-cool-grey">
        This proposal expired on {{ formattedExpiryDate }} without being accepted by all reviewers.
      </p>
    </div>

    <!-- Proposer Info -->
    <div class="mb-4">
      <p class="text-sm text-cool-grey mb-1">
        <strong class="text-deep-navy">Proposed by:</strong> {{ proposerName }}
      </p>
      <p class="text-sm text-cool-grey">
        <strong class="text-deep-navy">Proposed at:</strong> {{ formattedProposedDate }}
      </p>
    </div>

    <!-- Rationale -->
    <div class="mb-4">
      <p class="text-sm font-semibold text-deep-navy mb-2">Rationale:</p>
      <div class="prose prose-sm max-w-none text-cool-grey-dark bg-white rounded-lg p-3 border border-border">
        <div v-html="sanitizedRationale"></div>
      </div>
    </div>

    <!-- Acceptance Status -->
    <div v-if="showAcceptanceStatus" class="mb-4">
      <p class="text-sm font-semibold text-deep-navy mb-2">Acceptance Status:</p>
      <div class="flex flex-wrap items-center gap-4">
        <div
          v-for="reviewer in proposal.acceptance_required_from"
          :key="reviewer.id"
          class="flex items-center"
        >
          <svg
            v-if="hasAccepted(reviewer.id)"
            class="w-5 h-5 text-success mr-1.5"
            fill="currentColor"
            viewBox="0 0 20 20"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clip-rule="evenodd"
            />
          </svg>
          <svg
            v-else
            class="w-5 h-5 text-cool-grey mr-1.5"
            fill="currentColor"
            viewBox="0 0 20 20"
            aria-hidden="true"
          >
            <path
              fill-rule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
              clip-rule="evenodd"
            />
          </svg>
          <span class="text-sm" :class="hasAccepted(reviewer.id) ? 'text-cool-grey-dark' : 'text-cool-grey'">
            {{ getReviewerName(reviewer) }}{{ hasAccepted(reviewer.id) ? '' : ' (waiting)' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Progress (if IN_PROGRESS) -->
    <div v-if="proposal.status === 'IN_PROGRESS'" class="mb-4">
      <div class="flex items-center justify-between mb-2">
        <p class="text-sm font-semibold text-deep-navy">Fresh Assessment Progress:</p>
        <span class="text-xs text-cool-grey">{{ acceptanceProgress }}</span>
      </div>
      <div class="w-full bg-muted rounded-full h-2">
        <div
          class="bg-primary rounded-full h-2 transition-all duration-300"
          :style="{ width: progressPercentage }"
        ></div>
      </div>
    </div>

    <!-- Completed Message -->
    <div
      v-if="proposal.status === 'COMPLETED'"
      class="bg-success-light border-l-4 border-success rounded-lg p-4"
    >
      <div class="flex items-start">
        <svg class="w-5 h-5 text-success flex-shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
        </svg>
        <div class="ml-3 flex-1">
          <p class="text-sm font-medium text-success-dark">Fresh Assessment Complete</p>
          <p class="text-sm text-cool-grey-dark mt-1">All reviewers have submitted their updated assessments.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { RevoteProposal, User } from '@/types'
import StatusBadge from './StatusBadge.vue'

interface Props {
  proposal: RevoteProposal
}

const props = defineProps<Props>()

const cardClasses = computed(() => {
  const base = 'rounded-lg shadow-sm p-6 mb-6'

  if (props.proposal.is_expired || props.proposal.status === 'REJECTED') {
    return `${base} bg-muted border-l-4 border-muted-foreground`
  }

  if (props.proposal.status === 'ACCEPTED' || props.proposal.status === 'COMPLETED') {
    return `${base} bg-success-light border-l-4 border-success`
  }

  return `${base} bg-warning-light border-l-4 border-warning`
})

const proposerName = computed(() => {
  const proposer = props.proposal.proposed_by
  if (proposer.first_name || proposer.last_name) {
    return `${proposer.first_name} ${proposer.last_name}`.trim()
  }
  return proposer.username
})

const formattedProposedDate = computed(() => {
  const date = new Date(props.proposal.proposed_at)
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
})

const formattedExpiryDate = computed(() => {
  const date = new Date(props.proposal.expires_at)
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
})

const timeUntilExpiry = computed(() => {
  if (props.proposal.is_expired) return null

  const now = new Date()
  const expiry = new Date(props.proposal.expires_at)
  const diffMs = expiry.getTime() - now.getTime()

  if (diffMs <= 0) return null

  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))

  if (diffHours >= 24) {
    const days = Math.floor(diffHours / 24)
    return `in ${days} day${days > 1 ? 's' : ''}`
  }

  if (diffHours > 0) {
    return `in ${diffHours} hour${diffHours > 1 ? 's' : ''}`
  }

  return `in ${diffMins} minute${diffMins > 1 ? 's' : ''}`
})

const sanitizedRationale = computed(() => {
  marked.setOptions({
    breaks: true,
    gfm: true
  })

  const html = marked.parse(props.proposal.rationale) as string

  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre'],
    ALLOWED_ATTR: ['href', 'target', 'rel']
  })
})

const showAcceptanceStatus = computed(() => {
  return ['PROPOSED', 'ACCEPTED', 'IN_PROGRESS'].includes(props.proposal.status)
})

const hasAccepted = (reviewerId: string): boolean => {
  return props.proposal.accepted_by.some(reviewer => reviewer.id === reviewerId)
}

const getReviewerName = (reviewer: User): string => {
  if (reviewer.first_name || reviewer.last_name) {
    return `${reviewer.first_name} ${reviewer.last_name}`.trim()
  }
  return reviewer.username
}

const acceptanceProgress = computed(() => {
  const total = props.proposal.acceptance_required_from.length
  const accepted = props.proposal.accepted_by.length
  return `${accepted} / ${total} accepted`
})

const progressPercentage = computed(() => {
  const total = props.proposal.acceptance_required_from.length
  if (total === 0) return '0%'
  const accepted = props.proposal.accepted_by.length
  return `${(accepted / total) * 100}%`
})
</script>
