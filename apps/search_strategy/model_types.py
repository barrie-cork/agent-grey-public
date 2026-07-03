"""
TypedDict definitions for SearchStrategy model JSONFields.
Created during Phase 2 of TypedDict migration - Model Alignment.
"""

from typing import List, Literal, TypedDict


class PaginationConfigType(TypedDict, total=False):
    """Type definition for pagination settings within SearchConfigType.

    Configures how many pages to fetch from the Serper API to maximise result coverage.
    """

    enabled: bool  # Whether pagination is enabled (default: True)
    results_per_page: int  # Results per API call (default: 10, Serper standard)
    max_pages: int  # Maximum pages to fetch (default: 10, giving up to 100 results)
    delay_between_pages: float  # Delay in seconds between page requests (default: 0.5)


class SearchConfigType(TypedDict, total=False):
    """Type definition for SearchStrategy.search_config JSONField.

    Defines the structure for domain, file type, and search parameters.
    """

    domains: List[str]  # List of domains like ["nice.org.uk", "who.int"]
    include_general_search: bool  # Whether to include general Google search
    include_guidelines_filter: (
        bool  # Whether to add guideline-specific terms to all queries
    )
    file_types: List[str]  # File types like ["pdf", "doc", "docx"]
    search_types: List[Literal["google", "scholar"]]  # Search engine types
    max_results: int  # Maximum results per query (stored in search_config JSONField)
    pagination: PaginationConfigType  # Pagination configuration for result maximisation


class ValidationErrorsType(TypedDict, total=False):
    """Type definition for SearchStrategy.validation_errors JSONField.

    Maps validation error keys to error messages.
    Using total=False since errors are dynamic.
    """

    pic_terms: str  # Error about PIC terms
    domains: str  # Error about domain selection
    file_types: str  # Error about file types
    search_config: str  # General config error
