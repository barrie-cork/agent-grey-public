<script setup lang="ts">
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { StatusBadge } from '@/components/ui/status-badge'
import { ExternalLink } from 'lucide-vue-next'
import type { Decision } from '@/components/ui/decision-buttons'

export interface SearchResult {
  id: string
  title: string
  snippet: string
  url: string
  metadata?: {
    source?: string
    date?: string
    author?: string
  }
  decision?: Decision
}

interface Props {
  result: SearchResult
  showDecision?: boolean
}

withDefaults(defineProps<Props>(), {
  showDecision: true
})
</script>

<template>
  <Card class="hover:shadow-md transition-shadow">
    <CardHeader>
      <div class="flex items-start justify-between gap-4">
        <div class="flex-1 min-w-0">
          <CardTitle class="text-lg line-clamp-2">
            {{ result.title }}
          </CardTitle>
          <CardDescription class="mt-1.5 flex items-center gap-2 text-xs">
            <a
              :href="result.url"
              target="_blank"
              rel="noopener noreferrer"
              class="flex items-center gap-1 text-primary hover:underline truncate"
            >
              {{ result.url }}
              <ExternalLink :size="12" />
            </a>
          </CardDescription>
        </div>

        <StatusBadge
          v-if="showDecision && result.decision"
          :status="result.decision"
          size="sm"
        />
      </div>
    </CardHeader>

    <CardContent>
      <p class="text-sm text-foreground/90 line-clamp-3">
        {{ result.snippet }}
      </p>

      <div
        v-if="result.metadata"
        class="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground"
      >
        <span v-if="result.metadata.source">
          Source: {{ result.metadata.source }}
        </span>
        <span v-if="result.metadata.date">
          Date: {{ result.metadata.date }}
        </span>
        <span v-if="result.metadata.author">
          Author: {{ result.metadata.author }}
        </span>
      </div>

      <!-- Slot for custom actions (DecisionButtons, etc.) -->
      <div v-if="$slots.actions" class="mt-4 pt-4 border-t">
        <slot name="actions" />
      </div>
    </CardContent>
  </Card>
</template>
