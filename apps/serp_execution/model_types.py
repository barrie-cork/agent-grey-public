"""
TypedDict definitions for SERP Execution model JSONFields.
Created during Phase 2 of TypedDict migration - Model Alignment.
"""

from typing import Any, Dict, List, Optional, TypedDict


class APIParametersType(TypedDict):
    """Type definition for SearchExecution.api_parameters JSONField.

    Parameters sent to the Serper API for search execution.
    """

    q: str  # Query string
    gl: str  # Geographic location (e.g., "us", "uk")
    hl: str  # Language (e.g., "en", "es")
    num: int  # Number of results to fetch
    start: int  # Starting offset for pagination
    type: str  # Search type (e.g., "search", "news", "scholar")
    domain: Optional[str]  # Optional domain restriction
    filetype: Optional[str]  # Optional file type filter


class StepMetadataType(TypedDict):
    """Type definition for SearchExecution.step_metadata JSONField.

    Detailed tracking data for execution steps.
    """

    current_page: int  # Current pagination page
    total_pages: int  # Total pages to fetch
    results_fetched: int  # Results fetched so far
    api_calls_made: int  # Number of API calls
    rate_limit_remaining: Optional[int]  # Rate limit info
    last_error: Optional[str]  # Last error encountered
    retry_attempts: int  # Number of retries


class RawDataType(TypedDict):
    """Type definition for RawSearchResult.raw_data JSONField.

    Complete raw response from Serper API.
    """

    title: str
    link: str
    snippet: str
    position: int
    displayLink: Optional[str]
    date: Optional[str]  # Publication date if detected
    sitelinks: Optional[List[Dict[str, str]]]  # Additional links
    thumbnails: Optional[List[Dict[str, Any]]]  # Image thumbnails
    rich_snippet: Optional[Dict[str, Any]]  # Rich snippet data
    mime: Optional[str]  # MIME type for documents
    fileFormat: Optional[str]  # File format indicator
