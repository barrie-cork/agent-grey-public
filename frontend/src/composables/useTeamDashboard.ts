/**
 * Team dashboard composable.
 *
 * Manages all state, data loading, and helper functions for the
 * methodological dashboard (Workflow #2).
 */

import { ref, computed } from 'vue';
import { getTeamStats } from '../api/dashboard';
import { getBlindingStatus } from '../api/sessions';
import type { TeamDashboardStats, IRRMetric, ReviewerProgress, BlindingStatus } from '../types';
import { BLINDING_CONSTANTS } from '../types';
import { formatKappa, getKappaInterpretation, getKappaColorClass, getKappaBadgeVariant } from '../lib/kappa-utils';
import { getChartColorsFromCSS, buildKappaTrendChartData, buildKappaTrendChartOptions } from '../lib/chart-config';

export function useTeamDashboard() {
  // State
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const stats = ref<TeamDashboardStats | null>(null);
  const irrTrend = ref<IRRMetric[]>([]);
  const irrMetrics = ref<IRRMetric[]>([]);
  const reviewerProgress = ref<ReviewerProgress[]>([]);
  const blindingStatus = ref<BlindingStatus | null>(null);
  const blindingError = ref<string | null>(null);

  // Session ID from URL
  const sessionId = computed(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('session_id') || '';
  });

  // Computed properties
  const progressPercentage = computed(() => {
    if (!stats.value) return 0;
    return Math.round(stats.value.progress.percentage_complete);
  });

  const cohensKappa = computed(() => {
    return stats.value?.inter_rater_reliability?.average_kappa ?? null;
  });

  const percentageAgreement = computed(() => {
    return stats.value?.inter_rater_reliability?.average_agreement ?? null;
  });

  const kappaInterpretation = computed(() => getKappaInterpretation(cohensKappa.value));
  const kappaColorClass = computed(() => getKappaColorClass(cohensKappa.value));
  const kappaBadgeVariant = computed(() => getKappaBadgeVariant(cohensKappa.value));

  const isBlinded = computed(() => {
    return blindingStatus.value?.is_blinded || false;
  });

  // Chart computed
  const chartColors = computed(() => getChartColorsFromCSS());
  const chartData = computed(() => buildKappaTrendChartData(irrTrend.value, chartColors.value));
  const chartOptions = computed(() => buildKappaTrendChartOptions());

  // Methods
  async function loadBlindingStatus(sid: string): Promise<void> {
    try {
      blindingStatus.value = await getBlindingStatus(sid);
      blindingError.value = null;
    } catch (err) {
      console.error('Error loading blinding status:', err);
      blindingError.value = 'Failed to load blinding configuration. Displaying non-blinded view for safety.';
      blindingStatus.value = {
        is_blinded: false,
        min_reviewers: BLINDING_CONSTANTS.MIN_REVIEWERS_DEFAULT,
        reason: 'Blinding status unavailable (server error)'
      };
    }
  }

  async function loadDashboard(sid?: string) {
    isLoading.value = true;
    error.value = null;

    try {
      const currentSessionId = sid || sessionId.value;

      if (!currentSessionId) {
        error.value = 'No session ID provided';
        return;
      }

      await loadBlindingStatus(currentSessionId);

      const statsResponse = await getTeamStats(currentSessionId);
      stats.value = statsResponse;

      await loadIRRMetrics(currentSessionId);

      reviewerProgress.value = (statsResponse.reviewer_breakdown || []).map(r => ({
        reviewer: {
          id: r.reviewer.id,
          username: r.reviewer.username,
          email: r.reviewer.email,
          first_name: r.reviewer.username,
          last_name: '',
        } as any,
        reviewer_name: r.reviewer.username,
        reviewed_count: r.total_reviews,
        decisions_count: r.total_reviews,
        conflicts_count: 0,
        conflicts_involved: 0,
        avg_time_seconds: r.average_time_seconds,
        last_review_at: undefined,
      }));
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to load dashboard';
      console.error('Error loading dashboard:', err);
    } finally {
      isLoading.value = false;
    }
  }

  async function loadIRRMetrics(sid: string): Promise<void> {
    try {
      const response = await fetch(`/api/dashboard/irr/?session_id=${sid}`, {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
      });

      if (!response.ok) {
        throw new Error(`Failed to load IRR metrics: ${response.statusText}`);
      }

      const metrics = await response.json();
      irrMetrics.value = metrics;

      if (metrics && metrics.length > 0) {
        irrTrend.value = metrics.map((m: any) => ({
          calculated_at: m.calculated_at,
          cohens_kappa: m.cohens_kappa,
        }));
      }
    } catch (err) {
      console.error('Error loading IRR metrics:', err);
    }
  }

  function handleRefresh() {
    loadDashboard();
  }

  function calculateReviewerProgress(reviewer: ReviewerProgress): number {
    if (!stats.value || stats.value.overview.total_results === 0) return 0;
    return Math.round((reviewer.decisions_count / stats.value.overview.total_results) * 100);
  }

  function formatAvgTime(seconds: number | null): string {
    if (!seconds) return 'N/A';

    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);

    if (minutes > 0) {
      return `${minutes}m ${remainingSeconds}s`;
    }
    return `${remainingSeconds}s`;
  }

  function getReviewerDisplayName(reviewer: ReviewerProgress, index: number): string {
    if (!isBlinded.value) {
      return reviewer.reviewer_name || `${reviewer.reviewer.first_name} ${reviewer.reviewer.last_name}`;
    }
    return `Reviewer ${index + 1}`;
  }

  function getReviewerPairName(metric: any): string {
    if (!metric.reviewer_a || !metric.reviewer_b) return 'Unknown Pair';

    if (isBlinded.value) {
      return 'Reviewer Pair';
    }

    const nameA = metric.reviewer_a.username || metric.reviewer_a.email;
    const nameB = metric.reviewer_b.username || metric.reviewer_b.email;
    return `${nameA} × ${nameB}`;
  }

  function calculateBothInclude(metric: any): number {
    return Math.floor(metric.agreements / 2);
  }

  function calculateBothExclude(metric: any): number {
    return Math.ceil(metric.agreements / 2);
  }

  // SSE event handlers
  function handleConflictEvent() {
    console.log('SSE event: Conflict detected, refreshing dashboard...');
    loadDashboard();
  }

  function handleConsensusEvent() {
    console.log('SSE event: Consensus reached, refreshing dashboard...');
    loadDashboard();
  }

  function handleIRREvent() {
    console.log('SSE event: IRR calculated, refreshing dashboard...');
    loadDashboard();
  }

  return {
    // State
    isLoading,
    error,
    stats,
    irrTrend,
    irrMetrics,
    reviewerProgress,
    blindingStatus,
    blindingError,
    sessionId,

    // Computed
    progressPercentage,
    cohensKappa,
    percentageAgreement,
    kappaInterpretation,
    kappaColorClass,
    kappaBadgeVariant,
    isBlinded,
    chartData,
    chartOptions,

    // Methods
    loadDashboard,
    handleRefresh,
    formatKappa,
    calculateReviewerProgress,
    formatAvgTime,
    getReviewerDisplayName,
    getReviewerPairName,
    getKappaInterpretation,
    getKappaColorClass,
    getKappaBadgeVariant,
    calculateBothInclude,
    calculateBothExclude,

    // SSE handlers
    handleConflictEvent,
    handleConsensusEvent,
    handleIRREvent,
  };
}
