"""
Standardized error response utilities.

This module provides consistent error response generation throughout the application,
implementing the error response standards defined in the PRP refactoring plan.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.http import JsonResponse
from django.utils import timezone

from apps.core.types.api_responses import StandardErrorResponse, ValidationErrorDetail

logger = logging.getLogger(__name__)


class ErrorResponseBuilder:
    """Builder class for creating standardized error responses."""

    # HTTP status codes and their default messages
    HTTP_STATUS_MESSAGES = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }

    # Error type mapping based on status codes
    ERROR_TYPE_MAPPING = {
        400: "ValidationError",
        401: "AuthenticationError",
        403: "PermissionError",
        404: "NotFoundError",
        405: "MethodNotAllowedError",
        409: "ConflictError",
        422: "ValidationError",
        429: "RateLimitError",
        500: "InternalServerError",
        502: "ServiceError",
        503: "ServiceUnavailableError",
        504: "TimeoutError",
    }

    def __init__(self):
        """Initialize the error response builder."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def create_error_response(
        self,
        exception: Exception,
        status_code: int,
        request_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[StandardErrorResponse, int]:
        """
        Create a standardized error response from an exception.

        Args:
            exception: The exception that occurred
            status_code: HTTP status code
            request_id: Optional request ID for tracking
            context: Optional additional context

        Returns:
            Tuple of (error_response_dict, status_code)
        """
        error_type = self.ERROR_TYPE_MAPPING.get(status_code, "Error")
        error_message = self.HTTP_STATUS_MESSAGES.get(status_code, "Error")

        response: StandardErrorResponse = {
            "error": error_message,
            "error_type": error_type,
            "message": str(exception),
            "details": self._extract_error_details(exception, context),
            "timestamp": timezone.now().isoformat(),
            "request_id": request_id,
            "field_errors": None,
        }

        # Log the error for monitoring
        self._log_error(exception, status_code, request_id, context)

        return response, status_code

    def create_validation_error_response(
        self,
        field_errors: Dict[str, List[str]],
        message: str = "Validation failed",
        request_id: Optional[str] = None,
    ) -> Tuple[StandardErrorResponse, int]:
        """
        Create a validation error response with field-specific errors.

        Args:
            field_errors: Dictionary of field names to error messages
            message: Overall error message
            request_id: Optional request ID

        Returns:
            Tuple of (error_response_dict, 422)
        """
        validation_errors = []
        for field, messages in field_errors.items():
            for msg in messages:
                validation_errors.append(
                    ValidationErrorDetail(
                        field=field,
                        message=msg,
                        code="validation_error",
                        value=None,  # Don't expose actual values for security
                    )
                )

        response: StandardErrorResponse = {
            "error": "Validation Failed",
            "error_type": "ValidationError",
            "message": message,
            "details": {
                "field_count": len(field_errors),
                "error_count": len(validation_errors),
            },
            "timestamp": timezone.now().isoformat(),
            "request_id": request_id,
            "field_errors": validation_errors,
        }

        return response, 422

    def create_not_found_response(
        self, resource: str, identifier: str, request_id: Optional[str] = None
    ) -> Tuple[StandardErrorResponse, int]:
        """
        Create a standardized not found error response.

        Args:
            resource: Type of resource (e.g., 'session', 'user')
            identifier: Resource identifier that wasn't found
            request_id: Optional request ID

        Returns:
            Tuple of (error_response_dict, 404)
        """
        response: StandardErrorResponse = {
            "error": "Not Found",
            "error_type": "NotFoundError",
            "message": f"{resource.title()} with identifier '{identifier}' not found",
            "details": {"resource_type": resource, "identifier": identifier},
            "timestamp": timezone.now().isoformat(),
            "request_id": request_id,
            "field_errors": None,
        }

        return response, 404

    def create_permission_denied_response(
        self,
        action: str,
        resource: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Tuple[StandardErrorResponse, int]:
        """
        Create a permission denied error response.

        Args:
            action: Action that was denied (e.g., 'delete', 'view')
            resource: Optional resource type
            request_id: Optional request ID

        Returns:
            Tuple of (error_response_dict, 403)
        """
        if resource:
            message = f"Permission denied to {action} {resource}"
        else:
            message = f"Permission denied to {action}"

        response: StandardErrorResponse = {
            "error": "Forbidden",
            "error_type": "PermissionError",
            "message": message,
            "details": {"action": action, "resource": resource},
            "timestamp": timezone.now().isoformat(),
            "request_id": request_id,
            "field_errors": None,
        }

        return response, 403

    def create_rate_limit_response(
        self,
        limit: int,
        reset_time: Optional[datetime] = None,
        request_id: Optional[str] = None,
    ) -> Tuple[StandardErrorResponse, int]:
        """
        Create a rate limit exceeded error response.

        Args:
            limit: Rate limit that was exceeded
            reset_time: When the rate limit resets
            request_id: Optional request ID

        Returns:
            Tuple of (error_response_dict, 429)
        """
        details: dict[str, int | str] = {"rate_limit": limit}
        if reset_time:
            details["reset_at"] = reset_time.isoformat()

        response: StandardErrorResponse = {
            "error": "Too Many Requests",
            "error_type": "RateLimitError",
            "message": f"Rate limit of {limit} requests exceeded",
            "details": details,
            "timestamp": timezone.now().isoformat(),
            "request_id": request_id,
            "field_errors": None,
        }

        return response, 429

    def _extract_error_details(
        self, exception: Exception, context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Extract additional details from exception and context."""
        details = {}

        # Add exception class name
        details["exception_type"] = exception.__class__.__name__

        # Add context if provided
        if context:
            details.update(context)

        # Add specific exception attributes if available
        if hasattr(exception, "details"):
            details["exception_details"] = exception.details  # type: ignore[attr-defined]

        if hasattr(exception, "code"):
            details["error_code"] = exception.code  # type: ignore[attr-defined]

        return details if details else None

    def _log_error(
        self,
        exception: Exception,
        status_code: int,
        request_id: Optional[str],
        context: Optional[Dict[str, Any]],
    ) -> None:
        """Log error for monitoring and debugging."""
        log_data = {
            "exception": str(exception),
            "exception_type": exception.__class__.__name__,
            "status_code": status_code,
            "request_id": request_id,
        }

        if context:
            log_data["context"] = context

        if status_code >= 500:
            self.logger.error(f"Server error occurred: {exception}", extra=log_data)
        elif status_code >= 400:
            self.logger.warning(f"Client error occurred: {exception}", extra=log_data)


# Convenience functions for common error responses
_error_builder = ErrorResponseBuilder()


def error_response(
    exception: Exception,
    status_code: int = 500,
    request_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> JsonResponse:
    """
    Create a standardized error JsonResponse.

    Args:
        exception: The exception that occurred
        status_code: HTTP status code
        request_id: Optional request ID
        context: Optional additional context

    Returns:
        JsonResponse with standardized error structure
    """
    response_data, status = _error_builder.create_error_response(
        exception, status_code, request_id, context
    )
    return JsonResponse(response_data, status=status)


def validation_error_response(
    field_errors: Dict[str, List[str]],
    message: str = "Validation failed",
    request_id: Optional[str] = None,
) -> JsonResponse:
    """
    Create a validation error JsonResponse.

    Args:
        field_errors: Dictionary of field errors
        message: Overall error message
        request_id: Optional request ID

    Returns:
        JsonResponse with validation error structure
    """
    response_data, status = _error_builder.create_validation_error_response(
        field_errors, message, request_id
    )
    return JsonResponse(response_data, status=status)


def not_found_response(
    resource: str, identifier: str, request_id: Optional[str] = None
) -> JsonResponse:
    """
    Create a not found error JsonResponse.

    Args:
        resource: Type of resource
        identifier: Resource identifier
        request_id: Optional request ID

    Returns:
        JsonResponse with not found error structure
    """
    response_data, status = _error_builder.create_not_found_response(
        resource, identifier, request_id
    )
    return JsonResponse(response_data, status=status)


def permission_denied_response(
    action: str, resource: Optional[str] = None, request_id: Optional[str] = None
) -> JsonResponse:
    """
    Create a permission denied JsonResponse.

    Args:
        action: Action that was denied
        resource: Optional resource type
        request_id: Optional request ID

    Returns:
        JsonResponse with permission denied error structure
    """
    response_data, status = _error_builder.create_permission_denied_response(
        action, resource, request_id
    )
    return JsonResponse(response_data, status=status)


def rate_limit_response(
    limit: int, reset_time: Optional[datetime] = None, request_id: Optional[str] = None
) -> JsonResponse:
    """
    Create a rate limit error JsonResponse.

    Args:
        limit: Rate limit that was exceeded
        reset_time: When the rate limit resets
        request_id: Optional request ID

    Returns:
        JsonResponse with rate limit error structure
    """
    response_data, status = _error_builder.create_rate_limit_response(
        limit, reset_time, request_id
    )
    return JsonResponse(response_data, status=status)


def server_error_response(
    message: str = "Internal server error occurred", request_id: Optional[str] = None
) -> JsonResponse:
    """
    Create a generic server error JsonResponse.

    Args:
        message: Error message
        request_id: Optional request ID

    Returns:
        JsonResponse with server error structure
    """
    exception = Exception(message)
    return error_response(exception, 500, request_id)
