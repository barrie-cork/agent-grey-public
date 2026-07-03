"""
Core validation utilities for Pydantic schema integration.
Provides request validation and response formatting for Django views.
"""

from django.http import JsonResponse
from pydantic import ValidationError


def validate_request(schema_class, data):
    """
    Validate request data using Pydantic schema.

    Args:
        schema_class: Pydantic BaseModel class to use for validation
        data: Dictionary of data to validate

    Returns:
        Validated Pydantic model instance

    Raises:
        ValueError: If validation fails with detailed error messages
    """
    try:
        return schema_class(**data)
    except ValidationError as e:
        errors = []
        for error in e.errors():
            field = ".".join(str(x) for x in error["loc"])
            errors.append(f"{field}: {error['msg']}")
        raise ValueError("; ".join(errors))


def schema_response(schema_instance, status=200):
    """
    Convert Pydantic schema to JSON response.

    Args:
        schema_instance: Pydantic model instance
        status: HTTP status code (default 200)

    Returns:
        JsonResponse with serialized schema data
    """
    return JsonResponse(schema_instance.model_dump(), status=status)


def validate_and_clean(schema_class, data, exclude_unset=True):
    """
    Validate and clean request data, removing unset fields.

    Args:
        schema_class: Pydantic BaseModel class
        data: Dictionary of data to validate
        exclude_unset: Whether to exclude unset fields (default True)

    Returns:
        Dictionary of cleaned data
    """
    try:
        instance = schema_class(**data)
        if exclude_unset:
            return instance.model_dump(exclude_unset=True)
        return instance.model_dump()
    except ValidationError as e:
        errors = format_validation_errors(e)
        raise ValueError(errors)


def format_validation_errors(validation_error):
    """
    Format Pydantic validation errors for user-friendly display.

    Args:
        validation_error: Pydantic ValidationError instance

    Returns:
        String with formatted error messages
    """
    errors = []
    for error in validation_error.errors():
        field = ".".join(str(x) for x in error["loc"])
        msg = error["msg"]
        errors.append(f"{field}: {msg}")
    return "; ".join(errors)


def paginated_response(queryset, schema_class, request, page_size=25):
    """
    Create a paginated response using Pydantic schemas.

    Args:
        queryset: Django QuerySet to paginate
        schema_class: Pydantic schema class for items
        request: Django request object
        page_size: Items per page (default 25)

    Returns:
        Dictionary with paginated results
    """
    from django.core.paginator import Paginator

    page_num = request.GET.get("page", 1)
    paginator = Paginator(queryset, page_size)
    page = paginator.get_page(page_num)

    # Serialize items using schema
    items = []
    for obj in page:
        try:
            schema = schema_class.model_validate(obj)
            items.append(schema.model_dump())
        except Exception:
            # Skip items that fail validation
            continue

    # Build pagination URLs
    base_url = request.build_absolute_uri(request.path)
    next_url = None
    previous_url = None

    if page.has_next():
        next_url = f"{base_url}?page={page.next_page_number()}"
    if page.has_previous():
        previous_url = f"{base_url}?page={page.previous_page_number()}"

    return {
        "count": paginator.count,
        "next": next_url,
        "previous": previous_url,
        "results": items,
    }


def api_error_response(error_message, status=400, errors=None):
    """
    Create a standardized API error response.

    Args:
        error_message: Main error message
        status: HTTP status code (default 400)
        errors: Dictionary of field-specific errors (optional)

    Returns:
        JsonResponse with error details
    """
    response_data = {"success": False, "error": error_message}

    if errors:
        response_data["errors"] = errors

    return JsonResponse(response_data, status=status)


def api_success_response(data=None, message=None, status=200):
    """
    Create a standardized API success response.

    Args:
        data: Response data (optional)
        message: Success message (optional)
        status: HTTP status code (default 200)

    Returns:
        JsonResponse with success details
    """
    response_data = {"success": True}

    if message:
        response_data["message"] = message

    if data is not None:
        response_data["data"] = data

    return JsonResponse(response_data, status=status)
