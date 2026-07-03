"""
Testing and diagnostic API endpoints.
Contains functions for API health checks, test session creation, and diagnostic utilities.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.core.services.serper_client import SerperAPIError

from ..api_types import TestSessionCreateResponse, TestSessionUpdateResponse
from ..services.api_service import DiagnosticAPIService

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def diagnostic_api_test(request) -> JsonResponse:
    """
    Diagnostic endpoint to test Serper API connectivity and response structure.

    Provides comprehensive testing of API functionality including
    search execution, response parsing, and result processing.
    Used for troubleshooting and monitoring API health.
    """
    service = DiagnosticAPIService()

    # Test query
    test_query = request.GET.get("q", "health technology assessment grey literature")
    try:
        num_results = int(request.GET.get("num", 10))
    except (ValueError, TypeError):
        num_results = 10

    try:
        response_analysis = service.run_diagnostic_test(
            test_query, num_results, request.user
        )
        return JsonResponse(response_analysis)
    except SerperAPIError as e:
        logger.error(f"Diagnostic API test failed with API error: {str(e)}")
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "api_status": "error",
            },
            status=500,
        )
    except Exception as e:
        logger.error(f"Diagnostic API test failed with unexpected error: {str(e)}")
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "api_status": "unknown",
            },
            status=500,
        )


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def create_test_session_api(request) -> JsonResponse:
    """
    Create a test session for E2E testing.
    Only available in development/testing environments.
    Requires authenticated staff user.
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Staff access required"}, status=403)
    import json

    from django.conf import settings

    from apps.review_manager.models import SearchSession
    from apps.search_strategy.models import SearchQuery

    # Only allow in development/testing
    if not settings.DEBUG:
        return JsonResponse({"error": "Not available in production"}, status=403)

    try:
        data = json.loads(request.body)
        title = data.get("title", "E2E Test Session")
        status = data.get("status", "draft")

        # Get or create test user (for E2E testing)
        from apps.accounts.models import User

        test_user, created = User.objects.get_or_create(
            username="cross_app_auth_test",
            defaults={
                "email": "cross_app_auth_test@example.com",
            },
        )
        if created:
            # Use test password from settings or environment
            from django.conf import settings

            test_password = getattr(settings, "TEST_USER_PASSWORD", "TestPass123!")
            test_user.set_password(test_password)
            test_user.save()

        # Create session
        session = SearchSession.objects.create(
            title=title, status=status, owner=test_user
        )

        # Create a test query if requested
        if data.get("create_query", False):
            # First create a strategy since SearchQuery needs one
            from apps.search_strategy.models import SearchStrategy

            strategy = SearchStrategy.objects.create(
                session=session,
                user=test_user,
                population_terms=["test population"],
                interest_terms=["test interest"],
                context_terms=["test context"],
                is_complete=True,
            )
            SearchQuery.objects.create(
                strategy=strategy,
                session=session,  # Denormalised field
                query_text="test query",
                query_type="general",
                target_domain=None,
                execution_order=1,
                is_active=True,
            )

        response_data: TestSessionCreateResponse = {
            "session_id": str(session.id),
            "title": session.title,
            "status": session.status,
            "created": True,
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error creating test session: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def update_test_session_api(request) -> JsonResponse:
    """
    Update a test session status for E2E testing.
    Only available in development/testing environments.
    Requires authenticated staff user.
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "Staff access required"}, status=403)
    import json

    from django.conf import settings

    from apps.review_manager.models import SearchSession

    # Only allow in development/testing
    if not settings.DEBUG:
        return JsonResponse({"error": "Not available in production"}, status=403)

    try:
        data = json.loads(request.body)
        session_id = data.get("session_id")
        new_status = data.get("status")

        if not session_id or not new_status:
            return JsonResponse({"error": "Missing session_id or status"}, status=400)

        # Get and update session (for testing, don't require owner match)
        session = SearchSession.objects.get(id=session_id)
        session.status = new_status
        session.save()

        # Simple status update without events
        logger.info(f"Test session {session_id} updated to status: {new_status}")

        response_data: TestSessionUpdateResponse = {
            "session_id": str(session.id),
            "status": session.status,
            "updated": True,
        }

        return JsonResponse(response_data)

    except SearchSession.DoesNotExist:
        return JsonResponse({"error": "Session not found"}, status=404)
    except Exception as e:
        logger.error(f"Error updating test session: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
