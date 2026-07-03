"""
Execution control and status API endpoints.
Contains functions for execution monitoring, retry operations, and raw results data.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods

from ..api_types import ErrorResponse, RawResultsCountResponse
from ..services.api_service import ExecutionAPIService, RecoveryAPIService

logger = logging.getLogger(__name__)


def get_raw_results_count(
    session_id: str | None = None, execution_id: str | None = None
) -> RawResultsCountResponse:
    """
    Get count of raw search results for a session or execution.

    Args:
        session_id: Session UUID string (optional)
        execution_id: Execution UUID string (optional)

    Returns:
        RawResultsCountResponse: Raw results count response
    """
    from ..models import RawSearchResult

    # Basic validation
    if not session_id and not execution_id:
        raise ValueError("Either session_id or execution_id must be provided")

    # Query raw results
    if session_id:
        count = RawSearchResult.objects.filter(
            execution__query__session_id=session_id
        ).count()
    elif execution_id:
        count = RawSearchResult.objects.filter(execution_id=execution_id).count()
    else:
        count = 0

    # Build response
    response_data: RawResultsCountResponse = {
        "count": count,
        "session_id": session_id,
        "execution_id": execution_id,
    }

    return response_data


@login_required
@require_http_methods(["GET"])
def execution_status_api(request, execution_id) -> JsonResponse:
    """
    Get individual execution status via AJAX for real-time monitoring.

    Provides detailed execution information including status, progress,
    results count, and error details. Used by frontend JavaScript
    for live status updates during search execution.

    Args:
        request: The HTTP request object
        execution_id: UUID string identifying the search execution

    Returns:
        JsonResponse: Execution status data or error information
    """
    format_param = request.GET.get("format", "json")

    if format_param not in ["json"]:
        error_response: ErrorResponse = {
            "error": "Invalid format parameter",
            "error_type": "ValidationError",
            "details": {"format": format_param},
            "status_code": 400,
        }
        return JsonResponse(error_response, status=400)

    service = ExecutionAPIService()

    try:
        response_data = service.get_execution_status(execution_id, request.user)
        return JsonResponse(response_data)
    except Http404:
        error_response = {
            "error": "Execution not found",
            "error_type": "NotFound",
            "details": None,
            "status_code": 404,
        }
        return JsonResponse(error_response, status=404)
    except PermissionError:
        error_response = {
            "error": "Permission denied",
            "error_type": "PermissionDenied",
            "details": None,
            "status_code": 403,
        }
        return JsonResponse(error_response, status=403)
    except Exception as e:
        logger.error(f"Error getting execution status: {str(e)}")
        error_response = {
            "error": "Internal server error",
            "error_type": "InternalError",
            "details": {"message": str(e)},
            "status_code": 500,
        }
        return JsonResponse(error_response, status=500)


@login_required
@require_http_methods(["POST"])
def retry_execution_api(request, execution_id) -> JsonResponse:
    """
    Retry a failed execution via AJAX.

    Initiates a retry for failed executions, providing immediate feedback
    for user-initiated recovery actions. Validates execution state and
    ownership before proceeding with retry operation.
    """
    service = RecoveryAPIService()

    try:
        response_data = service.retry_failed_execution(execution_id, request.user)
        return JsonResponse(response_data)
    except Http404:
        error_response: ErrorResponse = {
            "error": "Execution not found",
            "error_type": "NotFound",
            "details": None,
            "status_code": 404,
        }
        return JsonResponse(error_response, status=404)
    except PermissionError:
        error_response = {
            "error": "Permission denied",
            "error_type": "PermissionDenied",
            "details": None,
            "status_code": 403,
        }
        return JsonResponse(error_response, status=403)
    except ValueError as e:
        error_response = {
            "error": str(e),
            "error_type": "ValidationError",
            "details": None,
            "status_code": 400,
        }
        return JsonResponse(error_response, status=400)
    except Exception as e:
        logger.error(f"Error retrying execution: {str(e)}")
        error_response = {
            "error": "Failed to retry execution",
            "error_type": "InternalError",
            "details": {"message": str(e)},
            "status_code": 500,
        }
        return JsonResponse(error_response, status=500)
