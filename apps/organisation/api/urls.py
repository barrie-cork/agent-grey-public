"""
URL Configuration for Organisation APIs.

All URLs are prefixed with /api/organisation/
"""

from django.urls import path
from apps.organisation.api import org_views

app_name = "organisation_api"

urlpatterns = [
    # =========================================================================
    # ORGANISATION APIS (4 endpoints)
    # =========================================================================
    # GET /api/organisation/{org_id}/dashboard/ - Organisation-wide metrics
    path("<uuid:org_id>/dashboard/", org_views.get_org_dashboard, name="org-dashboard"),
    # GET /api/organisation/{org_id}/reviews/ - Review list with filters
    path("<uuid:org_id>/reviews/", org_views.list_org_reviews, name="org-reviews"),
    # POST /api/organisation/{org_id}/users/invite/ - Invite user
    path("<uuid:org_id>/users/invite/", org_views.invite_user, name="org-invite-user"),
    # GET /api/organisation/{org_id}/reports/quality/ - Quality report (CSV/PDF/JSON)
    path(
        "<uuid:org_id>/reports/quality/",
        org_views.get_quality_report,
        name="org-quality-report",
    ),
]
