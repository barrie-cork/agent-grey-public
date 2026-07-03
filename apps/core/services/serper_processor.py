"""
Response processing and data extraction for Serper API.
Handles result extraction, metadata processing, and data transformation.
"""

import logging
import re
from datetime import datetime
from typing import Any, Optional, Tuple, TypedDict

logger = logging.getLogger(__name__)


class SerperRequestParams(TypedDict):
    """Type definition for Serper API request parameters."""

    q: str  # Query string (required)
    num: int  # Number of results (1-100)
    gl: str  # Geography (2-letter country code)
    hl: str  # Language (2-letter language code)


def validate_serper_params(params: dict) -> SerperRequestParams:
    """
    Validate and normalize Serper API parameters.

    Args:
        params: Raw parameters dictionary

    Returns:
        SerperRequestParams: Validated parameters

    Raises:
        ValueError: If validation fails
    """
    query = params.get("q", "").strip()
    if not query:
        raise ValueError("Query cannot be empty")

    num = params.get("num", 10)
    if not isinstance(num, int) or num < 1 or num > 100:
        raise ValueError("num must be between 1 and 100")

    gl = params.get("gl", "us")
    if not isinstance(gl, str) or len(gl) != 2:
        raise ValueError("gl must be a 2-letter country code")

    hl = params.get("hl", "en")
    if not isinstance(hl, str) or len(hl) != 2:
        raise ValueError("hl must be a 2-letter language code")

    return {
        "q": query,
        "num": num,
        "gl": gl.lower(),
        "hl": hl.lower(),
    }


class SerperProcessor:
    """Processes and extracts data from Serper API responses."""

    def __init__(self):
        """Initialize the processor with default settings."""
        self.alternative_result_types = [
            "knowledgeGraph",
            "answerBox",
            "topStories",
            "peopleAlsoAsk",
            "relatedSearches",
        ]

        # Sensitive data patterns to sanitize
        self.sensitive_patterns = {
            "api_key": re.compile(
                r'(api[_-]?key|apikey)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9\-_]+)',
                re.IGNORECASE,
            ),
            "token": re.compile(
                r'(token|bearer|auth)["\']?\s*[:=]\s*["\']?([a-zA-Z0-9\-_]+)',
                re.IGNORECASE,
            ),
            "password": re.compile(
                r'(password|pwd|pass)["\']?\s*[:=]\s*["\']?([^\s"\']+)', re.IGNORECASE
            ),
            "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            "credit_card": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        }

        # Fields to always sanitize
        self.fields_to_sanitize = ["gl", "uule", "hl", "cr", "lr"]

    def build_request_params(
        self,
        query: str,
        num_results: int = 10,
        search_type: str = "search",
        location: str = "United States",
        language: str = "en",
        country_code: str = "us",
        max_results_limit: int = 100,
        **kwargs,
    ) -> dict:
        """
        Build request parameters for Serper API.

        Args:
            query: Search query string
            num_results: Number of results to retrieve
            search_type: Type of search (search, images, news, etc.)
            location: Location for search results
            language: Language code for results
            country_code: Country code for results
            max_results_limit: Maximum results API allows
            **kwargs: Additional parameters (page, requested_num, date_from)

        Returns:
            Dictionary of API parameters
        """
        # Validate core parameters first
        validated_params = validate_serper_params(
            {
                "q": query,
                "num": min(num_results, max_results_limit),
                "gl": country_code,
                "hl": language[:2] if len(language) > 2 else language,
            }
        )

        # Build base parameters from validated inputs
        params = {
            "q": validated_params["q"],
            "num": validated_params["num"],
            "gl": validated_params["gl"],
            "hl": validated_params["hl"],
        }

        # Add pagination support (page parameter for Serper API)
        if "page" in kwargs and kwargs["page"]:
            page = int(kwargs["page"])
            if page > 1:
                params["page"] = page
                logger.debug(f"Adding pagination: page={page}")

        # Add date filtering if provided
        if "date_from" in kwargs and kwargs["date_from"]:
            params["tbs"] = f"cdr:1,cd_min:{kwargs['date_from']}"

        # Store internal tracking parameters
        if "requested_num" in kwargs:
            params["_internal_requested_num"] = kwargs["requested_num"]

        return params

    def extract_organic_results(self, response: dict) -> list:
        """
        Extract and process organic search results.

        Args:
            response: Raw API response

        Returns:
            List of processed organic results
        """
        organic = response.get("organic", [])
        processed = []

        for idx, result in enumerate(organic):
            try:
                processed_result = {
                    "position": idx + 1,
                    "title": result.get("title", ""),
                    "link": result.get("link", ""),
                    "snippet": result.get("snippet", ""),
                    "date": self._parse_date(result.get("date")),
                    "domain": self._extract_domain(result.get("link", "")),
                    "sitelinks": result.get("sitelinks", []),
                    "raw_position": result.get("position", idx + 1),
                    # Additional metadata fields
                    "cached": result.get("cached"),
                    "related": result.get("related"),
                    "rich_snippet": result.get("richSnippet"),
                }

                # Clean up None values
                processed_result = {
                    k: v for k, v in processed_result.items() if v is not None
                }
                processed.append(processed_result)

            except Exception as e:
                logger.error(f"Error processing result at position {idx + 1}: {e}")
                # Still include partial result if possible
                processed.append(
                    {
                        "position": idx + 1,
                        "title": result.get("title", "Error processing result"),
                        "link": result.get("link", ""),
                        "error": str(e),
                    }
                )

        return processed

    def sanitize_sensitive_data(self, data: Any) -> Any:
        """
        Sanitize sensitive data from search parameters and metadata.

        Args:
            data: Data to sanitize (dict, list, or string)

        Returns:
            Sanitized data with sensitive information redacted
        """
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                # Check if key should be sanitized
                if key.lower() in self.fields_to_sanitize:
                    sanitized[key] = "[REDACTED]"
                elif any(
                    pattern in key.lower()
                    for pattern in ["key", "token", "password", "secret"]
                ):
                    sanitized[key] = "[REDACTED]"
                else:
                    # Recursively sanitize value
                    sanitized[key] = self.sanitize_sensitive_data(value)
            return sanitized

        elif isinstance(data, list):
            return [self.sanitize_sensitive_data(item) for item in data]

        elif isinstance(data, str):
            # Check for sensitive patterns in strings
            sanitized_str = data
            for pattern_name, pattern in self.sensitive_patterns.items():
                if pattern.search(sanitized_str):
                    if pattern_name == "email":
                        # Partially redact email
                        sanitized_str = pattern.sub(
                            lambda m: (
                                m.group(0).split("@")[0][:2]
                                + "***@"
                                + m.group(0).split("@")[1]
                            ),
                            sanitized_str,
                        )
                    else:
                        sanitized_str = pattern.sub("[REDACTED]", sanitized_str)
            return sanitized_str

        else:
            return data

    def extract_metadata(self, response: dict) -> dict:
        """
        Extract search metadata from response.

        Args:
            response: Raw API response

        Returns:
            Dictionary containing search metadata
        """
        search_info = response.get("searchInformation", {})

        # Sanitize search parameters before storing
        search_params = response.get("searchParameters", {})
        sanitized_params = self.sanitize_sensitive_data(search_params)

        metadata = {
            "total_results": self._parse_total_results(search_info.get("totalResults")),
            "search_time": search_info.get(
                "searchTime"
            ),  # Changed from timeTaken to searchTime
            "organic_results_count": len(response.get("organic", [])),
            "credits_used": response.get("credits"),
            "search_parameters": sanitized_params,  # Use sanitized parameters
            "query_displayed": search_info.get("queryDisplayed"),
            "detected_location": search_info.get("detectedLocation"),
        }

        # Add alternative result type counts
        for result_type in self.alternative_result_types:
            if result_type in response:
                metadata[f"{result_type}_present"] = True
                if isinstance(response[result_type], list):
                    metadata[f"{result_type}_count"] = len(response[result_type])

        # Clean up None values
        return {k: v for k, v in metadata.items() if v is not None}

    def extract_alternative_results(self, response: dict) -> dict:
        """
        Extract alternative result types (knowledge graph, answer box, etc.).

        Args:
            response: Raw API response

        Returns:
            Dictionary containing alternative results
        """
        alternatives = {}

        # Knowledge Graph
        if "knowledgeGraph" in response:
            kg = response["knowledgeGraph"]
            alternatives["knowledgeGraph"] = {
                "title": kg.get("title"),
                "type": kg.get("type"),
                "description": kg.get("description"),
                "website": kg.get("website"),
                "image_url": kg.get("imageUrl"),
                "attributes": kg.get("attributes", {}),
            }

        # Answer Box
        if "answerBox" in response:
            ab = response["answerBox"]
            alternatives["answerBox"] = {
                "title": ab.get("title"),
                "answer": ab.get("answer"),
                "snippet": ab.get("snippet"),
                "link": ab.get("link"),
            }

        # People Also Ask
        if "peopleAlsoAsk" in response:
            alternatives["peopleAlsoAsk"] = [
                {
                    "question": item.get("question"),
                    "snippet": item.get("snippet"),
                    "link": item.get("link"),
                    "title": item.get("title"),
                }
                for item in response["peopleAlsoAsk"]
            ]

        # Related Searches
        if "relatedSearches" in response:
            alternatives["relatedSearches"] = [
                {"query": item.get("query")} for item in response["relatedSearches"]
            ]

        # Top Stories
        if "topStories" in response:
            alternatives["topStories"] = [
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "source": item.get("source"),
                    "date": self._parse_date(item.get("date")),
                    "image_url": item.get("imageUrl"),
                }
                for item in response["topStories"]
            ]

        return alternatives

    def process_full_response(self, response: dict) -> dict:
        """
        Process the full API response into a structured format.

        Args:
            response: Raw API response

        Returns:
            Fully processed response dictionary
        """
        try:
            processed = {
                "organic_results": self.extract_organic_results(response),
                "metadata": self.extract_metadata(response),
                "alternative_results": self.extract_alternative_results(response),
                "raw_response": {
                    "credits": response.get("credits"),
                    "searchParameters": response.get("searchParameters", {}),
                },
                "processed_at": datetime.utcnow().isoformat(),
            }

            # Log processing statistics for debugging (Issue #91, #108)
            organic_count = len(processed["organic_results"])
            logger.info(f"[Issue #108] Processed {organic_count} organic results")

            if organic_count == 0 and processed["alternative_results"]:
                logger.warning(
                    f"[Issue #108] No organic results but found alternative types: "
                    f"{list(processed['alternative_results'].keys())}"
                )

            return processed

        except Exception as e:
            logger.error(f"Error processing full response: {e}")
            # Return minimal processed response on error
            return {
                "organic_results": [],
                "metadata": {"error": str(e)},
                "alternative_results": {},
                "processed_at": datetime.utcnow().isoformat(),
            }

    def _extract_domain(self, url: str) -> str:
        """
        Extract and sanitize domain from URL with validation.

        (Deprecated: Now delegates to shared utility)

        Args:
            url: URL string

        Returns:
            Sanitized domain name or empty string
        """
        from apps.core.utils import extract_domain

        return extract_domain(url, lowercase=True, sanitize=True)

    def handle_api_response(  # noqa: C901 - API response
        self, response, api_params: dict, requested_num: int
    ) -> Tuple[dict, dict]:
        """
        Handle different API response codes and process the response.

        Args:
            response: HTTP response object
            api_params: Parameters sent to API
            requested_num: Number of results requested

        Returns:
            Tuple of (response data, metadata)

        Raises:
            Various SerperAPI exceptions based on response code
        """
        from .serper_exceptions import (
            SerperAuthError,
            SerperQuotaError,
            SerperRateLimitError,
        )

        if response.status_code == 200:
            # Log response for debugging
            logger.info(f"[Issue #91] Response status: {response.status_code}")
            logger.info(f"[Issue #91] Response headers: {dict(response.headers)}")

            data = response.json()

            # Check for error in successful response (API can return 200 with error)
            if "error" in data or "error_type" in data:
                error_msg = data.get("error", "Unknown API error")
                error_type = data.get("error_type", "unknown")
                logger.error(
                    f"Serper API returned error in 200 response. "
                    f"Error: {error_msg}, Type: {error_type}"
                )

                # Map error types to appropriate exceptions
                if (
                    "invalid_api_key" in str(error_type).lower()
                    or "api_key" in str(error_msg).lower()
                ):
                    raise SerperAuthError(f"Invalid API key: {error_msg}")
                elif "rate_limit" in str(error_type).lower():
                    raise SerperRateLimitError(f"Rate limit exceeded: {error_msg}")
                elif (
                    "quota" in str(error_type).lower()
                    or "limit" in str(error_msg).lower()
                ):
                    raise SerperQuotaError(f"API quota exceeded: {error_msg}")
                else:
                    # Return error response for unknown errors
                    return self.create_error_response(
                        "api_error", error_msg, api_error_type=error_type
                    )

            # Process response
            processed_response = self.process_full_response(data)

            # Add request headers metadata (for backward compatibility)
            if "metadata" in processed_response:
                # Add time_taken from search_time for backward compatibility
                if "search_time" in processed_response["metadata"]:
                    processed_response["metadata"]["time_taken"] = processed_response[
                        "metadata"
                    ]["search_time"]
                # Add request_id from headers
                processed_response["metadata"]["request_id"] = response.headers.get(
                    "X-Request-ID"
                )

            # Log results for debugging
            organic_count = len(processed_response["organic_results"])
            logger.info(
                f"Serper API response: received {organic_count} organic results"
            )
            logger.warning(
                f"[Issue #108] SERPER API RESPONSE RECEIVED: {organic_count} organic results"
            )

            # Log first 3 results for debugging
            if processed_response["organic_results"]:
                for i, result in enumerate(processed_response["organic_results"][:3]):
                    logger.info(
                        f"[Issue #108] Result {i + 1}: {result.get('link', 'NO_LINK')} - "
                        f"{result.get('title', 'NO_TITLE')[:50]}"
                    )
            else:
                logger.warning("[Issue #108] NO ORGANIC RESULTS IN RESPONSE")

            # Warn if API returned fewer results than requested
            if organic_count < api_params.get("num", 10):
                if organic_count < requested_num * 0.2:
                    severity = "SEVERE"
                elif organic_count < requested_num * 0.5:
                    severity = "WARNING"
                else:
                    severity = "INFO"

                log_msg = (
                    f"[Issue #91] {severity}: Serper API returned fewer results than requested. "
                    f"Requested: {api_params.get('num', 10)}, Received: {organic_count}"
                )

                if severity == "SEVERE":
                    logger.error(log_msg)
                elif severity == "WARNING":
                    logger.warning(log_msg)
                else:
                    logger.info(log_msg)

            # Return processed results and metadata
            # Maintain backward compatibility by returning raw response format
            return data, processed_response["metadata"]

        elif response.status_code == 401:
            raise SerperAuthError("Invalid API key")
        elif response.status_code == 402:
            raise SerperQuotaError("API quota exceeded")
        elif response.status_code == 403:
            raise SerperQuotaError("API quota exceeded")
        elif response.status_code == 429:
            retry_after = response.headers.get("Retry-After", 60)
            raise SerperRateLimitError(
                f"Rate limit exceeded. Retry after {retry_after} seconds",
                retry_after=int(retry_after),
            )
        else:
            response.raise_for_status()
            raise ValueError(f"Unexpected response status: {response.status_code}")

    def create_error_response(
        self, error_type: str, error_message: str, **kwargs
    ) -> Tuple[dict, dict]:
        """
        Create standardized error response for API failures.

        Args:
            error_type: Type of error (circuit_breaker_open, timeout, general_error)
            error_message: Human-readable error message
            **kwargs: Additional metadata

        Returns:
            Tuple of (error response dict, metadata dict)
        """
        response = {
            "error": error_message,
            "error_type": error_type,
            "organic": [],
            "knowledgeGraph": None,
        }

        metadata = {error_type.replace("_", ""): True}

        # Add specific error details
        if error_type == "circuit_breaker_open":
            response["circuit_breaker"] = {
                "state": "open",
                "message": "Too many failures detected. Service is being protected.",
            }
            metadata["circuit_open"] = True
        elif error_type == "timeout":
            metadata["timeout"] = True
        else:
            metadata["error"] = True

        # Add any additional kwargs to response
        response.update(kwargs)

        return response, metadata

    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        """
        Parse and normalize date string.

        Args:
            date_str: Date string from API

        Returns:
            Normalized date string or None
        """
        if not date_str:
            return None

        # Serper returns dates in various formats
        # For now, just return as-is, but could normalize here
        return date_str

    def _parse_total_results(self, total_results):
        """
        Parse total results count.

        Args:
            total_results: Total results value from API

        Returns:
            String representation of total results for backward compatibility
        """
        if total_results is None:
            return None

        # Keep as string for backward compatibility with tests
        if isinstance(total_results, str):
            return total_results
        else:
            # Convert numbers to string
            return str(total_results)

    def format_for_storage(self, processed_response: dict) -> dict:
        """
        Format processed response for database storage.

        Args:
            processed_response: Processed response dictionary

        Returns:
            Formatted dictionary suitable for storage
        """
        # Extract just the essential data for storage
        return {
            "organic_results": processed_response.get("organic_results", []),
            "total_results": processed_response.get("metadata", {}).get(
                "total_results"
            ),
            "search_time": processed_response.get("metadata", {}).get("search_time"),
            "credits_used": processed_response.get("metadata", {}).get("credits_used"),
            "alternative_results_summary": {
                result_type: True
                for result_type in self.alternative_result_types
                if result_type in processed_response.get("alternative_results", {})
            },
            "processed_at": processed_response.get("processed_at"),
        }
