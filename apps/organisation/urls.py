"""URL configuration for organisation app."""

from django.urls import path

from . import views

app_name = "organisation"

urlpatterns = [
    # Create new organisation
    path("create/", views.CreateOrganisationView.as_view(), name="create"),
    # Organisation dashboard
    path(
        "<uuid:org_id>/dashboard/",
        views.OrganisationDashboardView.as_view(),
        name="dashboard",
    ),
    # User invitation
    path("<uuid:org_id>/invite/", views.InviteUserView.as_view(), name="invite"),
    # Invitation acceptance (magic link)
    path(
        "invitation/<str:token>/",
        views.AcceptInvitationView.as_view(),
        name="invitation_accept",
    ),
    # API endpoints
    path(
        "<uuid:org_id>/api/metrics/",
        views.OrganisationMetricsAPIView.as_view(),
        name="api_metrics",
    ),
]
