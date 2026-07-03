"""
URL configuration for review_results app.

This module defines the URL patterns for the Review Results interface.
Provides endpoints for reviewing processed results with Include/Exclude decisions.
"""

from django.urls import path

from . import views
from .api.sse_views import conflict_discussion_stream
from .views.api_views import (
    ClaimNextResultAPIView,
    ConflictArbitrateAPIView,
    ConflictDetailAPIView,
    ConflictDiscussAPIView,
    ConflictListAPIView,
    ConflictResolveAPIView,
    GetSessionStatsAPIView,
    MakeDecisionAPIView,
    ReviewProgressAPIView,
    SkipResultAPIView,
    SubmitDecisionAPIView,
    TrackURLAccessAPIView,
    UpdateNotesAPIView,
)
from .views.duplicate_views import DuplicateGroupsView

app_name = "review_results"

urlpatterns = [
    # Main review interface
    path("overview/<uuid:session_id>/", views.results_review_view, name="overview"),
    # Filtered results (Issue #100)
    path(
        "filtered/<uuid:session_id>/",
        views.FilteredResultsView.as_view(),
        name="filtered_results",
    ),
    # Duplicate groups view
    path(
        "duplicates/<uuid:session_id>/",
        DuplicateGroupsView.as_view(),
        name="duplicate_groups",
    ),
    # Search statistics view
    path(
        "statistics/<uuid:session_id>/",
        views.SearchStatisticsView.as_view(),
        name="search_statistics",
    ),
    # Complete review
    path(
        "complete/<uuid:session_id>/",
        views.complete_review_view,
        name="complete_review",
    ),
    # Mark reviewer as complete (dual-screening workflow)
    path(
        "mark-complete/<uuid:session_id>/",
        views.mark_reviewer_complete,
        name="mark_reviewer_complete",
    ),
    # Hide/unhide iteration results
    path(
        "api/<uuid:session_id>/iterations/<int:execution_round>/hide/",
        views.hide_iteration_results,
        name="hide_iteration",
    ),
    path(
        "api/<uuid:session_id>/iterations/<int:execution_round>/unhide/",
        views.unhide_iteration_results,
        name="unhide_iteration",
    ),
    # Reset all reviews
    path(
        "reset/<uuid:session_id>/",
        views.BulkResetReviewsView.as_view(),
        name="reset_reviews",
    ),
    # AJAX API endpoints (legacy function-based views)
    path(
        "api/<uuid:session_id>/decision/", views.make_decision_api, name="make_decision"
    ),
    path(
        "api/<uuid:session_id>/bulk-decision/",
        views.bulk_decision_api,
        name="bulk_decision",
    ),
    path("api/<uuid:session_id>/notes/", views.notes_api, name="get_notes"),
    path("api/<uuid:session_id>/notes/save/", views.notes_api, name="save_notes"),
    path("api/<uuid:session_id>/progress/", views.progress_api, name="progress_api"),
    path(
        "api/<uuid:session_id>/track-url/",
        views.track_url_access,
        name="track_url_access",
    ),
    path(
        "api/<uuid:session_id>/include-filtered/",
        views.include_filtered_result_api,
        name="include_filtered",
    ),
    # TypedDict API endpoints (class-based views for type validation)
    path(
        "api/<uuid:session_id>/make-decision-api/",
        MakeDecisionAPIView.as_view(),
        name="make_decision_api",
    ),
    path(
        "api/<uuid:session_id>/session-stats-api/",
        GetSessionStatsAPIView.as_view(),
        name="session_stats_api",
    ),
    path(
        "api/<uuid:session_id>/update-notes-api/",
        UpdateNotesAPIView.as_view(),
        name="update_notes_api",
    ),
    path(
        "api/<uuid:session_id>/track-url-access-api/",
        TrackURLAccessAPIView.as_view(),
        name="track_url_access_api",
    ),
    # Dual Screening API Endpoints (Phase D - Multi-Reviewer Workflows)
    path(
        "api/screening/claim-next/",
        ClaimNextResultAPIView.as_view(),
        name="claim_next_result",
    ),
    path(
        "api/screening/submit-decision/",
        SubmitDecisionAPIView.as_view(),
        name="submit_decision",
    ),
    path(
        "api/screening/skip-result/",
        SkipResultAPIView.as_view(),
        name="skip_result",
    ),
    path(
        "api/screening/progress/<uuid:session_id>/",
        ReviewProgressAPIView.as_view(),
        name="review_progress",
    ),
    # Conflict Discussion API Endpoints (Phase 05)
    path(
        "api/conflicts/",
        ConflictListAPIView.as_view(),
        name="conflict_list",
    ),
    path(
        "api/conflicts/<uuid:conflict_id>/",
        ConflictDetailAPIView.as_view(),
        name="conflict_detail",
    ),
    path(
        "api/conflicts/<uuid:conflict_id>/discuss/",
        ConflictDiscussAPIView.as_view(),
        name="conflict_discuss",
    ),
    path(
        "api/conflicts/<uuid:conflict_id>/resolve/",
        ConflictResolveAPIView.as_view(),
        name="conflict_resolve",
    ),
    path(
        "api/conflicts/<uuid:conflict_id>/arbitrate/",
        ConflictArbitrateAPIView.as_view(),
        name="conflict_arbitrate",
    ),
    path(
        "api/conflicts/<uuid:conflict_id>/stream/",
        conflict_discussion_stream,
        name="conflict_discussion_stream",
    ),
]
