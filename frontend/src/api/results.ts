/**
 * Results API - Core dual screening endpoints
 * Maps to apps/review_results/api/core_views.py
 */

import apiClient from './client';
import type { PaginatedResponse } from './client';
import type {
  ProcessedResult,
  ClaimResultInput,
  ReviewerDecisionInput,
  DecisionResponse,
  WorkQueueFilter,
  WorkQueueResult,
} from '../types';

/**
 * Claim next available result for review
 * POST /api/results/claim/
 */
export async function claimNextResult(
  data: ClaimResultInput
): Promise<ProcessedResult> {
  const response = await apiClient.post<ProcessedResult>('/results/claim/', data);
  return response.data;
}

/**
 * Submit screening decision
 * POST /api/results/{id}/decide/
 */
export async function submitDecision(
  resultId: string,
  data: ReviewerDecisionInput
): Promise<DecisionResponse> {
  const response = await apiClient.post<DecisionResponse>(
    `/results/${resultId}/decide/`,
    data
  );
  return response.data;
}

/**
 * Release claimed result
 * POST /api/results/{id}/release/
 */
export async function releaseResult(resultId: string): Promise<{ message: string }> {
  const response = await apiClient.post(`/results/${resultId}/release/`);
  return response.data;
}

/**
 * Get result details
 * GET /api/results/{id}/
 */
export async function getResult(resultId: string): Promise<ProcessedResult> {
  const response = await apiClient.get<ProcessedResult>(`/results/${resultId}/`);
  return response.data;
}

/**
 * Track URL access for PRISMA compliance
 * POST /review-results/api/{sessionId}/track-url/
 */
export async function trackUrlAccess(
  sessionId: string,
  resultId: string
): Promise<void> {
  const params = new URLSearchParams({
    result_id: resultId,
    success: 'true',
  });
  await apiClient.post(
    `/review-results/api/${sessionId}/track-url/`,
    params.toString(),
    {
      baseURL: '/',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }
  );
}

/**
 * Get work queue
 * GET /api/results/queue/
 */
export async function getWorkQueue(
  filters?: WorkQueueFilter
): Promise<PaginatedResponse<WorkQueueResult>> {
  const response = await apiClient.get<PaginatedResponse<WorkQueueResult>>(
    '/results/queue/',
    { params: filters }
  );
  return response.data;
}
