/**
 * useConflictSSE Composable
 * Server-Sent Events (SSE) connection for real-time conflict discussion updates
 *
 * Phase 7: Pinia Store & Composables
 * Note: SSE backend endpoint will be implemented in Phase 9
 *
 * Features:
 * - Establish SSE connection to conflict discussion stream
 * - Handle real-time events: new comments, re-vote proposals, consensus reached
 * - Automatic reconnection with exponential backoff
 * - Connection state management
 * - Cleanup on component unmount
 *
 * SSE Events (from Phase 9 backend):
 * - new_comment: New discussion comment posted
 * - revote_proposed: Re-vote proposal created
 * - revote_accepted: Re-vote proposal accepted by all reviewers
 * - revote_decision_submitted: Reviewer submitted re-vote decision
 * - consensus_reached: Conflict resolved via re-vote consensus
 *
 * Usage:
 * ```typescript
 * import { useConflictSSE } from '@/composables/useConflictSSE'
 * import { useConsensusDiscussionStore } from '@/stores/consensusDiscussion'
 *
 * const { connect, disconnect, isConnected, connectionState } = useConflictSSE(conflictId)
 * const discussionStore = useConsensusDiscussionStore()
 *
 * onMounted(() => {
 *   connect()
 * })
 *
 * onUnmounted(() => {
 *   disconnect()
 * })
 * ```
 */

import { ref, onUnmounted } from 'vue';
import type { ConflictComment, RevoteProposal } from '../types';

/**
 * Connection states
 */
export type SSEConnectionState =
  | 'disconnected'  // Not connected
  | 'connecting'    // Attempting to connect
  | 'connected'     // Successfully connected
  | 'reconnecting'  // Reconnecting after disconnect
  | 'error';        // Connection error

/**
 * SSE event data types
 */
interface SSENewCommentEvent {
  comment: ConflictComment;
}

interface SSERevoteProposedEvent {
  proposal: RevoteProposal;
}

interface SSERevoteAcceptedEvent {
  proposal: RevoteProposal;
}

interface SSERevoteDecisionEvent {
  decision_id: string;
  reviewer_id: string;
  decision: string;
}

interface SSEConsensusReachedEvent {
  conflict_id: string;
  final_decision: string;
  resolved_at: string;
}

/**
 * Reconnection configuration
 */
const RECONNECT_CONFIG = {
  maxAttempts: 5,
  initialDelay: 1000,      // 1 second
  maxDelay: 8000,          // 8 seconds
  backoffMultiplier: 2,    // Exponential backoff: 1s, 2s, 4s, 8s
};

export function useConflictSSE(conflictId: string) {
  // ============================================================================
  // STATE
  // ============================================================================

  const eventSource = ref<EventSource | null>(null);
  const connectionState = ref<SSEConnectionState>('disconnected');
  const reconnectAttempts = ref(0);
  const reconnectTimer = ref<ReturnType<typeof setTimeout> | null>(null);

  // Computed convenience properties
  const isConnected = ref(false);
  const isConnecting = ref(false);
  const hasError = ref(false);
  const hasConnectedOnce = ref(false);

  // ============================================================================
  // SSE CONNECTION
  // ============================================================================

  /**
   * Connect to SSE stream
   * Endpoint: /api/conflicts/{id}/stream/ (Phase 9)
   */
  function connect(): void {
    if (eventSource.value) {
      console.warn('SSE already connected');
      return;
    }

    connectionState.value = reconnectAttempts.value > 0 ? 'reconnecting' : 'connecting';
    isConnecting.value = true;
    hasError.value = false;

    try {
      // SSE endpoint (Phase 9 backend)
      const sseUrl = `/api/conflicts/${conflictId}/stream/`;

      // Create EventSource
      eventSource.value = new EventSource(sseUrl, {
        withCredentials: true,
      });

      // Connection opened
      eventSource.value.onopen = handleOpen;

      // Connection error
      eventSource.value.onerror = handleError;

      // Register event listeners
      registerEventListeners();
    } catch (err) {
      console.error('SSE connection error:', err);
      handleError();
    }
  }

  /**
   * Disconnect from SSE stream
   * Cleans up EventSource and timers
   */
  function disconnect(): void {
    clearReconnectTimer();

    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }

    connectionState.value = 'disconnected';
    isConnected.value = false;
    isConnecting.value = false;
    reconnectAttempts.value = 0;
  }

  /**
   * Force reconnect
   * Useful for manual reconnection after network issues
   */
  function reconnect(): void {
    disconnect();
    reconnectAttempts.value = 0;
    connect();
  }

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  /**
   * Connection opened successfully
   */
  function handleOpen(): void {
    console.log('SSE connected:', conflictId);
    connectionState.value = 'connected';
    isConnected.value = true;
    isConnecting.value = false;
    hasError.value = false;
    hasConnectedOnce.value = true;
    reconnectAttempts.value = 0; // Reset on successful connection
  }

  /**
   * Connection error or closed
   * Implements automatic reconnection with exponential backoff
   */
  function handleError(): void {
    console.error('SSE connection error/closed');
    connectionState.value = 'error';
    isConnected.value = false;
    isConnecting.value = false;
    hasError.value = true;

    // Clean up current connection
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }

    // Attempt reconnection if under max attempts
    if (reconnectAttempts.value < RECONNECT_CONFIG.maxAttempts) {
      attemptReconnect();
    } else {
      console.error('SSE max reconnection attempts reached');
      connectionState.value = 'disconnected';
    }
  }

  /**
   * Attempt reconnection with exponential backoff
   */
  function attemptReconnect(): void {
    reconnectAttempts.value++;
    const delay = calculateReconnectDelay();

    console.log(`SSE reconnecting in ${delay}ms (attempt ${reconnectAttempts.value}/${RECONNECT_CONFIG.maxAttempts})`);

    reconnectTimer.value = setTimeout(() => {
      connect();
    }, delay);
  }

  /**
   * Calculate reconnection delay with exponential backoff
   * Formula: min(initialDelay * (backoffMultiplier ^ attempts), maxDelay)
   */
  function calculateReconnectDelay(): number {
    const delay = RECONNECT_CONFIG.initialDelay * Math.pow(
      RECONNECT_CONFIG.backoffMultiplier,
      reconnectAttempts.value - 1
    );
    return Math.min(delay, RECONNECT_CONFIG.maxDelay);
  }

  /**
   * Clear reconnection timer
   */
  function clearReconnectTimer(): void {
    if (reconnectTimer.value) {
      clearTimeout(reconnectTimer.value);
      reconnectTimer.value = null;
    }
  }

  // ============================================================================
  // SSE EVENT LISTENERS
  // ============================================================================

  /**
   * Register all SSE event listeners
   * Events correspond to Phase 3 backend triggers
   */
  function registerEventListeners(): void {
    if (!eventSource.value) return;

    // Event: New comment posted
    eventSource.value.addEventListener('new_comment', handleNewComment);

    // Event: Re-vote proposed
    eventSource.value.addEventListener('revote_proposed', handleRevoteProposed);

    // Event: Re-vote accepted
    eventSource.value.addEventListener('revote_accepted', handleRevoteAccepted);

    // Event: Re-vote decision submitted
    eventSource.value.addEventListener('revote_decision_submitted', handleRevoteDecisionSubmitted);

    // Event: Consensus reached
    eventSource.value.addEventListener('consensus_reached', handleConsensusReached);

    // Event: Discussion vote updated (straw poll)
    eventSource.value.addEventListener('discussion_vote_updated', handleDiscussionVoteUpdated);
  }

  /**
   * Handle new_comment event
   * Triggers when any reviewer posts a comment
   */
  function handleNewComment(event: MessageEvent): void {
    try {
      const data: SSENewCommentEvent = JSON.parse(event.data);
      console.log('SSE event: new_comment', data);

      // Emit custom event for components to handle
      window.dispatchEvent(new CustomEvent('conflict:new_comment', {
        detail: data.comment,
      }));
    } catch (err) {
      console.error('Error handling new_comment event:', err);
    }
  }

  /**
   * Handle revote_proposed event
   * Triggers when a reviewer proposes re-vote
   */
  function handleRevoteProposed(event: MessageEvent): void {
    try {
      const data: SSERevoteProposedEvent = JSON.parse(event.data);
      console.log('SSE event: revote_proposed', data);

      window.dispatchEvent(new CustomEvent('conflict:revote_proposed', {
        detail: data.proposal,
      }));
    } catch (err) {
      console.error('Error handling revote_proposed event:', err);
    }
  }

  /**
   * Handle revote_accepted event
   * Triggers when all reviewers accept the proposal
   */
  function handleRevoteAccepted(event: MessageEvent): void {
    try {
      const data: SSERevoteAcceptedEvent = JSON.parse(event.data);
      console.log('SSE event: revote_accepted', data);

      window.dispatchEvent(new CustomEvent('conflict:revote_accepted', {
        detail: data.proposal,
      }));
    } catch (err) {
      console.error('Error handling revote_accepted event:', err);
    }
  }

  /**
   * Handle revote_decision_submitted event
   * Triggers when a reviewer submits their re-vote decision
   */
  function handleRevoteDecisionSubmitted(event: MessageEvent): void {
    try {
      const data: SSERevoteDecisionEvent = JSON.parse(event.data);
      console.log('SSE event: revote_decision_submitted', data);

      window.dispatchEvent(new CustomEvent('conflict:revote_decision', {
        detail: data,
      }));
    } catch (err) {
      console.error('Error handling revote_decision_submitted event:', err);
    }
  }

  /**
   * Handle discussion_vote_updated event
   * Triggers when a straw poll is created or responded to
   */
  function handleDiscussionVoteUpdated(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data);
      console.log('SSE event: discussion_vote_updated', data);

      window.dispatchEvent(new CustomEvent('conflict:discussion_vote_updated', {
        detail: data,
      }));
    } catch (err) {
      console.error('Error handling discussion_vote_updated event:', err);
    }
  }

  /**
   * Handle consensus_reached event
   * Triggers when conflict is resolved via re-vote consensus
   */
  function handleConsensusReached(event: MessageEvent): void {
    try {
      const data: SSEConsensusReachedEvent = JSON.parse(event.data);
      console.log('SSE event: consensus_reached', data);

      window.dispatchEvent(new CustomEvent('conflict:consensus_reached', {
        detail: data,
      }));
    } catch (err) {
      console.error('Error handling consensus_reached event:', err);
    }
  }

  // ============================================================================
  // LIFECYCLE
  // ============================================================================

  /**
   * Cleanup on component unmount
   */
  onUnmounted(() => {
    disconnect();
  });

  // ============================================================================
  // RETURN
  // ============================================================================

  return {
    // Connection methods
    connect,
    disconnect,
    reconnect,

    // Connection state
    connectionState,
    isConnected,
    isConnecting,
    hasError,
    hasConnectedOnce,
    reconnectAttempts,
  };
}
