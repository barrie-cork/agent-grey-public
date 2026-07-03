"""
Views package for the review_results app.

This package provides a modular structure for organizing views while
maintaining backward compatibility with existing imports.
"""

# Import API views
from .api_views import (
    BulkDecisionAPIView,
    GetSessionStatsAPIView,
    IncludeFilteredResultAPIView,
    MakeDecisionAPIView,
    TrackURLAccessAPIView,
    UpdateNotesAPIView,
)

# Import function-based views
from .legacy_views import (
    bulk_decision_api,
    complete_review_view,
    hide_iteration_results,
    include_filtered_result_api,
    make_decision_api,
    mark_reviewer_complete,
    notes_api,
    progress_api,
    results_review_view,
    track_url_access,
    unhide_iteration_results,
)

# Import mixins
from .mixins import SessionOwnershipMixin

# Import template views
from .review_views import (
    BulkResetReviewsView,
    FilteredResultsView,
    ResultsReviewView,
    SearchStatisticsView,
)

# Export all for backward compatibility
__all__ = [
    # Mixins
    "SessionOwnershipMixin",
    # API Views
    "MakeDecisionAPIView",
    "BulkDecisionAPIView",
    "UpdateNotesAPIView",
    "GetSessionStatsAPIView",
    "TrackURLAccessAPIView",
    "IncludeFilteredResultAPIView",
    # Template views
    "ResultsReviewView",
    "FilteredResultsView",
    "BulkResetReviewsView",
    "SearchStatisticsView",
    # Function-based views
    "results_review_view",
    "make_decision_api",
    "bulk_decision_api",
    "notes_api",
    "progress_api",
    "track_url_access",
    "include_filtered_result_api",
    "complete_review_view",
    "mark_reviewer_complete",
    "hide_iteration_results",
    "unhide_iteration_results",
]
