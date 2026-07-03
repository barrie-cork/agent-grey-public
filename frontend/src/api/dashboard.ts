/**
 * Dashboard API - Team metrics and IRR tracking
 * Maps to apps/review_results/api/dashboard_views.py
 */

import apiClient from './client';
import type {
  TeamDashboardStats,
  InterRaterReliabilityResponse,
  IRRTrend,
} from '../types';

/**
 * Get team dashboard statistics
 * GET /api/dashboard/stats/
 */
export async function getDashboardStats(params: {
  session_id: string;
  period?: '7d' | '30d' | '90d' | 'all';
}): Promise<TeamDashboardStats> {
  const response = await apiClient.get<TeamDashboardStats>('/dashboard/stats/', {
    params,
  });
  return response.data;
}

/**
 * Get IRR metrics for session
 * GET /api/dashboard/irr/
 */
export async function getIRRMetrics(params: {
  session_id: string;
  reviewer1_id?: string;
  reviewer2_id?: string;
}): Promise<InterRaterReliabilityResponse[]> {
  const response = await apiClient.get<InterRaterReliabilityResponse[]>('/dashboard/irr/', {
    params,
  });
  return response.data;
}

/**
 * Get IRR trend over time
 * GET /api/dashboard/irr-trend/
 */
export async function getIRRTrend(params: {
  session_id: string;
  days?: number;
}): Promise<IRRTrend[]> {
  const response = await apiClient.get<IRRTrend[]>('/dashboard/irr-trend/', {
    params,
  });
  return response.data;
}

/**
 * Get reviewer progress
 * GET /api/dashboard/progress/
 */
export async function getReviewerProgress(sessionId: string) {
  const response = await apiClient.get(`/dashboard/progress/`, {
    params: { session_id: sessionId },
  });
  return response.data;
}

/**
 * Get team statistics
 * GET /api/dashboard/team-stats/
 * Alias for getDashboardStats for backward compatibility
 */
export async function getTeamStats(sessionId: string): Promise<TeamDashboardStats> {
  return getDashboardStats({ session_id: sessionId });
}
