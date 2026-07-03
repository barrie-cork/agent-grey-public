<template>
  <div
    :class="[
      'bg-white rounded-card shadow-card p-card-padding mb-section-gap',
      slaInfo?.is_overdue || slaInfo?.is_critical ? 'ring-2 ring-alert-danger' :
      slaInfo?.is_approaching ? 'ring-2 ring-alert-warning' : ''
    ]"
  >
    <!-- Result Title -->
    <h2 class="text-2xl font-bold text-deep-navy mb-3">
      {{ result.title }}
    </h2>

    <!-- Metadata Badges -->
    <div class="flex flex-wrap items-center gap-2 mb-4">
      <span
        v-if="result.result_type"
        class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-info-light text-info-dark border border-info"
      >
        {{ result.result_type }}
      </span>

      <span
        v-if="result.source_name"
        class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-success-light text-success-dark border border-success"
      >
        {{ result.source_name }}
      </span>

      <span
        class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-alert-danger-light text-alert-danger-dark border border-alert-danger"
      >
        ⚠️ Discussion Needed
      </span>

      <span
        v-if="conflictType"
        class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-alert-warning-light text-alert-warning-dark border border-alert-warning"
      >
        {{ formatConflictType(conflictType) }}
      </span>
    </div>

    <!-- Snippet -->
    <div
      v-if="result.snippet"
      class="text-sm text-cool-grey mb-4 line-clamp-3"
      :title="result.snippet"
    >
      {{ result.snippet }}
    </div>

    <!-- Authors and Date -->
    <div v-if="result.authors || result.date_published" class="text-sm text-cool-grey mb-4">
      <span v-if="result.authors" class="mr-4">
        <strong class="text-deep-navy">Authors:</strong> {{ result.authors }}
      </span>
      <span v-if="result.date_published">
        <strong class="text-deep-navy">Published:</strong> {{ formattedPublishDate }}
      </span>
    </div>

    <!-- Full Document Link and Metadata -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between pt-4 border-t border-cool-grey-light gap-3">
      <a
        :href="result.url"
        target="_blank"
        rel="noopener noreferrer"
        class="inline-flex items-center text-sm font-medium text-cta-blue hover:text-cta-blue-dark transition-colors duration-base focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-cta-blue rounded"
      >
        <svg
          class="w-5 h-5 mr-1"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
          />
        </svg>
        View Full Document
      </a>

      <div class="text-right">
        <time
          v-if="detectedAt"
          :datetime="detectedAt"
          class="text-xs text-cool-grey"
        >
          Identified: {{ formattedDetectedAt }}
        </time>
        <p
          v-if="slaInfo"
          :class="[
            'text-xs font-semibold mt-0.5',
            slaInfo.is_overdue ? 'text-alert-danger-dark' :
            slaInfo.is_critical ? 'text-alert-danger-dark' :
            slaInfo.is_approaching ? 'text-alert-warning-dark' :
            'text-cool-grey'
          ]"
        >
          {{ slaTimeText }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProcessedResult, ConflictType, SlaInfo } from '@/types'

interface Props {
  result: ProcessedResult
  conflictType?: ConflictType
  detectedAt?: string
  slaInfo?: SlaInfo | null
}

const props = defineProps<Props>()

const formattedPublishDate = computed(() => {
  if (!props.result.date_published) return ''
  const date = new Date(props.result.date_published)
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  })
})

const formattedDetectedAt = computed(() => {
  if (!props.detectedAt) return ''
  const date = new Date(props.detectedAt)
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  })
})

const slaTimeText = computed(() => {
  if (!props.slaInfo) return ''
  if (props.slaInfo.is_overdue) {
    return `Overdue by ${Math.round(props.slaInfo.hours_overdue)} hours`
  }
  return `${Math.round(props.slaInfo.hours_remaining)} hours remaining`
})

const formatConflictType = (type: ConflictType): string => {
  const typeMap: Record<ConflictType, string> = {
    'INCLUDE_EXCLUDE': 'Include vs. Exclude',
    'INCLUDE_MAYBE': 'Include vs. Maybe',
    'EXCLUDE_MAYBE': 'Exclude vs. Maybe',
    'MULTIPLE_DISAGREEMENT': 'Multiple Disagreement'
  }
  return typeMap[type] || type
}
</script>
