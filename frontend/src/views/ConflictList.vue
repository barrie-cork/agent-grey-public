<template>
  <div class="w-full px-6 py-4" data-testid="conflict-list">
    <!-- Back to Review Overview -->
    <a
      v-if="sessionId"
      :href="`/review-results/overview/${sessionId}/`"
      class="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors mb-4"
    >
      <ArrowLeft class="h-4 w-4" />
      Back to Review Overview
    </a>

    <!-- Header -->
    <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-foreground mb-1">Discussions Needed</h1>
        <p class="text-sm text-muted-foreground">
          Review assessments where reviewers have reached different conclusions
        </p>
        <p class="text-xs text-muted-foreground/70 mt-1 italic">
          Most disagreements resolve when both reviewers re-read the source material together.
        </p>
      </div>
      <div class="mt-4 md:mt-0">
        <Button
          variant="outline"
          @click="handleRefresh"
          :disabled="isLoading"
          aria-label="Refresh discussions list"
        >
          <RefreshCw :class="{ 'animate-spin': isLoading }" class="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>
    </div>

    <!-- Metrics -->
    <div class="grid grid-cols-3 gap-4 mb-4">
      <div class="border-l-4 border-l-[color:var(--color-warning)] bg-card border border-border rounded-md px-4 py-3">
        <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Awaiting Discussion</p>
        <p class="text-xl font-bold text-foreground mt-1">{{ sessionPendingCount }}</p>
      </div>
      <div class="border-l-4 border-l-[color:var(--color-success)] bg-card border border-border rounded-md px-4 py-3">
        <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Resolved</p>
        <p class="text-xl font-bold text-foreground mt-1">{{ sessionResolvedCount }}</p>
      </div>
      <div class="border-l-4 border-l-[color:var(--color-primary)] bg-card border border-border rounded-md px-4 py-3">
        <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Total</p>
        <p class="text-xl font-bold text-foreground mt-1">{{ sessionTotalCount }}</p>
      </div>
    </div>

    <!-- Progress Bar -->
    <div v-if="sessionTotalCount > 0" class="mb-6">
      <div class="flex items-center justify-between mb-1.5">
        <p class="text-sm font-medium text-foreground">
          Discussing {{ sessionPendingCount }} of {{ sessionTotalCount }} assessments
        </p>
        <span class="text-sm font-bold text-foreground">
          {{ sessionProgressPercent }}% resolved
        </span>
      </div>
      <div class="w-full bg-muted rounded-full h-2">
        <div
          class="bg-[color:var(--color-success)] h-2 rounded-full transition-all duration-500"
          :style="{ width: `${sessionProgressPercent}%` }"
        />
      </div>
    </div>

    <!-- Filters -->
    <div class="mb-4 border-b border-border">
      <nav class="flex gap-6 -mb-px" role="group" aria-label="Filter discussions by status">
        <button
          :class="[
            'pb-2 text-xs font-semibold uppercase tracking-wider border-b-2 transition-colors',
            currentFilter === 'all'
              ? 'border-primary text-foreground'
              : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
          ]"
          @click="currentFilter = 'all'; handleFilterChange()"
        >
          All ({{ sessionTotalCount }})
        </button>
        <button
          :class="[
            'pb-2 text-xs font-semibold uppercase tracking-wider border-b-2 transition-colors',
            currentFilter === 'pending'
              ? 'border-primary text-foreground'
              : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
          ]"
          @click="currentFilter = 'pending'; handleFilterChange()"
        >
          Awaiting Discussion ({{ sessionPendingCount }})
        </button>
        <button
          :class="[
            'pb-2 text-xs font-semibold uppercase tracking-wider border-b-2 transition-colors',
            currentFilter === 'resolved'
              ? 'border-primary text-foreground'
              : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
          ]"
          @click="currentFilter = 'resolved'; handleFilterChange()"
        >
          Resolved ({{ sessionResolvedCount }})
        </button>
      </nav>
    </div>

    <!-- Error Alert -->
    <ErrorAlert
      v-if="error"
      :title="'Error loading discussions'"
      :message="error"
      dismissible
      @dismiss="error = null"
    />

    <!-- Loading State -->
    <LoadingState
      v-if="isLoading && conflicts.length === 0"
      variant="spinner"
      size="lg"
      message="Loading discussions..."
    />

    <!-- Empty State -->
    <div
      v-else-if="!isLoading && conflicts.length === 0"
      class="text-center py-12"
    >
      <CheckCircle2 class="h-16 w-16 text-[color:var(--color-success)] mx-auto mb-4" />
      <h3 class="text-lg font-semibold text-muted-foreground mb-2">No discussions found</h3>
      <p class="text-muted-foreground">
        {{ getEmptyStateMessage() }}
      </p>
    </div>

    <!-- Conflicts Table -->
    <div v-else class="rounded-lg border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow class="bg-muted/50">
            <TableHead class="w-[35%]">Result</TableHead>
            <TableHead class="w-[20%]">Disagreement Type</TableHead>
            <TableHead class="w-[15%]">Status</TableHead>
            <TableHead class="w-[20%]">Identified</TableHead>
            <TableHead class="w-[10%]">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="conflict in conflicts"
            :key="conflict.id"
            data-testid="conflict-item"
            @click="handleRowClick(conflict)"
            :class="[
              'cursor-pointer hover:bg-muted/50 transition-colors',
              conflict.status === 'PENDING' ? 'bg-[color:var(--color-warning-light)]/30' : '',
              getSlaUrgencyClass(conflict),
            ]"
          >
            <TableCell>
              <p class="font-semibold text-foreground">{{ getResultTitle(conflict) }}</p>
              <p class="text-sm text-muted-foreground line-clamp-2">
                {{ getResultSnippet(conflict) }}
              </p>
            </TableCell>
            <TableCell>
              <StatusBadge
                :status="getConflictTypeStatus(conflict.conflict_type)"
                size="sm"
              >
                {{ formatConflictType(conflict.conflict_type) }}
              </StatusBadge>
            </TableCell>
            <TableCell>
              <StatusBadge
                :status="conflict.status"
                size="sm"
              />
              <p v-if="conflict.resolution_method && conflict.status === 'RESOLVED'" class="text-xs text-muted-foreground mt-1">
                {{ formatResolutionMethod(conflict.resolution_method) }}
              </p>
            </TableCell>
            <TableCell>
              <p class="text-sm">{{ formatDate(conflict.detected_at) }}</p>
              <p v-if="conflict.resolved_at" class="text-xs text-muted-foreground">
                Resolved: {{ formatDate(conflict.resolved_at) }}
              </p>
              <p
                v-else-if="conflict.sla_info"
                :class="[
                  'text-xs font-medium mt-0.5',
                  conflict.sla_info.is_overdue ? 'text-destructive' :
                  conflict.sla_info.is_critical ? 'text-destructive' :
                  conflict.sla_info.is_approaching ? 'text-[color:var(--color-warning)]' :
                  'text-muted-foreground'
                ]"
              >
                {{ formatSlaTime(conflict.sla_info) }}
              </p>
            </TableCell>
            <TableCell>
              <Button
                variant="outline"
                size="sm"
                data-testid="resolve-conflict-btn"
                @click.stop="viewConflict(conflict)"
                :aria-label="`View discussion for ${getResultTitle(conflict)}`"
                class="text-xs font-semibold"
              >
                <Eye class="h-3.5 w-3.5 mr-1" />
                Review
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex flex-col md:flex-row md:items-center md:justify-between mt-6">
      <p class="text-sm text-muted-foreground mb-4 md:mb-0">
        Showing {{ ((currentPage - 1) * perPage) + 1 }} to
        {{ Math.min(currentPage * perPage, totalCount) }} of {{ totalCount }} discussions
      </p>
      <nav aria-label="Discussions pagination" class="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          @click="handlePageChange(currentPage - 1)"
          :disabled="!hasPrevious"
          aria-label="Previous page"
        >
          <ChevronLeft class="h-4 w-4" />
        </Button>

        <template v-for="page in visiblePages" :key="page">
          <span v-if="page === -1" class="px-2 text-muted-foreground">...</span>
          <Button
            v-else
            :variant="page === currentPage ? 'default' : 'outline'"
            size="icon"
            @click="handlePageChange(page)"
            :aria-label="`Go to page ${page}`"
            :aria-current="page === currentPage ? 'page' : undefined"
          >
            {{ page }}
          </Button>
        </template>

        <Button
          variant="outline"
          size="icon"
          @click="handlePageChange(currentPage + 1)"
          :disabled="!hasNext"
          aria-label="Next page"
        >
          <ChevronRight class="h-4 w-4" />
        </Button>
      </nav>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RefreshCw, CheckCircle2, Eye, ChevronLeft, ChevronRight, ArrowLeft } from 'lucide-vue-next'
import { useConflictsStore } from '../stores/conflicts'
import type { ConflictResolution, SlaInfo } from '../types'

// Shadcn-vue components
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

// Agent Grey components
import { StatusBadge, type StatusType } from '@/components/ui/status-badge'
import { LoadingState } from '@/components/ui/loading-state'
import { ErrorAlert } from '@/components/shared'

// Router
const route = useRoute()
const router = useRouter()

// Store
const conflictsStore = useConflictsStore()

// Session context from query params
const sessionId = computed(() => route.query.session_id as string | undefined)

// Local state
const currentFilter = ref<'all' | 'pending' | 'resolved'>('pending')
const perPage = 20

// Store state (reactive references)
const conflicts = computed(() => conflictsStore.conflicts)
const isLoading = computed(() => conflictsStore.isLoading)
const error = computed({
  get: () => conflictsStore.error,
  set: (value) => {
    if (value === null) conflictsStore.clearError()
  }
})
const totalCount = computed(() => conflictsStore.totalCount)
const currentPage = computed(() => conflictsStore.currentPage)
const totalPages = computed(() => conflictsStore.totalPages)
const hasNext = computed(() => conflictsStore.hasNext)
const hasPrevious = computed(() => conflictsStore.hasPrevious)

// Session-wide counts (from server)
const sessionCounts = computed(() => conflictsStore.sessionCounts)
const sessionPendingCount = computed(() => sessionCounts.value.pending)
const sessionResolvedCount = computed(() => sessionCounts.value.resolved)
const sessionTotalCount = computed(() => sessionCounts.value.total)
const sessionProgressPercent = computed(() => conflictsStore.sessionProgressPercent)

// Pagination helpers
const visiblePages = computed(() => {
  const pages: number[] = []
  const maxVisible = 5
  const total = totalPages.value
  const current = currentPage.value

  if (total <= maxVisible) {
    for (let i = 1; i <= total; i++) {
      pages.push(i)
    }
  } else {
    const start = Math.max(1, current - 2)
    const end = Math.min(total, current + 2)

    if (start > 1) pages.push(1)
    if (start > 2) pages.push(-1) // Ellipsis placeholder

    for (let i = start; i <= end; i++) {
      pages.push(i)
    }

    if (end < total - 1) pages.push(-1) // Ellipsis placeholder
    if (end < total) pages.push(total)
  }

  return pages
})

// Methods
async function fetchConflicts() {
  const statusParam = currentFilter.value === 'all' ? undefined : currentFilter.value.toUpperCase()
  const sessionId = route.query.session_id as string | undefined

  await conflictsStore.fetchConflicts({
    session_id: sessionId,
    page: currentPage.value,
    per_page: perPage,
    status: statusParam as 'PENDING' | 'RESOLVED' | undefined,
  })
}

function handleFilterChange() {
  conflictsStore.setFilter('page', 1)
  fetchConflicts()
}

function handlePageChange(page: number) {
  if (page < 1 || page > totalPages.value) return
  conflictsStore.setFilter('page', page)
  fetchConflicts()
}

function handleRefresh() {
  fetchConflicts()
}

function handleRowClick(conflict: ConflictResolution) {
  viewConflict(conflict)
}

function viewConflict(conflict: ConflictResolution) {
  const query = sessionId.value ? { session_id: sessionId.value } : {};
  router.push({ name: 'conflict-resolution', params: { id: conflict.id }, query })
}

function getConflictTypeStatus(conflictType: string): StatusType {
  switch (conflictType) {
    case 'INCLUDE_EXCLUDE':
      return 'exclude' // Red
    case 'INCLUDE_MAYBE':
      return 'maybe' // Amber/Yellow
    case 'EXCLUDE_MAYBE':
      return 'pending' // Blue-ish
    case 'MULTIPLE_DISAGREEMENT':
      return 'conflict' // Dark
    default:
      return 'inactive'
  }
}

function formatConflictType(conflictType: string): string {
  const typeLabels: Record<string, string> = {
    INCLUDE_EXCLUDE: 'Include vs Exclude',
    INCLUDE_MAYBE: 'Include vs Uncertain',
    EXCLUDE_MAYBE: 'Exclude vs Uncertain',
    EXCLUSION_REASON: 'Different Exclusion Reasons',
    LOW_CONFIDENCE: 'Low Confidence',
    MULTIPLE_DISAGREEMENT: 'Multiple Disagreement',
  }
  return typeLabels[conflictType] || conflictType
}

function formatResolutionMethod(method: string): string {
  const methodLabels: Record<string, string> = {
    CONSENSUS: 'Consensus',
    ARBITRATION: 'Arbitration',
    LEAD_DECISION: 'Lead Decision',
    SENIOR_OVERRIDE: 'Senior Override',
  }
  return methodLabels[method] || method
}

function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-GB', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateString
  }
}

// Handle both full serializer (nested result) and blinded serializer (flat result_title)
function getResultTitle(conflict: ConflictResolution): string {
  return conflict.result?.title ?? (conflict as unknown as Record<string, unknown>).result_title as string ?? 'Untitled'
}

function getResultSnippet(conflict: ConflictResolution): string {
  return conflict.result?.snippet ?? ''
}

function getSlaUrgencyClass(conflict: ConflictResolution): string {
  if (!conflict.sla_info) return ''
  if (conflict.sla_info.is_overdue || conflict.sla_info.is_critical) {
    return 'border-l-4 border-l-destructive'
  }
  if (conflict.sla_info.is_approaching) {
    return 'border-l-4 border-l-[color:var(--color-warning)]'
  }
  return ''
}

function formatSlaTime(slaInfo: SlaInfo): string {
  if (slaInfo.is_overdue) {
    const hours = Math.round(slaInfo.hours_overdue)
    return `Overdue by ${hours}h`
  }
  const hours = Math.round(slaInfo.hours_remaining)
  return `${hours}h remaining`
}

function getEmptyStateMessage(): string {
  switch (currentFilter.value) {
    case 'pending':
      return 'No discussions awaiting attention. All disagreements have been resolved!'
    case 'resolved':
      return 'No resolved discussions yet.'
    case 'all':
      return 'No disagreements identified in this review. Great alignment!'
    default:
      return 'No discussions found.'
  }
}

// Lifecycle hooks
onMounted(() => {
  fetchConflicts()
})
</script>
