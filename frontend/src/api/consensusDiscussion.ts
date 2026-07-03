/**
 * Consensus Discussion API - Conflict discussion and re-vote endpoints
 * Maps to apps/review_results/api/conflict_views.py (Phase 3 endpoints)
 *
 * Phase 7: Pinia Store & Composables
 *
 * API Endpoints (all implemented in Phase 3):
 * - GET  /api/conflicts/{id}/details/           - Fetch full conflict discussion data
 * - POST /api/conflicts/{id}/comments/          - Post discussion comment
 * - POST /api/conflicts/{id}/propose-revote/    - Propose re-vote
 * - POST /api/conflicts/{id}/proposals/{id}/accept/          - Accept re-vote proposal
 * - POST /api/conflicts/{id}/proposals/{id}/submit-decision/ - Submit re-vote decision
 */

import apiClient from './client';
import type {
  ConflictResolutionDetail,
  ConflictComment,
  ConflictCommentInput,
  RevoteProposal,
  RevoteProposalInput,
  RevoteDecisionInput,
  ReviewerDecision,
  InDiscussionVote,
} from '../types';

/**
 * Get full conflict discussion details
 * GET /api/conflicts/{id}/details/
 *
 * Returns:
 * - Conflict resolution info
 * - Conflicting decisions
 * - All discussion comments (threaded)
 * - Active re-vote proposal (if any)
 * - Discussion summary stats
 */
export async function getConflictDiscussionDetails(conflictId: string): Promise<ConflictResolutionDetail> {
  const response = await apiClient.get(`/conflicts/${conflictId}/details/`);
  const data = response.data;
  // Backend returns { conflict, comments, active_revote_proposal, permissions }
  // Unwrap into the flat ConflictResolutionDetail shape the store expects
  return {
    ...data.conflict,
    comments: data.comments ?? [],
    active_revote_proposal: data.active_revote_proposal ?? undefined,
    discussion_summary: data.conflict?.discussion_summary ?? { total_comments: 0, participant_count: 0 },
    _permissions: data.permissions,
  } as ConflictResolutionDetail;
}

/**
 * Post a discussion comment
 * POST /api/conflicts/{id}/comments/
 *
 * Permissions:
 * - Only conflicting reviewers can comment
 *
 * Request body:
 * - content: string (markdown supported)
 * - parent_comment?: string (UUID for threading)
 *
 * Triggers:
 * - Email notification to other reviewers
 * - SessionActivity log
 * - System message if first comment
 */
export async function postComment(
  conflictId: string,
  input: ConflictCommentInput
): Promise<ConflictComment> {
  const response = await apiClient.post<ConflictComment>(
    `/conflicts/${conflictId}/comments/`,
    input
  );
  return response.data;
}

/**
 * Propose re-vote
 * POST /api/conflicts/{id}/propose-revote/
 *
 * Permissions:
 * - Only conflicting reviewers can propose
 * - Only one active proposal allowed per conflict
 *
 * Request body:
 * - rationale: string (markdown supported)
 *
 * Creates:
 * - RevoteProposal with status PROPOSED
 * - System message in discussion
 * - Email notification to other reviewers
 * - 48-hour expiry timer
 *
 * Triggers:
 * - Email notification with proposal details
 * - SessionActivity log
 */
export async function proposeRevote(
  conflictId: string,
  input: RevoteProposalInput
): Promise<RevoteProposal> {
  const response = await apiClient.post<RevoteProposal>(
    `/conflicts/${conflictId}/propose-revote/`,
    input
  );
  return response.data;
}

/**
 * Accept re-vote proposal
 * POST /api/conflicts/{id}/proposals/{proposal_id}/accept/
 *
 * Permissions:
 * - Only conflicting reviewers can accept
 * - Proposer cannot accept their own proposal
 *
 * Validation:
 * - Proposal must be in PROPOSED status
 * - Proposal must not be expired
 * - Reviewer must be in acceptance_required_from list
 *
 * Effects:
 * - Adds reviewer to accepted_by list
 * - If all required reviewers accept:
 *   - Status changes to ACCEPTED
 *   - Email sent to all reviewers: "Ready to re-vote"
 *   - System message created
 *
 * Triggers:
 * - Email notification when all accept
 * - SessionActivity log
 */
export async function acceptRevoteProposal(
  conflictId: string,
  proposalId: string
): Promise<RevoteProposal> {
  const response = await apiClient.post<RevoteProposal>(
    `/conflicts/${conflictId}/proposals/${proposalId}/accept/`
  );
  return response.data;
}

/**
 * Submit re-vote decision
 * POST /api/conflicts/{id}/proposals/{proposal_id}/submit-decision/
 *
 * Permissions:
 * - Only conflicting reviewers can submit
 * - Each reviewer can only vote once per proposal
 *
 * Validation:
 * - Proposal must be ACCEPTED (all reviewers accepted)
 * - Decision must be INCLUDE or EXCLUDE (MAYBE not allowed in re-votes)
 *
 * Request body:
 * - decision: DecisionType ("INCLUDE" | "EXCLUDE")
 * - notes?: string
 * - confidence_level?: number (1-5)
 *
 * Effects:
 * - Creates new ReviewerDecision with is_revote=true
 * - Marks old decision as superseded (is_active=false)
 * - If all reviewers vote:
 *   - Checks for consensus
 *   - If consensus: Resolves conflict, sends celebration email
 *   - If still conflicting: Proposal status COMPLETED, conflict remains PENDING
 *
 * Triggers:
 * - Email notification on consensus
 * - SessionActivity log
 * - System message on consensus
 */
export async function submitRevoteDecision(
  conflictId: string,
  proposalId: string,
  input: RevoteDecisionInput
): Promise<ReviewerDecision> {
  const response = await apiClient.post<ReviewerDecision>(
    `/conflicts/${conflictId}/proposals/${proposalId}/submit-decision/`,
    input
  );
  return response.data;
}

// ============================================================================
// IN-DISCUSSION VOTING (STRAW POLL) API
// ============================================================================

/**
 * Propose a straw poll during conflict discussion
 * POST /api/conflicts/{id}/discussion-votes/
 */
export async function proposeDiscussionVote(
  conflictId: string,
  rationale: string
): Promise<InDiscussionVote> {
  const response = await apiClient.post<InDiscussionVote>(
    `/conflicts/${conflictId}/discussion-votes/`,
    { rationale }
  );
  return response.data;
}

/**
 * Respond to a straw poll
 * POST /api/conflicts/{id}/discussion-votes/{voteId}/respond/
 */
export async function respondToDiscussionVote(
  conflictId: string,
  voteId: string,
  decision: string
): Promise<InDiscussionVote> {
  const response = await apiClient.post<InDiscussionVote>(
    `/conflicts/${conflictId}/discussion-votes/${voteId}/respond/`,
    { decision }
  );
  return response.data;
}
