"""
Query and response validation for Serper API.
Extracted from SerperClient to follow single responsibility principle.
"""

import logging
import re

logger = logging.getLogger(__name__)


class SerperValidator:
    """Validates Serper API queries and responses."""

    def __init__(self):
        self.max_query_length = 2048
        self.valid_engines = ["google", "bing", "yandex", "baidu"]
        self.dangerous_patterns = [
            r"(DROP|DELETE|INSERT|UPDATE)\s+",  # SQL injection patterns
            r"<script.*?>.*?</script>",  # XSS patterns
            r"javascript:",  # JavaScript protocols
        ]

    def validate_query(self, query: str):
        """
        Validate search query before API call.

        Args:
            query: Search query string

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not query or not query.strip():
            return False, "Query cannot be empty"

        if len(query) > self.max_query_length:
            return False, f"Query too long (max {self.max_query_length} characters)"

        # Check for unmatched quotes
        if query.count('"') % 2 != 0:
            return False, "Unmatched quotes in query"

        # Check for dangerous patterns (SQL injection, XSS)
        for pattern in self.dangerous_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                logger.warning(
                    f"Query contains potentially dangerous pattern: {pattern}"
                )
                return False, "Query contains potentially dangerous pattern"

        # Check for excessive special characters that might break the API
        special_char_count = sum(
            1 for char in query if not char.isalnum() and not char.isspace()
        )
        if special_char_count > len(query) * 0.5:  # More than 50% special characters
            return False, "Query contains too many special characters"

        return True, None

    def validate_response_structure(self, response_data):
        """
        Validate the structure of the Serper API response.

        Args:
            response_data: The JSON response from Serper API

        Returns:
            Tuple of (is_valid, error_message, warnings)
        """
        warnings = []

        if not response_data:
            return False, "Response data is None or empty", warnings

        if not isinstance(response_data, dict):
            return (
                False,
                f"Response is not a dictionary, got {type(response_data)}",
                warnings,
            )

        # Check for essential keys
        if "organic" not in response_data:
            warnings.append(
                "No 'organic' key in response - API may have changed format"
            )

            # Check for alternative result types
            alternative_types = [
                "knowledgeGraph",
                "answerBox",
                "topStories",
                "peopleAlsoAsk",
            ]
            found_alternatives = [
                key for key in alternative_types if key in response_data
            ]

            if found_alternatives:
                warnings.append(
                    f"Found alternative result types: {', '.join(found_alternatives)}"
                )
            else:
                return (
                    False,
                    "No organic results and no alternative result types found",
                    warnings,
                )

        # Validate organic results structure if present
        if "organic" in response_data:
            is_valid, error_msg, result_warnings = self._validate_organic_results(
                response_data["organic"]
            )
            warnings.extend(result_warnings)
            if not is_valid:
                return False, error_msg, warnings

        # Check for search metadata
        if "searchInformation" not in response_data:
            warnings.append(
                "No 'searchInformation' key - cannot get total results count"
            )

        return True, None, warnings

    def _validate_organic_results(self, organic):
        """
        Validate the structure of organic search results.

        Args:
            organic: The organic results from the response

        Returns:
            Tuple of (is_valid, error_message, warnings)
        """
        warnings = []

        if not isinstance(organic, list):
            return False, f"'organic' is not a list, got {type(organic)}", warnings

        if organic:
            # Validate first result structure as a sample
            first_result = organic[0]

            if not isinstance(first_result, dict):
                return (
                    False,
                    f"First organic result is not a dictionary, got {type(first_result)}",
                    warnings,
                )

            # Check required keys
            required_keys = ["link", "title"]
            missing_keys = [key for key in required_keys if key not in first_result]

            if missing_keys:
                warnings.append(f"First result missing keys: {', '.join(missing_keys)}")

            # Check for recommended keys
            recommended_keys = ["snippet", "position"]
            missing_recommended = [
                key for key in recommended_keys if key not in first_result
            ]

            if missing_recommended:
                warnings.append(
                    f"First result missing recommended keys: {', '.join(missing_recommended)}"
                )

        return True, None, warnings

    def validate_request_params(self, params: dict):
        """
        Validate request parameters before sending to API.

        Args:
            params: Dictionary of API parameters

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required parameters
        if "q" not in params:
            return False, "Missing required parameter 'q' (query)"

        # Validate num parameter
        if "num" in params:
            num = params["num"]
            if not isinstance(num, int) or num < 1 or num > 100:
                return False, "'num' must be an integer between 1 and 100"

        # Validate language parameter
        if "hl" in params:
            hl = params["hl"]
            if not isinstance(hl, str) or len(hl) != 2:
                return False, "'hl' must be a 2-letter language code"

        # Validate country parameter
        if "gl" in params:
            gl = params["gl"]
            if not isinstance(gl, str) or len(gl) != 2:
                return False, "'gl' must be a 2-letter country code"

        return True, None

    def validate_api_key(self, api_key: str):
        """
        Validate API key format.

        Args:
            api_key: The API key to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not api_key:
            return False, "API key is required"

        if not isinstance(api_key, str):
            return False, "API key must be a string"

        # Basic format check (adjust based on actual Serper API key format)
        if len(api_key) < 20:
            return False, "API key appears to be too short"

        # Check for common placeholder values
        placeholder_patterns = ["your_api_key", "xxxx", "test", "demo"]
        if any(pattern in api_key.lower() for pattern in placeholder_patterns):
            return False, "API key appears to be a placeholder value"

        return True, None
