/**
 * TypeScript types matching Django models and serializers
 * Based on apps/review_results/serializers.py and models.py
 */

// ============================================================================
// USER & ORGANISATION TYPES
// ============================================================================

export interface User {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
}

export interface Organisation {
  id: string;
  name: string;
  created_at: string;
}

export interface OrganisationMembership {
  id: string;
  organisation: Organisation;
  user: User;
  role: 'REVIEWER' | 'LEAD_REVIEWER' | 'SENIOR_RESEARCHER' | 'INFORMATION_SPECIALIST' | 'ARBITRATOR';
  joined_at: string;
}

// ============================================================================
// SESSION TYPES
// ============================================================================

export interface SearchSession {
  id: string;
  title: string;
  status: 'draft' | 'defining_search' | 'ready_to_execute' | 'executing' |
          'processing_results' | 'ready_for_review' | 'under_review' |
          'completed' | 'archived';
  review_mode: 'SINGLE' | 'DUAL' | 'TRIPLE';
  organisation: Organisation;
  created_by: User;
  created_at: string;
  updated_at: string;
}

// ============================================================================
// RESULT TYPES
// ============================================================================

export interface ProcessedResult {
  id: string;
  session: string | { id: string; title: string; status: string };  // UUID or nested object
  title: string;
  snippet: string;
  url: string;
  source_name?: string;
  result_type?: string;
  date_published?: string;
  authors?: string;
  is_duplicate: boolean;
  duplicate_of?: string;
  my_decision?: string;  // User's existing decision (lowercase), null if none
  created_at: string;
}

// ============================================================================
// REVIEWER ASSIGNMENT TYPES
// ============================================================================

export interface ReviewerAssignment {
  id: string;
  result: string;  // ProcessedResult UUID
  reviewer: User;
  role: 'PRIMARY' | 'SECONDARY' | 'ARBITRATOR';
  // Grey literature: single-stage screening only (always 'SCREENING')
  screening_stage: 'SCREENING';
  claimed_at: string;
  is_active: boolean;
}

// ============================================================================
// REVIEWER DECISION TYPES
// ============================================================================

export type DecisionType = 'INCLUDE' | 'EXCLUDE' | 'MAYBE';
export type ConfidenceLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export interface ReviewerDecision {
  id: string;
  assignment: string;  // ReviewerAssignment UUID
  result: string;  // ProcessedResult UUID
  reviewer: User;
  decision: DecisionType;
  exclusion_reason?: string;
  confidence_level: ConfidenceLevel;
  notes?: string;
  time_spent_seconds: number;
  report_accessed: boolean;
  decided_at: string;
  // Grey literature: single-stage screening only (always 'SCREENING')
  screening_stage: 'SCREENING';
  is_blinded: boolean;
  version: number;
  // Phase 3: Re-vote tracking
  is_revote: boolean;
  revote_proposal?: string;  // RevoteProposal UUID (if is_revote=true)
}

export interface ReviewerDecisionInput {
  decision: DecisionType;
  exclusion_reason?: string;
  confidence_level: number;  // 1 = LOW, 2 = MEDIUM, 3 = HIGH
  notes?: string;
  time_spent_seconds?: number;  // Optional - calculated by frontend
  // Grey literature: single-stage screening only (always 'SCREENING', optional field defaults to 'SCREENING')
  screening_stage?: 'SCREENING';
}

// Full decision response from backend (extends ReviewerDecisionOutputSerializer)
export interface DecisionResponse extends ReviewerDecision {
  status?: 'consensus_reached' | 'awaiting_second_reviewer' | 'conflict_detected';
  message?: string;
  conflict_id?: string;
  conflict_type?: string;
}

// ============================================================================
// CONFLICT RESOLUTION TYPES
// ============================================================================

export type ConflictType =
  | 'INCLUDE_EXCLUDE'
  | 'INCLUDE_MAYBE'
  | 'EXCLUDE_MAYBE'
  | 'MULTIPLE_DISAGREEMENT';

export type ConflictStatus = 'PENDING' | 'IN_DISCUSSION' | 'ESCALATED' | 'RESOLVED';

export type ResolutionMethod =
  | 'CONSENSUS'
  | 'ARBITRATION'
  | 'MAJORITY'
  | 'LEAD_DECISION'
  | 'SENIOR_OVERRIDE';

export type CriterionTag =
  | 'relevance'
  | 'grey_lit_classification'
  | 'document_type'
  | 'population'
  | 'intervention_interest'
  | 'context'
  | 'full_text_availability'
  | 'language'
  | 'other';

export interface SlaInfo {
  deadline: string;
  hours_remaining: number;
  hours_overdue: number;
  percent_elapsed: number;
  is_approaching: boolean;
  is_critical: boolean;
  is_overdue: boolean;
  sla_hours: number;
}

export interface ConflictResolution {
  id: string;
  result: ProcessedResult;
  conflict_type: ConflictType;
  status: ConflictStatus;
  conflicting_decisions: ReviewerDecision[];
  detected_at: string;
  resolved_at?: string;
  resolution_method?: ResolutionMethod;
  final_decision?: DecisionType;
  resolved_by?: User;
  arbitrator?: User;
  discussion_notes?: string;
  resolution_notes?: string;
  is_resolved: boolean;
  sla_info?: SlaInfo | null;
}

export interface ConflictItem {
  id: string;
  result: ProcessedResult;
  conflict_type: ConflictType;
  conflicting_decisions: ReviewerDecision[];
  detected_at: string;
  resolved_at?: string;
  resolution_method?: ResolutionMethod;
  final_decision?: DecisionType;
  resolved_by?: User;
  arbitrator?: User;
  discussion_notes?: string;
  is_resolved: boolean;
  status: 'pending' | 'in_discussion' | 'resolved';
  sla_info?: SlaInfo | null;
}

// ============================================================================
// INTER-RATER RELIABILITY TYPES
// ============================================================================

export interface InterRaterReliability {
  id: string;
  session: string;  // SearchSession UUID
  reviewer1: User;
  reviewer2: User;
  cohens_kappa: number;
  percentage_agreement: number;
  total_comparisons: number;
  agreements: number;
  disagreements: number;
  // Grey literature: single-stage screening only (always 'SCREENING')
  screening_stage: 'SCREENING';
  calculated_at: string;
}

// ============================================================================
// DASHBOARD TYPES
// ============================================================================

// Backend API response structure from dashboard_views.py
export interface TeamDashboardStats {
  session: {
    id: string;
    title: string;
    status: string;
  };
  overview: {
    total_results: number;
    reviewed: number;
    pending: number;
    included: number;
    excluded: number;
    conflicts: number;
    conflicts_resolved: number;
    pending_conflicts: number;
  };
  progress: {
    percentage_complete: number;
  };
  team_performance: {
    active_reviewers: number;
    reviews_today: number;
    reviews_this_week: number;
    average_time_per_review_seconds: number;
    conflict_rate_percentage: number;
  };
  inter_rater_reliability: {
    average_kappa: number | null;
    average_agreement: number | null;
    pairs_below_threshold: number;
    total_pairs: number;
    meets_cochrane: boolean;
    cochrane_threshold: number;
    calculated_at?: string;
    note?: string;
  };
  reviewer_breakdown: Array<{
    reviewer: {
      id: string;
      username: string;
      email: string;
    };
    total_reviews: number;
    reviews_today: number;
    average_time_seconds: number;
    inclusion_rate_percentage: number;
    current_status: 'active' | 'idle';
    last_activity: string;
  }>;
}

// Legacy flat structure (kept for backward compatibility)
export interface LegacyTeamDashboardStats {
  session: SearchSession;
  total_results: number;
  reviewed_count: number;
  completed_results: number;
  results_reviewed: number;
  pending_count: number;
  pending_conflicts: number;
  conflicts_count: number;
  resolved_conflicts_count: number;
  cohens_kappa?: number | null;
  percentage_agreement?: number | null;
  irr_metrics?: {
    cohens_kappa: number;
    interpretation: string;
    percentage_agreement: number;
  };
  reviewer_progress: ReviewerProgress[];
}

export interface ReviewerProgress {
  reviewer: User;
  reviewer_name?: string;
  reviewed_count: number;
  decisions_count: number;
  conflicts_count: number;
  conflicts_involved?: number;
  avg_time_seconds: number;
  last_review_at?: string;
}

export interface IRRTrend {
  date: string;
  cohens_kappa: number;
  comparisons: number;
}

/**
 * Simplified IRR metric for dashboard display.
 * Contains a subset of InterRaterReliabilityResponse fields used in TeamDashboard.vue.
 * Full response structure is in InterRaterReliabilityResponse below.
 */
export interface IRRMetric {
  id: string;
  cohens_kappa: number;
  interpretation: string;
  percentage_agreement: number;
  total_comparisons: number;
  agreements: number;
  disagreements: number;
  calculated_at: string;
}

// Backend InterRaterReliability serializer response
export interface InterRaterReliabilityResponse {
  id: string;
  search_session: {
    id: string;
    title: string;
  };
  reviewer_a: {
    id: string;
    username: string;
    email: string;
  };
  reviewer_b: {
    id: string;
    username: string;
    email: string;
  };
  cohens_kappa: number | null;
  percentage_agreement: number;
  total_comparisons: number;
  agreements: number;
  disagreements: number;
  screening_stage: string;
  calculated_at: string;
  calculation_window_start: string;
  calculation_window_end: string;
  meets_cochrane_threshold: boolean;
}

// ============================================================================
// WORK QUEUE TYPES
// ============================================================================

export interface WorkQueueFilter {
  status?: 'pending' | 'claimed' | 'conflicts' | 'pending' | 'in_discussion' | 'resolved';
  session_id?: string;
  // Grey literature: single-stage screening only (always 'SCREENING', optional field defaults to 'SCREENING')
  screening_stage?: 'SCREENING';
  is_resolved?: boolean;
  page?: number;
  per_page?: number;
}

export interface ConflictListFilter {
  session_id?: string;
  status?: 'PENDING' | 'RESOLVED';
  is_resolved?: boolean;
  page?: number;
  per_page?: number;
}

export interface WorkQueueResult {
  result: ProcessedResult;
  status: 'pending' | 'claimed_by_me' | 'claimed_by_other' | 'decided_by_me' | 'conflict';
  my_decision?: ReviewerDecision;
  claim_info?: {
    claimed_by: User;
    claimed_at: string;
  };
}

// ============================================================================
// API ENDPOINT TYPES
// ============================================================================

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
  page?: number;
  num_pages?: number;
}

export interface ClaimResultInput {
  session_id?: string;
  // Grey literature: single-stage screening only (always 'SCREENING', optional field defaults to 'SCREENING')
  screening_stage?: 'SCREENING';
}

export interface ResolveConflictInput {
  decision: DecisionType;
  exclusion_reason?: string;
  resolution_notes?: string;
}

// ============================================================================
// CONSENSUS DISCUSSION TYPES (Phase 6)
// ============================================================================

export interface ConflictComment {
  id: string;
  conflict: string;  // ConflictResolution UUID
  author: User;
  parent_comment?: string;  // UUID of parent comment (for threading)
  content: string;
  is_system_message: boolean;
  is_edited: boolean;
  is_deleted: boolean;
  criterion_tag?: CriterionTag;
  criterion_tag_display?: string;
  created_at: string;
  updated_at: string;
  replies?: ConflictComment[];  // Nested replies (populated by serializer)
  discussion_vote?: InDiscussionVote;  // Present if this comment initiated a straw poll
}

export interface ConflictCommentInput {
  content: string;
  parent_comment?: string;  // UUID for replying to a comment
  criterion_tag?: CriterionTag;
}

export type RevoteProposalStatus = 'PROPOSED' | 'ACCEPTED' | 'REJECTED' | 'EXPIRED' | 'IN_PROGRESS' | 'COMPLETED';

export interface RevoteProposal {
  id: string;
  conflict: string;  // ConflictResolution UUID
  proposed_by: User;
  rationale: string;
  status: RevoteProposalStatus;
  acceptance_required_from: User[];
  accepted_by: User[];
  proposed_at: string;
  expires_at: string;
  completed_at?: string;
  is_expired: boolean;
  is_accepted: boolean;
  is_completed: boolean;
}

export interface RevoteProposalInput {
  rationale: string;
}

export interface RevoteDecisionInput {
  decision: DecisionType;
  notes?: string;
  confidence_level?: number;
}

// Extended ConflictResolution for discussion interface
export interface ConflictResolutionDetail extends ConflictResolution {
  comments: ConflictComment[];
  active_revote_proposal?: RevoteProposal;
  discussion_summary: {
    total_comments: number;
    last_comment_at?: string;
    participant_count: number;
  };
  _permissions?: {
    can_comment: boolean;
    can_propose_revote: boolean;
    can_accept_revote: boolean;
    can_resolve: boolean;
    can_escalate: boolean;
  };
}

// ============================================================================
// IN-DISCUSSION VOTING (STRAW POLL) TYPES
// ============================================================================

export interface InDiscussionVoteResponse {
  id: string;
  reviewer: User;
  decision: DecisionType;
  responded_at: string;
}

export interface InDiscussionVote {
  id: string;
  conflict: string;
  proposed_by: User;
  rationale: string;
  is_closed: boolean;
  closed_at?: string;
  created_at: string;
  responses: InDiscussionVoteResponse[];
  results_summary: {
    total: number;
    include: number;
    exclude: number;
    maybe: number;
  };
}

// ============================================================================
// BLINDING TYPES
// ============================================================================

/**
 * Server-provided blinding configuration for a review session
 * Used to enforce PRISMA 2020 independent review requirements
 */
export interface BlindingStatus {
  /** Whether blinding is currently active for this session */
  is_blinded: boolean;
  /** Minimum number of reviewers required before unblinding */
  min_reviewers: number;
  /** Human-readable explanation of blinding status */
  reason: string;
}

/**
 * Constants for blinding configuration
 */
export const BLINDING_CONSTANTS = {
  /** Default minimum reviewers if not specified by server */
  MIN_REVIEWERS_DEFAULT: 2,
  /** API endpoint timeout for blinding status fetch (ms) */
  BLINDING_STATUS_TIMEOUT: 5000,
} as const;
