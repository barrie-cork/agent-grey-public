from django.urls import path

from . import api_views, views
from .views.sse import session_status_stream

# Reviewer invitation views (required dependency)
from .views_invitations import (
    AcceptInvitationView,
    DeclineInvitationView,
    PendingInvitationsView,
)

# External reviewer approval views (Phase E)
from .views_approvals import (
    PendingExternalReviewerApprovalsView,
    ApproveExternalReviewersView,
    RejectExternalReviewersView,
    ExternalReviewerDetailsView,
)

app_name = "review_manager"

urlpatterns = [
    # Dashboard
    path("", views.DashboardView.as_view(), name="dashboard"),
    # Session CRUD
    path("sessions/create/", views.SessionCreateView.as_view(), name="create_session"),
    path(
        "sessions/<uuid:session_id>/",
        views.SessionDetailView.as_view(),
        name="session_detail",
    ),
    path(
        "sessions/<uuid:session_id>/edit/",
        views.SessionUpdateView.as_view(),
        name="edit_session",
    ),
    # Session Actions
    path(
        "sessions/<uuid:session_id>/navigate/",
        views.SessionNavigateView.as_view(),
        name="session_navigate",
    ),
    path(
        "sessions/<uuid:session_id>/delete/",
        views.SessionDeleteView.as_view(),
        name="delete_session",
    ),
    path(
        "sessions/<uuid:session_id>/archive/",
        views.SessionArchiveView.as_view(),
        name="archive_session",
    ),
    # SSE endpoint for real-time session updates
    path(
        "sessions/<uuid:session_id>/stream/",
        session_status_stream,
        name="session_status_stream",
    ),
    # API endpoints for workflow automation
    path(
        "api/session/<uuid:session_id>/status/",
        api_views.session_status_api,
        name="session_status_api",
    ),
    # Temporary redirect for incorrect plural URLs (debugging)
    path(
        "api/sessions/<uuid:session_id>/status/",
        api_views.redirect_plural_session_status,
        name="redirect_plural_session_status",
    ),
    path(
        "api/session/<uuid:session_id>/quick-stats/",
        api_views.session_quick_stats_api,
        name="session_quick_stats_api",
    ),
    # Invitation management
    path(
        "invitations/",
        PendingInvitationsView.as_view(),
        name="pending_invitations",
    ),
    path(
        "invitations/accept/<str:token>/",
        AcceptInvitationView.as_view(),
        name="accept_invitation",
    ),
    path(
        "invitations/decline/<str:token>/",
        DeclineInvitationView.as_view(),
        name="decline_invitation",
    ),
    # External reviewer approval workflow (Phase E - IS Approval)
    path(
        "approvals/pending/",
        PendingExternalReviewerApprovalsView.as_view(),
        name="pending_approvals",
    ),
    path(
        "approvals/approve/<uuid:session_id>/",
        ApproveExternalReviewersView.as_view(),
        name="approve_external_reviewers",
    ),
    path(
        "approvals/reject/<uuid:session_id>/",
        RejectExternalReviewersView.as_view(),
        name="reject_external_reviewers",
    ),
    path(
        "approvals/details/<uuid:session_id>/",
        ExternalReviewerDetailsView.as_view(),
        name="external_reviewer_details",
    ),
]
