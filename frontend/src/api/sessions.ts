/**
 * Sessions API - Session management and blinding
 * Maps to apps/review_manager/api/ and apps/review_results/api/core_views.py
 */

import apiClient from './client';
import type { BlindingStatus } from '../types';

/**
 * Get blinding status for a session
 * GET /api/sessions/{sessionId}/blinding-status/
 *
 * @param sessionId - UUID of the search session
 * @returns Server-authoritative blinding configuration
 * @throws {Error} If session not found or user lacks permission
 */
export async function getBlindingStatus(sessionId: string): Promise<BlindingStatus> {
  const response = await apiClient.get<BlindingStatus>(
    `/sessions/${sessionId}/blinding-status/`,
    {
      headers: {
        'Accept': 'application/json',
      },
    }
  );
  return response.data;
}
