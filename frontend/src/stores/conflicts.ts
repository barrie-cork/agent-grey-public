/**
 * Conflicts Store
 * Manages conflict resolution state and actions
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { ConflictResolution, ConflictListFilter, ResolveConflictInput } from '../types';
import { listConflicts, resolveConflict, escalateConflict as escalateConflictApi } from '../api/conflicts';
import type { SessionCounts } from '../api/conflicts';
import { useOrganisationStore } from './organisation';
import { extractErrorMessage } from '../lib/errors';

export const useConflictsStore = defineStore('conflicts', () => {
  // State
  const conflicts = ref<ConflictResolution[]>([]);
  const currentConflict = ref<ConflictResolution | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  // Filters
  const filters = ref<ConflictListFilter>({
    status: 'PENDING',
    page: 1,
    per_page: 20,
  });

  // Pagination
  const totalCount = ref(0);
  const currentPage = ref(1);
  const totalPages = ref(1);
  const hasNext = ref(false);
  const hasPrevious = ref(false);

  // Session-wide counts (from server)
  const sessionCounts = ref<SessionCounts>({ total: 0, resolved: 0, pending: 0 });

  // Getters
  const pendingConflicts = computed(() =>
    conflicts.value.filter(c => c.status === 'PENDING')
  );

  const inDiscussionConflicts = computed(() =>
    conflicts.value.filter(c => c.status === 'IN_DISCUSSION')
  );

  const resolvedConflicts = computed(() =>
    conflicts.value.filter(c => c.status === 'RESOLVED')
  );

  const pendingCount = computed(() => pendingConflicts.value.length);
  const resolvedCount = computed(() => resolvedConflicts.value.length);

  const sessionProgressPercent = computed(() => {
    if (sessionCounts.value.total === 0) return 0;
    return Math.round((sessionCounts.value.resolved / sessionCounts.value.total) * 100);
  });

  function getNextPendingConflict(currentId: string): ConflictResolution | null {
    const isPending = (c: ConflictResolution) => c.id !== currentId && c.status !== 'RESOLVED';
    const currentIndex = conflicts.value.findIndex(c => c.id === currentId);

    if (currentIndex >= 0) {
      // Prefer the next conflict after the current position, then wrap around
      const after = conflicts.value.slice(currentIndex + 1).find(isPending);
      if (after) return after;
      return conflicts.value.slice(0, currentIndex).find(isPending) ?? null;
    }

    // Current not in list — return first pending
    return conflicts.value.find(isPending) ?? null;
  }

  // Actions
  async function fetchConflicts(filterParams?: ConflictListFilter) {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return;

    isLoading.value = true;
    error.value = null;

    try {
      const params = filterParams || filters.value;
      const response = await listConflicts(params);

      conflicts.value = response.results;
      totalCount.value = response.count;
      currentPage.value = response.page || 1;
      totalPages.value = response.num_pages || 1;
      hasNext.value = response.next !== null;
      hasPrevious.value = response.previous !== null;

      // Store session-wide counts from server
      if (response.session_counts) {
        sessionCounts.value = response.session_counts;
      }
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to fetch discussions');
      console.error('Conflicts fetch error:', err);
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Fetch all conflicts across all pages for a given filter.
   * Used by auto-advance to find the next pending conflict
   * without being limited by pagination.
   */
  async function fetchAllConflicts(filterParams: ConflictListFilter) {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return;

    isLoading.value = true;
    error.value = null;

    try {
      const allResults: ConflictResolution[] = [];
      let page = 1;
      let hasMore = true;

      while (hasMore) {
        const response = await listConflicts({ ...filterParams, page, per_page: 100 });
        allResults.push(...response.results);

        if (response.session_counts) {
          sessionCounts.value = response.session_counts;
        }

        hasMore = response.next !== null;
        page++;
      }

      conflicts.value = allResults;
      totalCount.value = allResults.length;
      currentPage.value = 1;
      totalPages.value = 1;
      hasNext.value = false;
      hasPrevious.value = false;
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to fetch discussions');
      console.error('Conflicts fetch error:', err);
    } finally {
      isLoading.value = false;
    }
  }

  async function submitResolution(conflictId: string, resolutionData: ResolveConflictInput) {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return null;

    isLoading.value = true;
    error.value = null;

    try {
      const resolvedConflict = await resolveConflict(conflictId, resolutionData);

      // Update current conflict if it's the same one
      if (currentConflict.value?.id === conflictId) {
        currentConflict.value = resolvedConflict;
      }

      // Update in conflicts list
      const index = conflicts.value.findIndex(c => c.id === conflictId);
      if (index !== -1) {
        conflicts.value[index] = resolvedConflict;
      }

      return resolvedConflict;
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to resolve discussion');
      console.error('Conflict resolution error:', err);
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  async function escalateConflict(conflictId: string, reason?: string) {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return null;

    isLoading.value = true;
    error.value = null;

    try {
      const escalatedConflict = await escalateConflictApi(conflictId, reason);

      // Update current conflict if it's the same one
      if (currentConflict.value?.id === conflictId) {
        currentConflict.value = escalatedConflict;
      }

      // Update in conflicts list
      const index = conflicts.value.findIndex(c => c.id === conflictId);
      if (index !== -1) {
        conflicts.value[index] = escalatedConflict;
      }

      return escalatedConflict;
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to request independent review');
      console.error('Conflict escalation error:', err);
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  function setFilter(key: keyof ConflictListFilter, value: any) {
    filters.value = { ...filters.value, [key]: value };
  }

  function resetFilters() {
    filters.value = {
      status: 'PENDING',
      page: 1,
      per_page: 20,
    };
  }

  function setCurrentConflict(conflict: ConflictResolution | null) {
    currentConflict.value = conflict;
  }

  function clearConflicts() {
    conflicts.value = [];
    currentConflict.value = null;
    error.value = null;
  }

  function clearError() {
    error.value = null;
  }

  return {
    // State
    conflicts,
    currentConflict,
    isLoading,
    error,
    filters,
    totalCount,
    currentPage,
    totalPages,
    hasNext,
    hasPrevious,
    // Getters
    pendingConflicts,
    inDiscussionConflicts,
    resolvedConflicts,
    pendingCount,
    resolvedCount,
    sessionCounts,
    sessionProgressPercent,
    // Actions
    fetchConflicts,
    fetchAllConflicts,
    submitResolution,
    escalateConflict,
    getNextPendingConflict,
    setFilter,
    resetFilters,
    setCurrentConflict,
    clearConflicts,
    clearError,
  };
});
