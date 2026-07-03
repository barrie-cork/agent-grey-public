"""
Organisation API Views.

Provides 4 endpoints:
1. GET /api/organisation/{org_id}/dashboard/ - Organisation-wide metrics
2. GET /api/organisation/{org_id}/reviews/ - Review list with filters
3. POST /api/organisation/{org_id}/users/invite/ - Invite user
4. GET /api/organisation/{org_id}/reports/quality/ - Quality report (CSV/PDF/JSON)
"""

import csv

from django.core.paginator import Paginator
from django.db.models import Avg, F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.organisation.models import Organisation, OrganisationMembership
from apps.organisation.services.invitation_service import InvitationService
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ConflictResolution,
    InterRaterReliability,
    ReviewerDecision,
)
from apps.review_results.permissions import (
    IsInfoSpecialistOnly,
    IsInfoSpecialistOrSeniorResearcher,
)

# ============================================================================
# ORGANISATION DASHBOARD
# ============================================================================


@extend_schema(
    responses={200: OpenApiResponse(description="Organisation metrics")},
    summary="Get organisation dashboard",
    description="Get organisation-wide metrics including total reviews, conflicts, and IRR metrics.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsInfoSpecialistOrSeniorResearcher])
def get_org_dashboard(request, org_id):
    """Get organisation-wide dashboard metrics."""
    # Get organisation
    org = get_object_or_404(Organisation, id=org_id)

    # Verify user has membership
    membership = OrganisationMembership.objects.filter(
        user=request.user, organisation=org, is_active=True
    ).first()

    if not membership:
        return Response(
            {
                "error": "not_member",
                "message": "You are not a member of this organisation",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # Get review statistics
    total_reviews = SearchSession.objects.filter(organisation=org).count()
    active_reviews = SearchSession.objects.filter(
        organisation=org,
        status__in=[
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
        ],
    ).count()
    completed_reviews = SearchSession.objects.filter(
        organisation=org, status="completed"
    ).count()
    archived_reviews = SearchSession.objects.filter(
        organisation=org, status="archived"
    ).count()

    # Get result statistics
    total_results_reviewed = (
        ReviewerDecision.objects.filter(organisation=org)
        .exclude(decision="ABSTAIN")
        .count()
    )

    # Get conflict statistics
    pending_conflicts = ConflictResolution.objects.filter(
        organisation=org, status__in=["PENDING", "IN_DISCUSSION", "ESCALATED"]
    ).count()

    # Get IRR statistics
    irr_metrics = InterRaterReliability.objects.filter(
        organisation=org, cohens_kappa__isnull=False
    )
    avg_kappa = irr_metrics.aggregate(avg=Avg("cohens_kappa"))["avg"] or 0.0
    reviews_below_threshold = (
        irr_metrics.filter(cohens_kappa__lt=0.70)
        .values("search_session")
        .distinct()
        .count()
    )

    # Get recent activity
    recent_sessions = (
        SearchSession.objects.filter(organisation=org)
        .select_related("owner")
        .order_by("-updated_at")[:5]
    )

    recent_activity = []
    for session in recent_sessions:
        recent_activity.append(
            {
                "review_id": str(session.id),
                "review_title": session.title,
                "last_updated": session.updated_at.isoformat(),
                "status": session.status,
                "lead_reviewer": session.owner.username if session.owner else "Unknown",
            }
        )

    # Build response
    dashboard_data = {
        "organisation": {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
        },
        "metrics": {
            "total_reviews": total_reviews,
            "active_reviews": active_reviews,
            "completed_reviews": completed_reviews,
            "archived_reviews": archived_reviews,
            "total_results_reviewed": total_results_reviewed,
            "pending_conflicts": pending_conflicts,
            "avg_kappa_organisation": round(avg_kappa, 2),
            "reviews_below_threshold": reviews_below_threshold,
        },
        "recent_activity": recent_activity,
    }

    return Response(dashboard_data, status=status.HTTP_200_OK)


# ============================================================================
# ORGANISATION REVIEWS LIST
# ============================================================================


@extend_schema(
    parameters=[
        OpenApiParameter(
            "status", str, description="Filter by status (active, completed, archived)"
        ),
        OpenApiParameter(
            "date_range", str, description="Filter by last_updated (7d, 30d, 90d, all)"
        ),
        OpenApiParameter(
            "lead_reviewer", str, description="Filter by lead reviewer ID"
        ),
        OpenApiParameter("page", int, description="Page number (default: 1)"),
        OpenApiParameter(
            "per_page", int, description="Results per page (default: 20, max: 100)"
        ),
    ],
    responses={200: OpenApiResponse(description="Review list")},
    summary="List organisation reviews",
    description="Get paginated list of reviews in organisation with optional filters.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsInfoSpecialistOrSeniorResearcher])
def list_org_reviews(request, org_id):
    """List all reviews in organisation with filters."""
    # Get organisation
    org = get_object_or_404(Organisation, id=org_id)

    # Verify user has membership
    membership = OrganisationMembership.objects.filter(
        user=request.user, organisation=org, is_active=True
    ).first()

    if not membership:
        return Response(
            {
                "error": "not_member",
                "message": "You are not a member of this organisation",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # Build queryset
    queryset = SearchSession.objects.filter(organisation=org).select_related("owner")

    # Apply status filter
    status_filter = request.query_params.get("status")
    if status_filter == "active":
        queryset = queryset.filter(
            status__in=[
                "defining_search",
                "ready_to_execute",
                "executing",
                "processing_results",
                "ready_for_review",
                "under_review",
            ]
        )
    elif status_filter == "completed":
        queryset = queryset.filter(status="completed")
    elif status_filter == "archived":
        queryset = queryset.filter(status="archived")

    # Apply date range filter
    date_range = request.query_params.get("date_range", "all")
    if date_range == "7d":
        queryset = queryset.filter(
            updated_at__gte=timezone.now() - timezone.timedelta(days=7)
        )
    elif date_range == "30d":
        queryset = queryset.filter(
            updated_at__gte=timezone.now() - timezone.timedelta(days=30)
        )
    elif date_range == "90d":
        queryset = queryset.filter(
            updated_at__gte=timezone.now() - timezone.timedelta(days=90)
        )

    # Apply lead reviewer filter
    lead_reviewer_id = request.query_params.get("lead_reviewer")
    if lead_reviewer_id:
        queryset = queryset.filter(owner_id=lead_reviewer_id)

    # Lead reviewers can only see own reviews
    if membership.role == "LEAD_REVIEWER":
        queryset = queryset.filter(owner=request.user)

    # Order by last updated
    queryset = queryset.order_by("-updated_at")

    # Pagination
    try:
        page_num = int(request.query_params.get("page", 1))
    except (ValueError, TypeError):
        page_num = 1
    try:
        per_page = min(int(request.query_params.get("per_page", 20)), 100)
    except (ValueError, TypeError):
        per_page = 20

    paginator = Paginator(queryset, per_page)
    page = paginator.get_page(page_num)

    # Build results with additional metrics
    results = []
    for session in page.object_list:
        # Get review statistics
        from apps.results_manager.models import ProcessedResult

        total_results = ProcessedResult.objects.filter(session=session).count()
        reviewed_results = ProcessedResult.objects.filter(
            session=session, reviewers_completed__gte=F("min_reviewers_required")
        ).count()
        progress_percentage = (
            (reviewed_results / total_results * 100) if total_results > 0 else 0
        )

        # Get reviewer count
        reviewers_count = (
            ReviewerDecision.objects.filter(result__session=session)
            .values("reviewer")
            .distinct()
            .count()
        )

        # Get IRR metrics for this session
        irr_metrics = InterRaterReliability.objects.filter(
            search_session=session, cohens_kappa__isnull=False
        )
        avg_kappa = irr_metrics.aggregate(avg=Avg("cohens_kappa"))["avg"]

        # Get pending conflicts
        pending_conflicts = ConflictResolution.objects.filter(
            result__session=session,
            status__in=["PENDING", "IN_DISCUSSION", "ESCALATED"],
        ).count()

        results.append(
            {
                "id": str(session.id),
                "title": session.title,
                "lead_reviewer": {
                    "id": str(session.owner.id) if session.owner else None,
                    "username": session.owner.username if session.owner else "Unknown",
                },
                "status": session.status,
                "reviewers_count": reviewers_count,
                "results_total": total_results,
                "results_reviewed": reviewed_results,
                "progress_percentage": round(progress_percentage, 1),
                "avg_kappa": round(avg_kappa, 2) if avg_kappa is not None else None,
                "pending_conflicts": pending_conflicts,
                "created_at": session.created_at.isoformat(),
                "last_updated": session.updated_at.isoformat(),
            }
        )

    # Build response
    return Response(
        {
            "count": paginator.count,
            "page": page_num,
            "num_pages": paginator.num_pages,
            "next": page.has_next(),
            "previous": page.has_previous(),
            "results": results,
        },
        status=status.HTTP_200_OK,
    )


# ============================================================================
# INVITE USER TO ORGANISATION
# ============================================================================


@extend_schema(
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email"},
                "name": {"type": "string"},
                "role": {
                    "type": "string",
                    "enum": [
                        "INFORMATION_SPECIALIST",
                        "SENIOR_RESEARCHER",
                        "LEAD_REVIEWER",
                        "REVIEWER",
                        "OBSERVER",
                    ],
                },
            },
            "required": ["email", "role"],
        }
    },
    responses={
        200: OpenApiResponse(description="Invitation sent"),
        400: OpenApiResponse(description="Validation error"),
    },
    summary="Invite user to organisation",
    description="Send an invitation email to a user to join the organisation. Requires INFORMATION_SPECIALIST role.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsInfoSpecialistOnly])
def invite_user(request, org_id):
    """Invite a user to the organisation."""
    # Get organisation
    org = get_object_or_404(Organisation, id=org_id)

    # Validate input
    email = request.data.get("email")
    name = request.data.get("name", "")
    role = request.data.get("role")

    if not email or not role:
        return Response(
            {"error": "validation_error", "message": "Email and role are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate role
    valid_roles = [
        "INFORMATION_SPECIALIST",
        "SENIOR_RESEARCHER",
        "LEAD_REVIEWER",
        "REVIEWER",
        "OBSERVER",
    ]
    if role not in valid_roles:
        return Response(
            {
                "error": "invalid_role",
                "message": f"Role must be one of: {', '.join(valid_roles)}",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create invitation using service
    invitation_service = InvitationService()

    try:
        invitation = invitation_service.create_invitation(
            organisation=org,
            email=email,
            role=role,
            invited_by=request.user,
            name=name,
        )
    except ValueError as e:
        return Response(
            {"error": "invitation_error", "message": str(e)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Build magic link
    magic_link = (
        f"{request.build_absolute_uri('/organisation/invitation/')}{invitation.token}/"
    )

    return Response(
        {
            "success": True,
            "invitation_id": str(invitation.id),
            "invitation_sent": True,
            "invitation_sent_at": invitation.created_at.isoformat(),
            "invitation_expires_at": invitation.expires_at.isoformat(),
            "magic_link": magic_link,
        },
        status=status.HTTP_200_OK,
    )


# ============================================================================
# ORGANISATION QUALITY REPORT
# ============================================================================


@extend_schema(
    parameters=[
        OpenApiParameter(
            "format", str, description="Output format (json, csv, pdf)", required=False
        ),
        OpenApiParameter(
            "date_range",
            str,
            description="Date range (30d, 90d, 365d, all)",
            required=False,
        ),
    ],
    responses={200: OpenApiResponse(description="Quality report")},
    summary="Get organisation quality report",
    description="Generate a quality report for the organisation with IRR metrics and conflict summary. Supports JSON, CSV, and PDF formats.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated, IsInfoSpecialistOrSeniorResearcher])
def get_quality_report(request, org_id):
    """Generate organisation quality report."""
    # Get organisation
    org = get_object_or_404(Organisation, id=org_id)

    # Verify user has membership
    membership = OrganisationMembership.objects.filter(
        user=request.user, organisation=org, is_active=True
    ).first()

    if not membership:
        return Response(
            {
                "error": "not_member",
                "message": "You are not a member of this organisation",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # Get format and date range
    output_format = request.query_params.get("format", "json")
    date_range = request.query_params.get("date_range", "90d")

    # Calculate date filter
    if date_range == "30d":
        date_filter = timezone.now() - timezone.timedelta(days=30)
    elif date_range == "90d":
        date_filter = timezone.now() - timezone.timedelta(days=90)
    elif date_range == "365d":
        date_filter = timezone.now() - timezone.timedelta(days=365)
    else:
        date_filter = None

    # Get sessions
    sessions = SearchSession.objects.filter(organisation=org)
    if date_filter:
        sessions = sessions.filter(updated_at__gte=date_filter)

    # Calculate metrics
    total_reviews = sessions.count()
    total_reviewers = OrganisationMembership.objects.filter(
        organisation=org, is_active=True
    ).count()
    total_decisions = (
        ReviewerDecision.objects.filter(organisation=org)
        .exclude(decision="ABSTAIN")
        .count()
    )

    # IRR metrics
    irr_metrics = InterRaterReliability.objects.filter(
        organisation=org, cohens_kappa__isnull=False
    )
    if date_filter:
        irr_metrics = irr_metrics.filter(calculated_at__gte=date_filter)

    avg_irr = irr_metrics.aggregate(avg=Avg("cohens_kappa"))["avg"] or 0.0

    # Conflict rate
    total_conflicts = ConflictResolution.objects.filter(organisation=org).count()
    conflict_rate = (total_conflicts / total_decisions) if total_decisions > 0 else 0

    # Review details
    reviews_data = []
    for session in sessions:
        session_irr = InterRaterReliability.objects.filter(
            search_session=session, cohens_kappa__isnull=False
        ).aggregate(avg=Avg("cohens_kappa"))["avg"]

        session_conflicts = ConflictResolution.objects.filter(
            result__session=session
        ).count()

        reviews_data.append(
            {
                "review_title": session.title,
                "lead_reviewer": session.owner.username if session.owner else "Unknown",
                "irr_metrics": {
                    "avg_kappa": round(session_irr, 2)
                    if session_irr is not None
                    else None,
                },
                "conflict_summary": {
                    "total_conflicts": session_conflicts,
                },
            }
        )

    # Build report data
    report_data = {
        "organisation": {
            "id": str(org.id),
            "name": org.name,
        },
        "period": {
            "start": date_filter.isoformat() if date_filter else "All time",
            "end": timezone.now().isoformat(),
        },
        "summary": {
            "total_reviews": total_reviews,
            "total_reviewers": total_reviewers,
            "total_decisions": total_decisions,
            "avg_irr": round(avg_irr, 2),
            "conflict_rate": round(conflict_rate, 2),
        },
        "reviews": reviews_data,
    }

    # Return based on format
    if output_format == "csv":
        # Generate CSV
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="quality_report_{org.slug}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(
            [
                "Organisation",
                "Period",
                "Total Reviews",
                "Total Reviewers",
                "Total Decisions",
                "Avg IRR",
                "Conflict Rate",
            ]
        )
        writer.writerow(
            [
                org.name,
                f"{report_data['period']['start']} to {report_data['period']['end']}",
                total_reviews,
                total_reviewers,
                total_decisions,
                round(avg_irr, 2),
                round(conflict_rate, 2),
            ]
        )

        writer.writerow([])  # Empty row
        writer.writerow(
            ["Review Title", "Lead Reviewer", "Avg Kappa", "Total Conflicts"]
        )

        for review in reviews_data:
            writer.writerow(
                [
                    review["review_title"],
                    review["lead_reviewer"],
                    review["irr_metrics"]["avg_kappa"] or "N/A",
                    review["conflict_summary"]["total_conflicts"],
                ]
            )

        return response

    elif output_format == "pdf":
        # PDF generation would require WeasyPrint integration
        # For now, return JSON with message
        return Response(
            {"error": "not_implemented", "message": "PDF format not yet implemented"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    else:
        # Return JSON
        return Response(report_data, status=status.HTTP_200_OK)
