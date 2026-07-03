<template>
  <div data-testid="work-queue" class="w-full px-6 py-4">
    <!-- Header -->
    <div class="flex flex-col md:flex-row md:items-end md:justify-between mb-10 gap-4">
      <div class="space-y-1">
        <h1 class="text-3xl font-bold text-foreground">Active Work Queue</h1>
        <p class="text-sm text-muted-foreground uppercase tracking-widest font-semibold flex items-center gap-2">
          <ShieldCheck class="h-4 w-4 text-deep-navy" />
          Protocol Enforcement: Dual Screening
        </p>
      </div>
      <div class="mt-4 md:mt-0">
        <Button
          data-testid="claim-button"
          @click="handleClaimNext"
          :disabled="isLoading || !canClaimResults"
          class="border-scholar shadow-scholar h-10 px-6 font-bold bg-deep-navy hover:bg-deep-navy-light text-off-white"
          aria-label="Claim next available result for screening"
        >
          <PlusCircle class="h-4 w-4 mr-2" />
          Enrol Next Record
        </Button>
      </div>
    </div>

    <!-- Status Summary (Academic Funnel) -->
    <div class="mb-8 border-scholar shadow-scholar rounded-lg overflow-hidden bg-white border-t-4 border-t-deep-navy">
      <div class="flex flex-wrap items-center divide-x divide-scholar">
        <div class="px-6 py-4 flex-1 min-w-[140px]">
          <span class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground block mb-2">Unscanned</span>
          <span class="text-2xl font-bold text-foreground">{{ pendingCount }}</span>
        </div>
        <div class="px-6 py-4 flex-1 min-w-[140px] bg-teal-blue/5">
          <span class="text-[10px] font-bold uppercase tracking-widest text-teal-blue-dark block mb-2">Personal Claims</span>
          <span class="text-2xl font-bold text-teal-blue-dark">{{ myClaimsCount }}</span>
        </div>
        <div class="px-6 py-4 flex-1 min-w-[140px]">
          <span class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground block mb-2">Completed</span>
          <span class="text-2xl font-bold text-foreground">{{ completedCount }}</span>
        </div>
        <div class="px-6 py-4 flex-1 min-w-[140px] bg-warning/5">
          <span class="text-[10px] font-bold uppercase tracking-widest text-warning-dark block mb-2">Variance (Conflicts)</span>
          <span class="text-2xl font-bold text-warning-dark">{{ conflictsCount }}</span>
        </div>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-4">
      <div class="inline-flex rounded-lg border border-input" role="group" aria-label="Filter results by status">
        <Button
          :variant="currentFilter === 'pending' ? 'default' : 'ghost'"
          size="sm"
          class="rounded-r-none"
          data-testid="filter-pending-btn"
          @click="currentFilter = 'pending'; handleFilterChange()"
        >
          Pending ({{ pendingCount }})
        </Button>
        <Button
          :variant="currentFilter === 'claimed' ? 'default' : 'ghost'"
          size="sm"
          class="rounded-none border-x border-input"
          data-testid="filter-claimed-btn"
          @click="currentFilter = 'claimed'; handleFilterChange()"
        >
          My Claims ({{ myClaimsCount }})
        </Button>
        <Button
          :variant="currentFilter === 'conflicts' ? 'default' : 'ghost'"
          size="sm"
          class="rounded-l-none"
          data-testid="filter-conflicts-btn"
          @click="currentFilter = 'conflicts'; handleFilterChange()"
        >
          Conflicts ({{ conflictsCount }})
        </Button>
      </div>
      <div class="mt-4 md:mt-0">
        <Button
          variant="outline"
          data-testid="refresh-queue-btn"
          @click="handleRefresh"
          :disabled="isLoading"
          aria-label="Refresh work queue"
        >
          <RefreshCw :class="{ 'animate-spin': isLoading }" class="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>
    </div>

    <!-- Error Alert -->
    <ErrorAlert
      v-if="error"
      title="Error"
      :message="error"
      dismissible
      @dismiss="error = null"
    />

    <!-- Success Alert -->
    <div
      v-if="successMessage"
      class="flex items-center gap-2 rounded-lg border border-[color:var(--color-success)] bg-[color:var(--color-success-light)] p-4 mb-4"
      role="alert"
    >
      <CheckCircle class="h-5 w-5 text-[color:var(--color-success)]" />
      <p class="text-sm text-foreground">{{ successMessage }}</p>
      <button
        type="button"
        class="ml-auto text-muted-foreground hover:text-foreground"
        @click="successMessage = null"
        aria-label="Close success alert"
      >
        <X class="h-4 w-4" />
      </button>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="isLoading && results.length === 0"
      variant="spinner"
      size="lg"
      message="Loading work queue..."
    />

    <!-- Empty State -->
    <div
      v-else-if="!isLoading && results.length === 0"
      class="text-center py-12"
    >
      <Inbox class="h-16 w-16 text-muted-foreground mx-auto mb-4" />
      <h3 class="text-lg font-semibold text-muted-foreground mb-2">No results found</h3>
      <p class="text-muted-foreground">
        {{ getEmptyStateMessage() }}
      </p>
    </div>

    <!-- Results Table -->
    <div v-else class="border-scholar shadow-scholar rounded-lg overflow-hidden bg-white">
      <Table>
        <TableHeader>
          <TableRow class="bg-off-white hover:bg-off-white border-b border-scholar">
            <TableHead class="w-[30%] text-[9px] font-bold uppercase tracking-widest py-4 px-6">Record Metadata</TableHead>
            <TableHead class="w-[20%] text-[9px] font-bold uppercase tracking-widest py-4">Direct Evidence (Link)</TableHead>
            <TableHead class="w-[35%] text-[9px] font-bold uppercase tracking-widest py-4">Content Abstract</TableHead>
            <TableHead class="w-[15%] text-[9px] font-bold uppercase tracking-widest py-4 pr-6 text-right">Protocol Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="item in results"
            :key="item.result.id"
            data-testid="work-queue-row"
            @click="handleRowClick(item)"
            :class="{ 'bg-teal-blue/5 border-l-4 border-l-teal-blue': item.status === 'claimed_by_me' }"
            class="cursor-pointer hover:bg-off-white transition-colors border-b border-scholar/50 last:border-0"
          >
            <TableCell class="py-4 px-6">
              <p class="text-base font-bold text-foreground mb-1 leading-tight">{{ item.result.title }}</p>
              <div class="flex items-center gap-2 text-[10px] text-muted-foreground uppercase font-bold tracking-tight">
                <span v-if="item.result.source_name" class="px-1.5 py-0.5 bg-cool-grey-light/50 rounded">{{ item.result.source_name }}</span>
                <span v-if="item.result.date_published" class="italic font-serif normal-case">{{ formatDate(item.result.date_published) }}</span>
              </div>
            </TableCell>
            <TableCell class="py-4">
              <a
                :href="item.result.url"
                target="_blank"
                rel="noopener noreferrer"
                class="text-teal-blue hover:text-teal-blue-dark transition-colors flex items-center gap-1.5 truncate max-w-[180px] font-mono text-[10px]"
                @click.stop
                :aria-label="`Open ${item.result.title} in new tab`"
              >
                <ExternalLink class="h-3 w-3 flex-shrink-0" />
                <span class="truncate">{{ item.result.url }}</span>
              </a>
            </TableCell>
            <TableCell class="py-4">
              <p class="text-xs text-muted-foreground font-serif italic line-clamp-2 leading-relaxed">
                {{ item.result.snippet }}
              </p>
            </TableCell>
            <TableCell class="py-4 pr-6 text-right">
              <StatusBadge :status="getStatusType(item.status)" size="sm" class="uppercase text-[8px] font-bold tracking-widest">
                {{ getStatusLabel(item.status) }}
              </StatusBadge>
              <p v-if="item.claim_info" class="text-[9px] text-muted-foreground mt-2 font-bold uppercase tracking-tighter">
                Assigned: {{ item.claim_info.claimed_by.username }}
              </p>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <!-- Pagination -->
    <div v-if="totalPages > 1" class="flex flex-col md:flex-row md:items-center md:justify-between mt-6">
      <p class="text-sm text-muted-foreground mb-4 md:mb-0">
        Showing {{ ((currentPage - 1) * perPage) + 1 }} to
        {{ Math.min(currentPage * perPage, totalCount) }} of {{ totalCount }} results
      </p>
      <nav aria-label="Work queue pagination" class="flex items-center gap-1">
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  PlusCircle,
  RefreshCw,
  CheckCircle,
  Inbox,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  X,
  ShieldCheck
} from 'lucide-vue-next'
import { useWorkQueueStore } from '../stores/workQueue'
import { useAuthStore } from '../stores/auth'
import { useOrganisationStore } from '../stores/organisation'
import type { WorkQueueResult } from '../types'

// Shadcn-vue components
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

// Agent Grey components
import { StatusBadge, type StatusType } from '@/components/ui/status-badge'
import { LoadingState } from '@/components/ui/loading-state'
import { ErrorAlert } from '@/components/shared'

// Stores
const router = useRouter()
const workQueueStore = useWorkQueueStore()
const authStore = useAuthStore()
const orgStore = useOrganisationStore()

// Helpers
function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-GB', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return dateString
  }
}

// Local state
const isLoading = ref(false)
const error = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const currentFilter = ref<'pending' | 'claimed' | 'conflicts'>('pending')
const perPage = 25


// Get session ID from URL query parameter
// FIX (Issue #30): Extract session_id from URL to load correct session
const sessionId = computed(() => {
  const params = new URLSearchParams(window.location.search)
  return params.get('session_id') || ''
})

// Computed properties from store
const results = computed(() => workQueueStore.results)
const totalCount = computed(() => workQueueStore.totalCount)
const currentPage = computed(() => workQueueStore.currentPage)
const totalPages = computed(() => workQueueStore.totalPages)
const hasNext = computed(() => workQueueStore.hasNext)
const hasPrevious = computed(() => workQueueStore.hasPrevious)

const pendingCount = computed(() => workQueueStore.pendingCount)
const myClaimsCount = computed(() => workQueueStore.myClaims.length)
const completedCount = computed(() => workQueueStore.completedCount)
const conflictsCount = computed(() => workQueueStore.conflicts.length)

const canClaimResults = computed(() => authStore.canClaimResults)

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
async function fetchQueue() {
  console.log('[WorkQueue] fetchQueue called')
  console.log('[WorkQueue] Session ID:', sessionId.value)
  console.log('[WorkQueue] Organisation ID:', orgStore.organisationId)
  console.log('[WorkQueue] Has organisation:', orgStore.hasOrganisation)

  if (!sessionId.value) {
    console.error('[WorkQueue] No session ID provided in URL')
    error.value = 'No session ID provided. Please navigate from a valid session.'
    return
  }

  if (!orgStore.checkOrganisationContext()) {
    console.error('[WorkQueue] No organisation context - aborting fetch')
    error.value = 'Organisation context missing. Please select an organisation.'
    return
  }

  isLoading.value = true
  error.value = null

  try {
    await workQueueStore.fetchQueue(sessionId.value)
  } catch (err: unknown) {
    error.value = workQueueStore.error || 'Failed to fetch work queue'
  } finally {
    isLoading.value = false
  }
}

async function handleClaimNext() {
  if (!canClaimResults.value) {
    error.value = 'You do not have permission to claim results'
    return
  }

  isLoading.value = true
  error.value = null
  successMessage.value = null

  try {
    const result = await workQueueStore.claimNext(sessionId.value)

    if (result) {
      successMessage.value = 'Result claimed successfully!'
      // Navigate to screening decision view
      router.push({ name: 'screening', params: { id: result.id } })
    } else {
      error.value = workQueueStore.error || 'No results available to claim'
    }
  } catch (err: unknown) {
    error.value = workQueueStore.error || 'Failed to claim result'
  } finally {
    isLoading.value = false
  }
}

function handleFilterChange() {
  workQueueStore.setFilter('status', currentFilter.value)
  workQueueStore.setFilter('page', 1)
  fetchQueue()
}

function handlePageChange(page: number) {
  if (page < 1 || page > totalPages.value) return
  workQueueStore.setFilter('page', page)
  fetchQueue()
}

function handleRefresh() {
  fetchQueue()
}

function handleRowClick(item: WorkQueueResult) {
  // Navigate to screening decision if claimed by current user
  if (item.status === 'claimed_by_me') {
    router.push({ name: 'screening', params: { id: item.result.id } })
  }
  // For conflicts, navigate to conflict resolution
  else if (item.status === 'conflict') {
    // Would need conflict ID - for now just show message
    successMessage.value = 'Navigate to conflict resolution for this result'
  }
  // Otherwise, could claim it
  else if (item.status === 'pending' && canClaimResults.value) {
    // Optionally auto-claim on click
    // For now, just show a message
  }
}

function getStatusType(status: string): StatusType {
  switch (status) {
    case 'pending':
      return 'pending'
    case 'claimed_by_me':
      return 'include'
    case 'claimed_by_other':
      return 'maybe'
    case 'decided_by_me':
      return 'RESOLVED'
    case 'conflict':
      return 'ESCALATED'
    default:
      return 'pending'
  }
}

function getStatusLabel(status: string): string {
  switch (status) {
    case 'pending':
      return 'Pending'
    case 'claimed_by_me':
      return 'Claimed by Me'
    case 'claimed_by_other':
      return 'Claimed by Other'
    case 'decided_by_me':
      return 'Completed'
    case 'conflict':
      return 'Conflict'
    default:
      return status
  }
}

function getEmptyStateMessage(): string {
  switch (currentFilter.value) {
    case 'pending':
      return 'No pending results. All results have been claimed or completed.'
    case 'claimed':
      return 'You have not claimed any results yet. Click "Claim Next Result" to start screening.'
    case 'conflicts':
      return 'No conflicts detected. Great work!'
    default:
      return 'No results found.'
  }
}


// Lifecycle hooks
onMounted(() => {
  console.log('[WorkQueue] Component mounted')
  console.log('[WorkQueue] Auth state:', authStore.isAuthenticated)
  console.log('[WorkQueue] Organisation:', orgStore.currentOrganisation)
  console.log('[WorkQueue] Organisation ID:', orgStore.organisationId)

  // Initial fetch
  fetchQueue()

  // Auto-dismiss success messages after 5 seconds
  const successInterval = setInterval(() => {
    if (successMessage.value) {
      successMessage.value = null
    }
  }, 5000)

  // Cleanup interval on unmount
  onUnmounted(() => {
    clearInterval(successInterval)
  })
})

</script>

<style scoped>
/* Truncate utility for URL display */
.truncate {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
