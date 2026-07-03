/**
 * Work Queue Store
 * Manages screening work queue state and filters
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type {
  WorkQueueResult,
  ProcessedResult,
  WorkQueueFilter,
  ReviewerDecisionInput,
  DecisionResponse,
} from '../types';
import {
  getWorkQueue,
  claimNextResult,
  submitDecision as apiSubmitDecision,
  releaseResult as apiReleaseResult,
} from '../api/results';
import { useOrganisationStore } from './organisation';

export const useWorkQueueStore = defineStore('workQueue', () => {
  // State
  const results = ref<WorkQueueResult[]>([]);
  const currentResult = ref<ProcessedResult | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  // Filters
  const filters = ref<WorkQueueFilter>({
    status: 'pending',
    page: 1,
    per_page: 25,
  });

  // Pagination
  const totalCount = ref(0);
  const currentPage = ref(1);
  const totalPages = ref(1);
  const hasNext = ref(false);
  const hasPrevious = ref(false);

  // Getters
  const pendingCount = computed(() =>
    results.value.filter(r => r.status === 'pending').length
  );

  const myClaims = computed(() =>
    results.value.filter(r => r.status === 'claimed_by_me' || r.status === 'decided_by_me')
  );

  const conflicts = computed(() =>
    results.value.filter(r => r.status === 'conflict')
  );

  const completedCount = computed(() =>
    results.value.filter(r => r.status === 'decided_by_me').length
  );

  // Actions
  async function fetchQueue(sessionId?: string) {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return;

    isLoading.value = true;
    error.value = null;

    try {
      const filterParams = { ...filters.value };
      if (sessionId) {
        filterParams.session_id = sessionId;
      }

      const response = await getWorkQueue(filterParams);

      results.value = response.results;
      totalCount.value = response.count;
      currentPage.value = response.page;
      totalPages.value = response.num_pages;
      hasNext.value = response.next !== null;
      hasPrevious.value = response.previous !== null;
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Failed to fetch work queue';
      console.error('Work queue error:', err);
    } finally {
      isLoading.value = false;
    }
  }

  async function claimNext(sessionId?: string, screeningStage: 'SCREENING' = 'SCREENING') {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return null;

    isLoading.value = true;
    error.value = null;

    try {
      const result = await claimNextResult({
        session_id: sessionId,
        screening_stage: screeningStage,
      });

      currentResult.value = result;

      // Refresh queue to show updated status
      await fetchQueue(sessionId);

      return result;
    } catch (err: any) {
      if (err.response?.data?.error === 'no_results_available') {
        error.value = 'No more results available for review';
      } else if (err.response?.data?.error === 'session_not_ready') {
        error.value = err.response.data.message;
      } else {
        error.value = 'Failed to claim result';
      }
      console.error('Claim error:', err);
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  function setFilter(key: keyof WorkQueueFilter, value: any) {
    filters.value = { ...filters.value, [key]: value };
  }

  function resetFilters() {
    filters.value = {
      status: 'pending',
      page: 1,
      per_page: 25,
    };
  }

  function setCurrentResult(result: ProcessedResult | null) {
    currentResult.value = result;
  }

  function clearQueue() {
    results.value = [];
    currentResult.value = null;
    error.value = null;
  }

  /**
   * Submit screening decision for a result
   * @param resultId - UUID of the result
   * @param data - Decision data (decision, confidence_level, notes, etc.)
   * @returns DecisionResponse with conflict status
   */
  async function submitDecision(
    resultId: string,
    data: ReviewerDecisionInput
  ): Promise<DecisionResponse | null> {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return null;

    isLoading.value = true;
    error.value = null;

    try {
      const response = await apiSubmitDecision(resultId, data);

      // Clear current result after successful submission
      currentResult.value = null;

      return response;
    } catch (err: any) {
      if (err.response?.status === 409) {
        error.value = 'You have already submitted a decision for this result';
      } else {
        error.value = err.response?.data?.message || 'Failed to submit decision';
      }
      console.error('Submit decision error:', err);
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Release a claimed result back to the queue
   * @param resultId - UUID of the result to release
   * @returns boolean indicating success
   */
  async function releaseResult(resultId: string): Promise<boolean> {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return false;

    error.value = null;

    try {
      await apiReleaseResult(resultId);

      // Clear current result after successful release
      currentResult.value = null;

      return true;
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Failed to release result';
      console.error('Release result error:', err);
      return false;
    }
  }

  return {
    // State
    results,
    currentResult,
    isLoading,
    error,
    filters,
    totalCount,
    currentPage,
    totalPages,
    hasNext,
    hasPrevious,
    // Getters
    pendingCount,
    myClaims,
    conflicts,
    completedCount,
    // Actions
    fetchQueue,
    claimNext,
    submitDecision,
    releaseResult,
    setFilter,
    resetFilters,
    setCurrentResult,
    clearQueue,
  };
});
