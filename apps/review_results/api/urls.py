"""
URL Configuration for Review Results APIs.

All URLs are prefixed with /api/
"""

from django.urls import path

from apps.review_results.api import (
    conflict_views,
    core_views,
    dashboard_views,
    sse_views,
)

app_name = "review_results_api"

urlpatterns = [
    # =========================================================================
    # CORE APIS (5 endpoints)
    # =========================================================================
    # POST /api/results/claim/ - Claim next available result
    path("results/claim/", core_views.ClaimResultView.as_view(), name="claim-result"),
    # POST /api/results/{id}/decide/ - Submit screening decision
    path(
        "results/<uuid:result_id>/decide/",
        core_views.SubmitDecisionView.as_view(),
        name="submit-decision",
    ),
    # POST /api/results/{id}/release/ - Release claimed result
    path(
        "results/<uuid:result_id>/release/",
        core_views.release_result,
        name="release-result",
    ),
    # GET /api/results/{id}/ - Get result details
    path(
        "results/<uuid:result_id>/", core_views.get_result_detail, name="result-detail"
    ),
    # POST /api/results/add-manual/ - Add manually discovered result
    path(
        "results/add-manual/",
        core_views.AddManualResultView.as_view(),
        name="add-manual-result",
    ),
    # GET /api/results/queue/ - View work queue
    path("results/queue/", core_views.get_work_queue, name="work-queue"),
    # GET /api/sessions/{id}/blinding-status/ - Get session blinding status
    path(
        "sessions/<uuid:session_id>/blinding-status/",
        core_views.get_blinding_status,
        name="blinding-status",
    ),
    # =========================================================================
    # CONFLICT APIS (4 endpoints)
    # =========================================================================
    # GET /api/conflicts/ - List conflicts (filterable)
    path("conflicts/", conflict_views.ConflictListView.as_view(), name="conflict-list"),
    # GET /api/conflicts/{id}/ - Get conflict details
    path(
        "conflicts/<uuid:conflict_id>/",
        conflict_views.get_conflict_detail,
        name="conflict-detail",
    ),
    # POST /api/conflicts/{id}/resolve/ - Resolve conflict
    path(
        "conflicts/<uuid:conflict_id>/resolve/",
        conflict_views.ResolveConflictView.as_view(),
        name="resolve-conflict",
    ),
    # POST /api/conflicts/{id}/discuss/ - Add discussion comment
    path(
        "conflicts/<uuid:conflict_id>/discuss/",
        conflict_views.add_conflict_discussion,
        name="conflict-discuss",
    ),
    # POST /api/conflicts/{id}/escalate/ - Escalate conflict to arbitrator
    path(
        "conflicts/<uuid:conflict_id>/escalate/",
        conflict_views.EscalateConflictView.as_view(),
        name="escalate-conflict",
    ),
    # =========================================================================
    # CONSENSUS DISCUSSION APIS (Phase 3 - 5 endpoints)
    # =========================================================================
    # GET /api/conflicts/{id}/details/ - Get full conflict discussion data
    path(
        "conflicts/<uuid:conflict_id>/details/",
        conflict_views.ConflictDetailView.as_view(),
        name="conflict-details",
    ),
    # POST /api/conflicts/{id}/comments/ - Create discussion comment
    path(
        "conflicts/<uuid:conflict_id>/comments/",
        conflict_views.ConflictCommentCreateView.as_view(),
        name="create-comment",
    ),
    # POST /api/conflicts/{id}/propose-revote/ - Propose re-vote
    path(
        "conflicts/<uuid:conflict_id>/propose-revote/",
        conflict_views.ProposeRevoteView.as_view(),
        name="propose-revote",
    ),
    # POST /api/conflicts/{id}/proposals/{proposal_id}/accept/ - Accept re-vote proposal
    path(
        "conflicts/<uuid:conflict_id>/proposals/<uuid:proposal_id>/accept/",
        conflict_views.AcceptRevoteView.as_view(),
        name="accept-revote",
    ),
    # POST /api/conflicts/{id}/proposals/{proposal_id}/submit-decision/ - Submit re-vote decision
    path(
        "conflicts/<uuid:conflict_id>/proposals/<uuid:proposal_id>/submit-decision/",
        conflict_views.SubmitRevoteDecisionView.as_view(),
        name="submit-revote-decision",
    ),
    # =========================================================================
    # IN-DISCUSSION VOTING (STRAW POLL) ENDPOINTS
    # =========================================================================
    # POST /api/conflicts/{id}/discussion-votes/ - Propose a straw poll
    path(
        "conflicts/<uuid:conflict_id>/discussion-votes/",
        conflict_views.ProposeDiscussionVoteView.as_view(),
        name="propose-discussion-vote",
    ),
    # POST /api/conflicts/{id}/discussion-votes/{vote_id}/respond/ - Respond to a straw poll
    path(
        "conflicts/<uuid:conflict_id>/discussion-votes/<uuid:vote_id>/respond/",
        conflict_views.RespondToDiscussionVoteView.as_view(),
        name="respond-discussion-vote",
    ),
    # =========================================================================
    # SSE REAL-TIME UPDATES (Phase 9 - 1 endpoint)
    # =========================================================================
    # GET /api/conflicts/{id}/stream/ - SSE stream for real-time conflict discussion updates
    path(
        "conflicts/<uuid:conflict_id>/stream/",
        sse_views.conflict_discussion_stream,
        name="conflict-stream",
    ),
    # =========================================================================
    # DASHBOARD APIS (3 endpoints)
    # =========================================================================
    # GET /api/dashboard/stats/ - Team metrics and progress
    path("dashboard/stats/", dashboard_views.get_team_stats, name="dashboard-stats"),
    # GET /api/dashboard/irr/ - Inter-rater reliability metrics
    path("dashboard/irr/", dashboard_views.get_irr_metrics, name="dashboard-irr"),
    # GET /api/dashboard/progress/ - Reviewer progress breakdown
    path(
        "dashboard/progress/",
        dashboard_views.get_reviewer_progress,
        name="dashboard-progress",
    ),
    # =========================================================================
    # SESSION-SPECIFIC APIS (1 endpoint)
    # =========================================================================
    # GET /api/sessions/{id}/irr-metrics/ - Session IRR metrics (alternative route)
    path(
        "sessions/<uuid:session_id>/irr-metrics/",
        dashboard_views.get_session_irr_metrics,
        name="session-irr-metrics",
    ),
    # POST /api/sessions/{id}/irr-calculate/ - Trigger IRR calculation
    path(
        "sessions/<uuid:session_id>/irr-calculate/",
        dashboard_views.trigger_session_irr_calculation,
        name="session-irr-calculate",
    ),
]
