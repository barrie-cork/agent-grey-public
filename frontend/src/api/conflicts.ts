/**
 * Conflicts API - Conflict resolution endpoints
 * Maps to apps/review_results/api/conflict_views.py
 */

import apiClient from './client';
import type { PaginatedResponse } from './client';
import type {
  ConflictResolution,
  ConflictListFilter,
  ResolveConflictInput,
} from '../types';

export interface SessionCounts {
  total: number;
  resolved: number;
  pending: number;
}

export interface ConflictListResponse extends PaginatedResponse<ConflictResolution> {
  session_counts?: SessionCounts;
}

/**
 * List conflicts for session
 * GET /api/conflicts/
 */
export async function listConflicts(params?: ConflictListFilter): Promise<ConflictListResponse> {
  const response = await apiClient.get<ConflictListResponse>(
    '/conflicts/',
    { params }
  );
  return response.data;
}

/**
 * Get conflict details
 * GET /api/conflicts/{id}/
 */
export async function getConflict(conflictId: string): Promise<ConflictResolution> {
  const response = await apiClient.get<ConflictResolution>(`/conflicts/${conflictId}/`);
  return response.data;
}

/**
 * Resolve conflict
 * POST /api/conflicts/{id}/resolve/
 */
export async function resolveConflict(
  conflictId: string,
  data: ResolveConflictInput
): Promise<ConflictResolution> {
  const response = await apiClient.post<ConflictResolution>(
    `/conflicts/${conflictId}/resolve/`,
    data
  );
  return response.data;
}

/**
 * Escalate conflict to arbitrator
 * POST /api/conflicts/{id}/escalate/
 */
export async function escalateConflict(
  conflictId: string,
  reason?: string
): Promise<ConflictResolution> {
  const response = await apiClient.post<ConflictResolution>(
    `/conflicts/${conflictId}/escalate/`,
    { reason: reason || '' }
  );
  return response.data;
}

