<template>
  <div class="space-y-6">
    <!-- Active Proposal Display -->
    <RevoteProposalCard
      v-if="proposal"
      :proposal="proposal"
    />

    <!-- Accept Proposal Button (if user hasn't accepted yet) -->
    <div
      v-if="canAcceptProposal"
      class="flex justify-end"
    >
      <button
        type="button"
        :disabled="isAccepting"
        :class="acceptButtonClasses"
        @click="handleAcceptProposal"
        :aria-busy="isAccepting"
      >
        <svg
          v-if="isAccepting"
          class="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle
            class="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            stroke-width="4"
          ></circle>
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          ></path>
        </svg>
        <svg
          v-else
          class="w-5 h-5 mr-2"
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
        Accept Fresh Assessment Proposal
      </button>
    </div>

    <!-- Re-vote Decision Form (if proposal accepted and user needs to vote) -->
    <div
      v-if="canSubmitRevoteDecision"
      class="bg-white rounded-lg shadow-sm p-6 border-l-4 border-primary"
    >
      <h4 class="text-lg font-semibold text-deep-navy mb-4">
        Submit Your Fresh Assessment
      </h4>

      <form @submit.prevent="handleSubmitDecision">
        <!-- Decision Selection -->
        <div class="mb-4">
          <label class="block text-sm font-semibold text-deep-navy mb-3">
            Decision <span class="text-destructive">*</span>
          </label>
          <div class="space-y-2">
            <label
              v-for="option in decisionOptions"
              :key="option.value"
              class="flex items-center p-3 border rounded-lg cursor-pointer transition-all duration-200"
              :class="getDecisionLabelClasses(option.value)"
            >
              <input
                type="radio"
                :value="option.value"
                v-model="revoteDecision"
                class="h-4 w-4 text-primary focus:ring-ring border-border"
              />
              <span class="ml-3 flex items-center">
                <StatusBadge
                  :status="option.value"
                  variant="decision"
                  size="small"
                  class="mr-2"
                />
                <span class="text-sm font-medium text-deep-navy">{{ option.label }}</span>
              </span>
            </label>
          </div>
        </div>

        <!-- Confidence Level -->
        <div class="mb-4">
          <label for="confidence-level" class="block text-sm font-semibold text-deep-navy mb-2">
            Confidence Level
          </label>
          <select
            id="confidence-level"
            v-model="confidenceLevel"
            class="w-full px-3 py-2 border border-border rounded-lg text-sm text-deep-navy focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent"
          >
            <option value="1">Low</option>
            <option value="2">Medium</option>
            <option value="3">High</option>
          </select>
        </div>

        <!-- Notes -->
        <div class="mb-6">
          <label for="revote-notes" class="block text-sm font-semibold text-deep-navy mb-2">
            Notes (optional)
          </label>
          <textarea
            id="revote-notes"
            v-model="revoteNotes"
            rows="3"
            placeholder="Add any additional notes about your decision..."
            class="w-full px-3 py-2 border border-border rounded-lg text-sm text-deep-navy placeholder-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent resize-none"
          ></textarea>
        </div>

        <!-- Submit Button -->
        <div class="flex justify-end">
          <button
            type="submit"
            :disabled="!isDecisionFormValid || isSubmittingDecision"
            :class="submitDecisionButtonClasses"
            :aria-busy="isSubmittingDecision"
          >
            <svg
              v-if="isSubmittingDecision"
              class="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                class="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="4"
              ></circle>
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            Submit Fresh Assessment
          </button>
        </div>
      </form>
    </div>

    <!-- Already Voted Notice -->
    <div
      v-if="hasAlreadyVoted"
      class="bg-info-light border-l-4 border-info rounded-lg p-4"
    >
      <div class="flex items-start">
        <svg class="w-5 h-5 text-info-dark flex-shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
          <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
        </svg>
        <div class="ml-3 flex-1">
          <p class="text-sm font-medium text-info-dark">Fresh Assessment Submitted</p>
          <p class="text-sm text-cool-grey-dark mt-1">
            You have already submitted your updated assessment. Waiting for other reviewers.
          </p>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <ErrorAlert
      v-if="error"
      variant="error"
      title="Error"
      :message="error"
      dismissible
      @dismiss="error = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { RevoteProposal, DecisionType } from '@/types'
import RevoteProposalCard from './RevoteProposalCard.vue'
import StatusBadge from './StatusBadge.vue'
import ErrorAlert from './ErrorAlert.vue'

interface Props {
  proposal: RevoteProposal | null
  conflictId: string
  currentUserId: string
  hasAlreadyVoted?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  hasAlreadyVoted: false
})

const emit = defineEmits<{
  acceptProposal: [proposalId: string]
  submitDecision: [decision: DecisionType, notes: string | undefined, confidenceLevel: number]
}>()

// State
const isAccepting = ref(false)
const isSubmittingDecision = ref(false)
const revoteDecision = ref<DecisionType | null>(null)
const confidenceLevel = ref<number>(2) // Default to MEDIUM
const revoteNotes = ref('')
const error = ref<string | null>(null)

const decisionOptions = [
  { value: 'INCLUDE' as DecisionType, label: 'Include this result' },
  { value: 'EXCLUDE' as DecisionType, label: 'Exclude this result' },
  { value: 'MAYBE' as DecisionType, label: 'Needs further review' }
]

// Computed properties
const canAcceptProposal = computed(() => {
  if (!props.proposal) return false
  if (props.proposal.status !== 'PROPOSED') return false
  if (props.proposal.is_expired) return false

  // Check if current user has already accepted
  return !props.proposal.accepted_by.some(user => user.id === props.currentUserId)
})

const canSubmitRevoteDecision = computed(() => {
  if (!props.proposal) return false
  if (props.hasAlreadyVoted) return false

  // Can submit if proposal is ACCEPTED or IN_PROGRESS
  return ['ACCEPTED', 'IN_PROGRESS'].includes(props.proposal.status)
})

const isDecisionFormValid = computed(() => {
  return revoteDecision.value !== null
})

const acceptButtonClasses = computed(() => {
  const base = 'inline-flex items-center px-4 py-2 border border-transparent rounded-md text-sm font-medium transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-success'

  if (isAccepting.value) {
    return `${base} text-muted-foreground bg-muted cursor-not-allowed`
  }

  return `${base} text-white bg-success hover:bg-success-dark`
})

const submitDecisionButtonClasses = computed(() => {
  const base = 'inline-flex items-center px-4 py-2 border border-transparent rounded-md text-sm font-medium transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-ring'

  if (!isDecisionFormValid.value || isSubmittingDecision.value) {
    return `${base} text-muted-foreground bg-muted cursor-not-allowed`
  }

  return `${base} text-white bg-primary hover:bg-deep-navy-dark`
})

const getDecisionLabelClasses = (decision: DecisionType) => {
  const base = 'hover:bg-muted/50'
  const selected = revoteDecision.value === decision

  if (selected) {
    const selectedClasses = {
      'INCLUDE': 'border-success bg-success/10',
      'EXCLUDE': 'border-destructive bg-destructive/10',
      'MAYBE': 'border-warning bg-warning/10'
    }
    return `${base} ${selectedClasses[decision]}`
  }

  return `${base} border-border`
}

// Methods
const handleAcceptProposal = async () => {
  if (!props.proposal) return

  isAccepting.value = true
  error.value = null

  try {
    emit('acceptProposal', props.proposal.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to accept proposal'
  } finally {
    isAccepting.value = false
  }
}

const handleSubmitDecision = async () => {
  if (!isDecisionFormValid.value || !revoteDecision.value) return

  isSubmittingDecision.value = true
  error.value = null

  try {
    emit(
      'submitDecision',
      revoteDecision.value,
      revoteNotes.value.trim() || undefined,
      confidenceLevel.value
    )

    // Reset form after successful submission
    revoteDecision.value = null
    revoteNotes.value = ''
    confidenceLevel.value = 2
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to submit decision'
  } finally {
    isSubmittingDecision.value = false
  }
}
</script>
