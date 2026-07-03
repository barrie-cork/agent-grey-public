<template>
  <div class="mt-3 p-4 bg-cool-grey-lighter border border-cool-grey-light rounded-lg">
    <!-- Header -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <BarChart3 class="h-4 w-4 text-deep-navy" />
        <span class="text-xs font-bold uppercase tracking-widest text-deep-navy">Straw Poll</span>
      </div>
      <span v-if="vote.is_closed" class="text-[10px] font-bold uppercase tracking-widest text-cool-grey">Closed</span>
    </div>

    <!-- Vote Buttons (if user hasn't voted and poll is open) -->
    <div v-if="!hasVoted && !vote.is_closed" class="grid grid-cols-3 gap-2 mb-3">
      <button
        @click="$emit('respond', vote.id, 'INCLUDE')"
        :disabled="isSubmitting"
        class="flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold rounded border border-success/30 text-success-dark bg-success/5 hover:bg-success/15 transition-colors"
      >
        <CheckCircle class="h-3.5 w-3.5" /> Include
      </button>
      <button
        @click="$emit('respond', vote.id, 'EXCLUDE')"
        :disabled="isSubmitting"
        class="flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold rounded border border-destructive/30 text-destructive bg-destructive/5 hover:bg-destructive/15 transition-colors"
      >
        <XCircle class="h-3.5 w-3.5" /> Exclude
      </button>
      <button
        @click="$emit('respond', vote.id, 'MAYBE')"
        :disabled="isSubmitting"
        class="flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold rounded border border-warning/30 text-warning-dark bg-warning/5 hover:bg-warning/15 transition-colors"
      >
        <HelpCircle class="h-3.5 w-3.5" /> Maybe
      </button>
    </div>

    <!-- Results Summary -->
    <div v-if="vote.results_summary.total > 0" class="space-y-2">
      <div class="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-cool-grey">
        <span>{{ vote.results_summary.total }} vote{{ vote.results_summary.total !== 1 ? 's' : '' }}</span>
        <span v-if="hasVoted" class="text-deep-navy">You voted</span>
      </div>

      <!-- Bar visualisation -->
      <div class="flex h-2 rounded-full overflow-hidden bg-cool-grey-light">
        <div
          v-if="vote.results_summary.include > 0"
          class="bg-success transition-all"
          :style="{ width: `${(vote.results_summary.include / vote.results_summary.total) * 100}%` }"
        ></div>
        <div
          v-if="vote.results_summary.exclude > 0"
          class="bg-destructive transition-all"
          :style="{ width: `${(vote.results_summary.exclude / vote.results_summary.total) * 100}%` }"
        ></div>
        <div
          v-if="vote.results_summary.maybe > 0"
          class="bg-warning transition-all"
          :style="{ width: `${(vote.results_summary.maybe / vote.results_summary.total) * 100}%` }"
        ></div>
      </div>

      <!-- Legend -->
      <div class="flex items-center gap-4 text-[10px] text-cool-grey">
        <span v-if="vote.results_summary.include > 0" class="flex items-center gap-1">
          <span class="inline-block w-2 h-2 rounded-full bg-success"></span>
          Include ({{ vote.results_summary.include }})
        </span>
        <span v-if="vote.results_summary.exclude > 0" class="flex items-center gap-1">
          <span class="inline-block w-2 h-2 rounded-full bg-destructive"></span>
          Exclude ({{ vote.results_summary.exclude }})
        </span>
        <span v-if="vote.results_summary.maybe > 0" class="flex items-center gap-1">
          <span class="inline-block w-2 h-2 rounded-full bg-warning"></span>
          Maybe ({{ vote.results_summary.maybe }})
        </span>
      </div>
    </div>

    <!-- No votes yet -->
    <div v-else-if="hasVoted" class="text-xs text-cool-grey italic">
      Waiting for other reviewers to respond...
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BarChart3, CheckCircle, XCircle, HelpCircle } from 'lucide-vue-next'
import type { InDiscussionVote } from '@/types'

interface Props {
  vote: InDiscussionVote
  currentUserId: string
  isSubmitting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isSubmitting: false
})

defineEmits<{
  respond: [voteId: string, decision: string]
}>()

const hasVoted = computed(() => {
  return props.vote.responses.some(r => r.reviewer.id === props.currentUserId)
})
</script>
