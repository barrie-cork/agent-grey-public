"""API views package for the review_results app.

This package splits the former single api_views module into cohesive
submodules. All public view classes are re-exported here so existing imports
from ``review_results.views.api_views`` keep working unchanged.
"""

from .conflict_api_views import (
    ConflictArbitrateAPIView,
    ConflictDetailAPIView,
    ConflictDiscussAPIView,
    ConflictListAPIView,
    ConflictResolveAPIView,
)
from .decision_views import (
    BulkDecisionAPIView,
    GetSessionStatsAPIView,
    IncludeFilteredResultAPIView,
    MakeDecisionAPIView,
    TrackURLAccessAPIView,
    UpdateNotesAPIView,
)
from .queue_views import (
    ClaimNextResultAPIView,
    ReviewProgressAPIView,
    SkipResultAPIView,
    SubmitDecisionAPIView,
)

__all__ = [
    # Decision and notes (single-reviewer + shared)
    "MakeDecisionAPIView",
    "BulkDecisionAPIView",
    "UpdateNotesAPIView",
    "GetSessionStatsAPIView",
    "TrackURLAccessAPIView",
    "IncludeFilteredResultAPIView",
    # Work-queue and dual-screening
    "ClaimNextResultAPIView",
    "SubmitDecisionAPIView",
    "SkipResultAPIView",
    "ReviewProgressAPIView",
    # Conflict resolution
    "ConflictListAPIView",
    "ConflictDetailAPIView",
    "ConflictDiscussAPIView",
    "ConflictResolveAPIView",
    "ConflictArbitrateAPIView",
]
