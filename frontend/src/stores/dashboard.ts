/**
 * Dashboard Store
 * Manages team dashboard statistics and IRR metrics
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { TeamDashboardStats, IRRTrend, InterRaterReliabilityResponse } from '../types';
import { getDashboardStats, getIRRTrend, getIRRMetrics } from '../api/dashboard';
import { useOrganisationStore } from './organisation';

export const useDashboardStore = defineStore('dashboard', () => {
  // State
  const stats = ref<TeamDashboardStats | null>(null);
  const irrTrend = ref<IRRTrend[]>([]);
  const irrMetrics = ref<InterRaterReliabilityResponse[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const lastRefresh = ref<Date | null>(null);

  // Getters
  const progressPercentage = computed(() => {
    if (!stats.value) return 0;
    return Math.round(stats.value.progress.percentage_complete);
  });

  const cohensKappa = computed(() => {
    return stats.value?.inter_rater_reliability?.average_kappa || null;
  });

  const kappaInterpretation = computed(() => {
    if (!cohensKappa.value) return null;
    const kappa = cohensKappa.value;

    if (kappa < 0) return 'Poor agreement';
    if (kappa < 0.20) return 'Slight agreement';
    if (kappa < 0.40) return 'Fair agreement';
    if (kappa < 0.60) return 'Moderate agreement';
    if (kappa < 0.80) return 'Substantial agreement';
    return 'Almost perfect agreement';
  });

  const needsCalibration = computed(() => {
    // Cochrane minimum threshold
    return cohensKappa.value !== null && cohensKappa.value < 0.70;
  });

  const hasConflicts = computed(() => {
    return stats.value ? stats.value.overview.conflicts > 0 : false;
  });

  // Actions
  async function fetchDashboardStats(sessionId: string, period: '7d' | '30d' | '90d' | 'all' = '30d') {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return;

    isLoading.value = true;
    error.value = null;

    try {
      const data = await getDashboardStats({
        session_id: sessionId,
        period,
      });

      stats.value = data;
      lastRefresh.value = new Date();
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Failed to fetch dashboard stats';
      console.error('Dashboard error:', err);
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchIRRTrend(sessionId: string, days: number = 30) {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return;

    try {
      const data = await getIRRTrend({
        session_id: sessionId,
        days,
      });

      irrTrend.value = data;
    } catch (err: any) {
      console.error('IRR trend error:', err);
    }
  }

  async function fetchIRRMetrics(sessionId: string, reviewer1Id?: string, reviewer2Id?: string) {
    const orgStore = useOrganisationStore();
    if (!orgStore.checkOrganisationContext()) return;

    try {
      const data = await getIRRMetrics({
        session_id: sessionId,
        reviewer1_id: reviewer1Id,
        reviewer2_id: reviewer2Id,
      });

      irrMetrics.value = data;
    } catch (err: any) {
      console.error('IRR metrics error:', err);
    }
  }

  async function refreshAll(sessionId: string) {
    await Promise.all([
      fetchDashboardStats(sessionId),
      fetchIRRTrend(sessionId),
    ]);
  }

  function clearDashboard() {
    stats.value = null;
    irrTrend.value = [];
    irrMetrics.value = [];
    error.value = null;
    lastRefresh.value = null;
  }

  return {
    // State
    stats,
    irrTrend,
    irrMetrics,
    isLoading,
    error,
    lastRefresh,
    // Getters
    progressPercentage,
    cohensKappa,
    kappaInterpretation,
    needsCalibration,
    hasConflicts,
    // Actions
    fetchDashboardStats,
    fetchIRRTrend,
    fetchIRRMetrics,
    refreshAll,
    clearDashboard,
  };
});
