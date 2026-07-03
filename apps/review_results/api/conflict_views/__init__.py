"""Conflict resolution API views package for the review_results app.

This package splits the former single conflict_views module into cohesive
submodules. All public views (and the two function-based endpoints) are
re-exported here so existing ``conflict_views.X`` references in api/urls.py
keep working unchanged.
"""

from .discussion_vote_views import (
    ProposeDiscussionVoteView,
    RespondToDiscussionVoteView,
)
from .resolution_views import (
    ConflictDetailView,
    ConflictListView,
    EscalateConflictView,
    ResolveConflictView,
    add_conflict_discussion,
    get_conflict_detail,
)
from .revote_views import (
    AcceptRevoteView,
    ConflictCommentCreateView,
    ProposeRevoteView,
    SubmitRevoteDecisionView,
)

__all__ = [
    # Listing, detail, resolution, escalation, discussion
    "ConflictListView",
    "get_conflict_detail",
    "ResolveConflictView",
    "EscalateConflictView",
    "add_conflict_discussion",
    "ConflictDetailView",
    # Comments and revote flow
    "ConflictCommentCreateView",
    "ProposeRevoteView",
    "AcceptRevoteView",
    "SubmitRevoteDecisionView",
    # In-discussion straw polls
    "ProposeDiscussionVoteView",
    "RespondToDiscussionVoteView",
]
