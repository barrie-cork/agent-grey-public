"""
Utility functions for the serp_execution app.

This module contains validation and helper functions.
Business logic has been moved to dedicated services.
"""

import re
from typing import Any, Dict, Optional

from .models import SearchExecution

# Removed complex services - using simplified approach
from .services.execution_service import ExecutionService

# Initialize simplified services
execution_service = ExecutionService()

# Simplified utility functions


def get_execution_statistics(session_id: str):
    """Get execution statistics."""
    return execution_service.get_execution_statistics(session_id)


def validate_search_execution(execution: SearchExecution):
    """
    Validate search execution parameters and state.

    Args:
        execution: SearchExecution instance

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check if execution can be started
    if execution.status not in ["pending", "failed"]:
        errors.append(f"Cannot start execution with status '{execution.status}'")

    # Check query validity
    if not execution.query.is_active:
        errors.append("Cannot execute inactive query")

    # Check API parameters
    if not execution.api_parameters:
        errors.append("API parameters are required")

    # Check search engine
    valid_engines = ["google", "bing", "duckduckgo", "yahoo"]
    if execution.search_engine not in valid_engines:
        errors.append(f"Invalid search engine: {execution.search_engine}")

    # Check retry limits
    if execution.retry_count >= 3:
        errors.append("Maximum retry attempts reached")

    return len(errors) == 0, errors


def parse_query_details(
    query_text: str, api_params: Optional[Dict] = None
) -> Dict[str, str]:
    """
    Parse query details to extract domain, search terms, and file type.

    Args:
        query_text: The raw query text
        api_params: Optional API parameters that might contain additional info

    Returns:
        Dictionary with keys: domain, terms, file_type, full_text

    Example:
        Input: "site:www.cnn.com (Sea) AND (Sand) AND (Sun) type:pdf"
        Output: {
            'domain': 'www.cnn.com',
            'terms': '(Sea) AND (Sand) AND (Sun)',
            'file_type': 'pdf',
            'full_text': 'www.cnn.com (Sea) AND (Sand) AND (Sun) type:pdf'
        }
    """
    details = {"domain": "", "terms": "", "file_type": "", "full_text": ""}

    if not query_text:
        return details

    # Extract domain using site: operator
    domain_match = re.search(r"site:([^\s]+)", query_text)
    if domain_match:
        details["domain"] = domain_match.group(1)
        # Remove site: from terms
        query_text = re.sub(r"site:[^\s]+\s*", "", query_text)

    # Extract file type using type: or filetype: operator
    type_match = re.search(r"(?:type|filetype):([^\s]+)", query_text)
    if type_match:
        details["file_type"] = type_match.group(1)
        # Remove type: from terms
        query_text = re.sub(r"(?:type|filetype):[^\s]+\s*", "", query_text)

    # The remaining text is the search terms
    details["terms"] = query_text.strip()

    # Check API params for additional information
    if api_params:
        if "siteSearch" in api_params and not details["domain"]:
            details["domain"] = api_params["siteSearch"]
        if "fileType" in api_params and not details["file_type"]:
            details["file_type"] = api_params["fileType"]

    # Build full_text for display
    parts = []
    if details["domain"]:
        parts.append(details["domain"])
    if details["terms"]:
        parts.append(details["terms"])
    if details["file_type"]:
        parts.append(f"type:{details['file_type']}")

    details["full_text"] = " ".join(parts)

    return details


def build_execution_progress_message(
    query_details: Dict[str, str], action: str = "Executing"
) -> str:
    """
    Build a detailed progress message for query execution.

    Args:
        query_details: Dictionary from parse_query_details
        action: The action being performed (e.g., "Executing", "Completed", "Failed")

    Returns:
        Formatted progress message

    Example:
        Input: {'domain': 'www.cnn.com', 'terms': '(Sea) AND (Sand)', 'file_type': 'pdf'}
        Output: "Executing www.cnn.com (Sea) AND (Sand) type:pdf"
    """
    if not query_details:
        return f"{action} query"

    # Use the pre-built full_text if available
    if query_details.get("full_text"):
        return f"{action} {query_details['full_text']}"

    # Build from parts if full_text not available
    parts = []
    if query_details.get("domain"):
        parts.append(query_details["domain"])
    if query_details.get("terms"):
        parts.append(query_details["terms"])
    if query_details.get("file_type"):
        parts.append(f"type:{query_details['file_type']}")

    if parts:
        return f"{action} {' '.join(parts)}"

    return f"{action} query"


def extract_result_count(api_response: Dict) -> int:
    """
    Extract the result count from a Serper API response.

    Args:
        api_response: The raw API response from Serper

    Returns:
        Number of results found

    Example:
        Input: {'organic': [result1, result2, ...], 'searchParameters': {...}}
        Output: 23
    """
    if not api_response:
        return 0

    # Primary: Count organic results
    if "organic" in api_response and isinstance(api_response["organic"], list):
        return len(api_response["organic"])

    # Fallback: Check for total results in search information
    if "searchInformation" in api_response:
        search_info = api_response["searchInformation"]
        if "totalResults" in search_info:
            try:
                return int(search_info["totalResults"])
            except (ValueError, TypeError):
                pass

    # Fallback: Check for news results
    if "news" in api_response and isinstance(api_response["news"], list):
        return len(api_response["news"])

    # Fallback: Check for places results
    if "places" in api_response and isinstance(api_response["places"], list):
        return len(api_response["places"])

    return 0


def format_result_count_message(count: int, source: str = "Serper.dev") -> str:
    """
    Format a result count message for display.

    Args:
        count: Number of results
        source: The source of the results

    Returns:
        Formatted message

    Example:
        Input: 23
        Output: "23 results retrieved from Serper.dev"
    """
    if count == 0:
        return f"No results found from {source}"
    elif count == 1:
        return f"1 result retrieved from {source}"
    else:
        return f"{count} results retrieved from {source}"


def safe_get_query_text(query: Any) -> str:
    """
    Safely extract query text from various query objects.

    Args:
        query: Query object or dictionary

    Returns:
        Query text or empty string if not found
    """
    if not query:
        return ""

    # Try different attributes
    if hasattr(query, "query_text"):
        return str(query.query_text or "")
    if isinstance(query, dict):
        return str(query.get("query_text", query.get("text", "")))

    # Last resort - convert to string
    try:
        return str(query)
    except Exception:
        return ""
