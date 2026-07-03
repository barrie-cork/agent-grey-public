/**
 * Consensus Discussion Store
 * Manages conflict discussion state, comments, and re-vote workflow
 *
 * Phase 7: Pinia Store & Composables
 *
 * Features:
 * - Fetch and display conflict discussion details
 * - Post and thread discussion comments
 * - Propose, accept, and vote on re-votes
 * - Real-time updates via SSE (integrated in Phase 9)
 * - Permission-based UI states
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type {
  ConflictResolutionDetail,
  ConflictComment,
  ConflictCommentInput,
  RevoteProposal,
  RevoteProposalInput,
  RevoteDecisionInput,
  ReviewerDecision,
} from '../types';
import {
  getConflictDiscussionDetails,
  postComment,
  proposeRevote,
  acceptRevoteProposal,
  submitRevoteDecision,
  proposeDiscussionVote,
  respondToDiscussionVote,
} from '../api/consensusDiscussion';
import { useAuthStore } from './auth';
import { extractErrorMessage } from '../lib/errors';

export const useConsensusDiscussionStore = defineStore('consensusDiscussion', () => {
  // ============================================================================
  // STATE
  // ============================================================================

  const conflictDetail = ref<ConflictResolutionDetail | null>(null);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const isSubmitting = ref(false);

  // Track optimistic UI updates
  const optimisticComments = ref<ConflictComment[]>([]);

  // ============================================================================
  // GETTERS
  // ============================================================================

  /**
   * All comments (server + optimistic)
   */
  const allComments = computed(() => {
    if (!conflictDetail.value) return [];
    return [...conflictDetail.value.comments, ...optimisticComments.value];
  });

  /**
   * Active re-vote proposal (if any)
   */
  const activeRevoteProposal = computed(() => {
    return conflictDetail.value?.active_revote_proposal || null;
  });

  /**
   * Can current user comment?
   * - Must be authenticated
   * - Must be a conflicting reviewer
   * - Conflict must not be resolved
   */
  const canComment = computed(() => {
    const authStore = useAuthStore();
    if (!authStore.user || !conflictDetail.value) return false;

    const userId = authStore.user.id;
    const isConflictingReviewer = conflictDetail.value.conflicting_decisions?.some(
      (decision) => decision.reviewer.id === userId
    );

    return isConflictingReviewer && ['PENDING', 'IN_DISCUSSION', 'ESCALATED'].includes(conflictDetail.value.status);
  });

  /**
   * Can current user propose re-vote?
   * - Must be able to comment
   * - No active proposal exists
   * - At least one discussion comment exists
   */
  const canProposeRevote = computed(() => {
    if (!canComment.value || !conflictDetail.value) return false;

    const hasActiveProposal = activeRevoteProposal.value !== null;
    const hasDiscussion = conflictDetail.value.comments.length > 0;

    return !hasActiveProposal && hasDiscussion;
  });

  /**
   * Can current user accept the active proposal?
   * - Must be able to comment
   * - Active proposal exists in PROPOSED status
   * - User is in acceptance_required_from list
   * - User hasn't already accepted
   * - Proposal not expired
   */
  const canAcceptRevote = computed(() => {
    const authStore = useAuthStore();
    if (!canComment.value || !activeRevoteProposal.value || !authStore.user) return false;

    const proposal = activeRevoteProposal.value;
    const userId = authStore.user.id;

    const isRequiredToAccept = proposal.acceptance_required_from.some(
      (reviewer) => reviewer.id === userId
    );
    const hasAlreadyAccepted = proposal.accepted_by.some(
      (reviewer) => reviewer.id === userId
    );

    return (
      proposal.status === 'PROPOSED' &&
      !proposal.is_expired &&
      isRequiredToAccept &&
      !hasAlreadyAccepted
    );
  });

  /**
   * Can current user vote on the active proposal?
   * - Must be able to comment
   * - Active proposal exists in ACCEPTED status
   * - User hasn't voted yet on this proposal
   */
  const canVoteOnRevote = computed(() => {
    const authStore = useAuthStore();
    if (!canComment.value || !activeRevoteProposal.value || !authStore.user) return false;

    const proposal = activeRevoteProposal.value;
    const userId = authStore.user.id;

    // Check if user has already voted on this proposal
    const hasVoted = conflictDetail.value?.conflicting_decisions?.some(
      (decision) =>
        decision.reviewer.id === userId &&
        decision.is_revote &&
        decision.revote_proposal === proposal.id
    );

    return proposal.status === 'ACCEPTED' && !hasVoted;
  });

  /**
   * Has current user already voted on active proposal?
   */
  const hasVotedOnActiveProposal = computed(() => {
    const authStore = useAuthStore();
    if (!authStore.user || !activeRevoteProposal.value) return false;

    const proposal = activeRevoteProposal.value;
    const userId = authStore.user.id;

    return conflictDetail.value?.conflicting_decisions?.some(
      (decision) =>
        decision.reviewer.id === userId &&
        decision.is_revote &&
        decision.revote_proposal === proposal.id
    ) || false;
  });

  /**
   * Discussion summary stats
   */
  const discussionSummary = computed(() => {
    return conflictDetail.value?.discussion_summary || {
      total_comments: 0,
      last_comment_at: null,
      participant_count: 0,
    };
  });

  // ============================================================================
  // ACTIONS
  // ============================================================================

  /**
   * Fetch conflict discussion details
   * Loads full conflict data including comments, decisions, and active proposal
   */
  async function fetchConflictDetail(conflictId: string): Promise<void> {
    isLoading.value = true;
    error.value = null;

    try {
      const data = await getConflictDiscussionDetails(conflictId);
      conflictDetail.value = data;
      optimisticComments.value = []; // Clear optimistic updates
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to load conflict discussion');
      console.error('Consensus discussion fetch error:', err);
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Post a discussion comment
   * Supports threading via parent_comment parameter
   *
   * Optimistic UI: Adds comment locally before server confirmation
   */
  async function addComment(conflictId: string, input: ConflictCommentInput): Promise<ConflictComment | null> {
    if (!canComment.value) {
      error.value = 'You do not have permission to comment';
      return null;
    }

    isSubmitting.value = true;
    error.value = null;

    try {
      const newComment = await postComment(conflictId, input);

      // Add comment to conflict detail
      if (conflictDetail.value) {
        if (input.parent_comment) {
          // Find parent comment and add reply
          const addReplyToComment = (comments: ConflictComment[]): boolean => {
            for (const comment of comments) {
              if (comment.id === input.parent_comment) {
                comment.replies = comment.replies || [];
                comment.replies.push(newComment);
                return true;
              }
              if (comment.replies && addReplyToComment(comment.replies)) {
                return true;
              }
            }
            return false;
          };
          addReplyToComment(conflictDetail.value.comments);
        } else {
          // Add as top-level comment
          conflictDetail.value.comments.push(newComment);
        }

        // Update discussion summary
        conflictDetail.value.discussion_summary.total_comments++;
        conflictDetail.value.discussion_summary.last_comment_at = newComment.created_at;
      }

      return newComment;
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to post comment');
      console.error('Comment post error:', err);
      return null;
    } finally {
      isSubmitting.value = false;
    }
  }

  /**
   * Propose re-vote
   * Creates a new re-vote proposal with rationale
   *
   * Requirements:
   * - At least one discussion comment must exist
   * - No active proposal can exist
   */
  async function createRevoteProposal(conflictId: string, input: RevoteProposalInput): Promise<RevoteProposal | null> {
    if (!canProposeRevote.value) {
      error.value = 'Cannot propose re-vote at this time';
      return null;
    }

    isSubmitting.value = true;
    error.value = null;

    try {
      const proposal = await proposeRevote(conflictId, input);

      // Update conflict detail with new proposal
      if (conflictDetail.value) {
        conflictDetail.value.active_revote_proposal = proposal;
      }

      return proposal;
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to propose re-vote');
      console.error('Re-vote proposal error:', err);
      return null;
    } finally {
      isSubmitting.value = false;
    }
  }

  /**
   * Accept re-vote proposal
   * Current user accepts the active proposal
   *
   * Effects:
   * - Adds user to accepted_by list
   * - If all required reviewers accept, status changes to ACCEPTED
   * - Email sent when ready to vote
   */
  async function acceptProposal(conflictId: string, proposalId: string): Promise<RevoteProposal | null> {
    if (!canAcceptRevote.value) {
      error.value = 'Cannot accept this proposal';
      return null;
    }

    isSubmitting.value = true;
    error.value = null;

    try {
      const updatedProposal = await acceptRevoteProposal(conflictId, proposalId);

      // Update conflict detail with accepted proposal
      if (conflictDetail.value) {
        conflictDetail.value.active_revote_proposal = updatedProposal;
      }

      return updatedProposal;
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to accept proposal');
      console.error('Proposal acceptance error:', err);
      return null;
    } finally {
      isSubmitting.value = false;
    }
  }

  /**
   * Submit re-vote decision
   * Current user submits their new decision on the accepted proposal
   *
   * Validation:
   * - Proposal must be ACCEPTED
   * - Decision must be INCLUDE or EXCLUDE (no MAYBE)
   *
   * Effects:
   * - Creates new ReviewerDecision with is_revote=true
   * - Checks for consensus
   * - If consensus: Resolves conflict, sends email
   */
  async function submitVote(
    conflictId: string,
    proposalId: string,
    input: RevoteDecisionInput
  ): Promise<ReviewerDecision | null> {
    if (!canVoteOnRevote.value) {
      error.value = 'Cannot vote on this proposal';
      return null;
    }

    isSubmitting.value = true;
    error.value = null;

    try {
      const decision = await submitRevoteDecision(conflictId, proposalId, input);

      // Reload conflict detail to get updated state
      await fetchConflictDetail(conflictId);

      return decision;
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to submit re-vote decision');
      console.error('Re-vote decision error:', err);
      return null;
    } finally {
      isSubmitting.value = false;
    }
  }

  /**
   * Propose a straw poll
   */
  async function createDiscussionVote(conflictId: string, rationale: string): Promise<void> {
    isSubmitting.value = true;
    error.value = null;

    try {
      await proposeDiscussionVote(conflictId, rationale);
      // Reload to get the new comment with embedded vote
      await fetchConflictDetail(conflictId);
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to create straw poll');
      console.error('Straw poll creation error:', err);
    } finally {
      isSubmitting.value = false;
    }
  }

  /**
   * Respond to a straw poll
   */
  async function submitDiscussionVoteResponse(
    conflictId: string,
    voteId: string,
    decision: string
  ): Promise<void> {
    isSubmitting.value = true;
    error.value = null;

    try {
      await respondToDiscussionVote(conflictId, voteId, decision);
      // Reload to get updated vote results
      await fetchConflictDetail(conflictId);
    } catch (err: any) {
      error.value = extractErrorMessage(err, 'Failed to submit vote response');
      console.error('Straw poll response error:', err);
    } finally {
      isSubmitting.value = false;
    }
  }

  /**
   * Clear current conflict detail
   */
  function clearConflict(): void {
    conflictDetail.value = null;
    optimisticComments.value = [];
    error.value = null;
  }

  /**
   * Clear error
   */
  function clearError(): void {
    error.value = null;
  }

  // ============================================================================
  // RETURN
  // ============================================================================

  return {
    // State
    conflictDetail,
    isLoading,
    error,
    isSubmitting,

    // Getters
    allComments,
    activeRevoteProposal,
    canComment,
    canProposeRevote,
    canAcceptRevote,
    canVoteOnRevote,
    hasVotedOnActiveProposal,
    discussionSummary,

    // Actions
    fetchConflictDetail,
    addComment,
    createRevoteProposal,
    acceptProposal,
    submitVote,
    createDiscussionVote,
    submitDiscussionVoteResponse,
    clearConflict,
    clearError,
  };
});
