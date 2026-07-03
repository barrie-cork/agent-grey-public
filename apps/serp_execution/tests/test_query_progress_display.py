"""
Tests for query progress display functionality.
Tests detailed query messages, result counts, and progress updates.
"""

import unittest
from unittest.mock import Mock

from apps.serp_execution.utils import (
    build_execution_progress_message,
    extract_result_count,
    format_result_count_message,
    parse_query_details,
    safe_get_query_text,
)


class TestQueryParser(unittest.TestCase):
    """Test query parsing functionality."""

    def test_parse_domain_query(self) -> None:
        """Test parsing query with domain."""
        query = "site:www.cnn.com (Sea) AND (Sand) AND (Sun)"
        result = parse_query_details(query)

        self.assertEqual(result["domain"], "www.cnn.com")
        self.assertEqual(result["terms"], "(Sea) AND (Sand) AND (Sun)")
        self.assertEqual(result["file_type"], "")
        self.assertEqual(result["full_text"], "www.cnn.com (Sea) AND (Sand) AND (Sun)")

    def test_parse_domain_and_type_query(self) -> None:
        """Test parsing query with domain and file type."""
        query = "site:www.cnn.com (Sea) AND (Sand) type:pdf"
        result = parse_query_details(query)

        self.assertEqual(result["domain"], "www.cnn.com")
        self.assertEqual(result["terms"], "(Sea) AND (Sand)")
        self.assertEqual(result["file_type"], "pdf")
        self.assertEqual(result["full_text"], "www.cnn.com (Sea) AND (Sand) type:pdf")

    def test_parse_general_query(self) -> None:
        """Test parsing general query without domain."""
        query = "(Sea) AND (Sand) AND (Sun)"
        result = parse_query_details(query)

        self.assertEqual(result["domain"], "")
        self.assertEqual(result["terms"], "(Sea) AND (Sand) AND (Sun)")
        self.assertEqual(result["file_type"], "")
        self.assertEqual(result["full_text"], "(Sea) AND (Sand) AND (Sun)")

    def test_parse_with_api_params(self) -> None:
        """Test parsing with API parameters fallback."""
        query = "(Sea) AND (Sand)"
        api_params = {"siteSearch": "www.msn.com", "fileType": "docx"}
        result = parse_query_details(query, api_params)

        self.assertEqual(result["domain"], "www.msn.com")
        self.assertEqual(result["terms"], "(Sea) AND (Sand)")
        self.assertEqual(result["file_type"], "docx")
        self.assertEqual(result["full_text"], "www.msn.com (Sea) AND (Sand) type:docx")

    def test_parse_empty_query(self) -> None:
        """Test parsing empty query."""
        result = parse_query_details("")

        self.assertEqual(result["domain"], "")
        self.assertEqual(result["terms"], "")
        self.assertEqual(result["file_type"], "")
        self.assertEqual(result["full_text"], "")


class TestProgressMessageBuilder(unittest.TestCase):
    """Test progress message building."""

    def test_build_execution_message(self) -> None:
        """Test building execution message."""
        query_details = {
            "domain": "www.cnn.com",
            "terms": "(Sea) AND (Sand)",
            "file_type": "pdf",
            "full_text": "www.cnn.com (Sea) AND (Sand) type:pdf",
        }
        result = build_execution_progress_message(query_details)

        self.assertEqual(result, "Executing www.cnn.com (Sea) AND (Sand) type:pdf")

    def test_build_completed_message(self) -> None:
        """Test building completed message."""
        query_details = {
            "domain": "www.msn.com",
            "terms": "(Sun) AND (Moon)",
            "file_type": "",
            "full_text": "www.msn.com (Sun) AND (Moon)",
        }
        result = build_execution_progress_message(query_details, "Completed")

        self.assertEqual(result, "Completed www.msn.com (Sun) AND (Moon)")

    def test_build_message_no_domain(self) -> None:
        """Test building message without domain."""
        query_details = {
            "domain": "",
            "terms": "(Sea) AND (Sand)",
            "file_type": "pdf",
            "full_text": "(Sea) AND (Sand) type:pdf",
        }
        result = build_execution_progress_message(query_details)

        self.assertEqual(result, "Executing (Sea) AND (Sand) type:pdf")

    def test_build_message_empty_details(self) -> None:
        """Test building message with empty details."""
        result = build_execution_progress_message({})

        self.assertEqual(result, "Executing query")

    def test_build_message_fallback_construction(self) -> None:
        """Test message construction when full_text is missing."""
        query_details = {
            "domain": "example.com",
            "terms": "search terms",
            "file_type": "doc",
        }
        result = build_execution_progress_message(query_details)

        self.assertEqual(result, "Executing example.com search terms type:doc")


class TestResultCountExtractor(unittest.TestCase):
    """Test result count extraction."""

    def test_extract_organic_results(self) -> None:
        """Test extracting count from organic results."""
        api_response = {
            "organic": [
                {"title": "Result 1"},
                {"title": "Result 2"},
                {"title": "Result 3"},
            ]
        }
        count = extract_result_count(api_response)

        self.assertEqual(count, 3)

    def test_extract_news_results(self) -> None:
        """Test extracting count from news results."""
        api_response = {"news": [{"title": "News 1"}, {"title": "News 2"}]}
        count = extract_result_count(api_response)

        self.assertEqual(count, 2)

    def test_extract_places_results(self) -> None:
        """Test extracting count from places results."""
        api_response = {"places": [{"name": "Place 1"}]}
        count = extract_result_count(api_response)

        self.assertEqual(count, 1)

    def test_extract_from_search_information(self) -> None:
        """Test extracting from search information."""
        api_response = {"searchInformation": {"totalResults": "150"}}
        count = extract_result_count(api_response)

        self.assertEqual(count, 150)

    def test_extract_empty_response(self) -> None:
        """Test extracting from empty response."""
        count = extract_result_count({})
        self.assertEqual(count, 0)

        count = extract_result_count(None)  # type: ignore[arg-type]
        self.assertEqual(count, 0)

    def test_extract_priority_organic_over_total(self) -> None:
        """Test that organic count takes priority over totalResults."""
        api_response = {
            "organic": [{"title": "Result 1"}, {"title": "Result 2"}],
            "searchInformation": {"totalResults": "1000"},
        }
        count = extract_result_count(api_response)

        self.assertEqual(count, 2)  # Should use organic count, not totalResults


class TestResultCountFormatter(unittest.TestCase):
    """Test result count message formatting."""

    def test_format_zero_results(self) -> None:
        """Test formatting zero results."""
        message = format_result_count_message(0)
        self.assertEqual(message, "No results found from Serper.dev")

    def test_format_single_result(self) -> None:
        """Test formatting single result."""
        message = format_result_count_message(1)
        self.assertEqual(message, "1 result retrieved from Serper.dev")

    def test_format_multiple_results(self) -> None:
        """Test formatting multiple results."""
        message = format_result_count_message(23)
        self.assertEqual(message, "23 results retrieved from Serper.dev")

    def test_format_custom_source(self) -> None:
        """Test formatting with custom source."""
        message = format_result_count_message(10, "Google API")
        self.assertEqual(message, "10 results retrieved from Google API")


class TestSafeQueryTextExtractor(unittest.TestCase):
    """Test safe query text extraction."""

    def test_extract_from_object_with_query_text(self) -> None:
        """Test extracting from object with query_text attribute."""
        mock_query = Mock()
        mock_query.query_text = "test query"

        result = safe_get_query_text(mock_query)
        self.assertEqual(result, "test query")

    def test_extract_from_object_without_query_text(self) -> None:
        """Test extracting from object without query_text attribute falls back to str()."""
        mock_query = Mock(spec=["text"])
        mock_query.text = "another query"

        result = safe_get_query_text(mock_query)
        # Function doesn't check 'text' attribute on objects, falls back to str()
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_extract_from_dict(self) -> None:
        """Test extracting from dictionary."""
        query_dict = {"query_text": "dict query"}
        result = safe_get_query_text(query_dict)
        self.assertEqual(result, "dict query")

        query_dict = {"text": "dict text"}
        result = safe_get_query_text(query_dict)
        self.assertEqual(result, "dict text")

    def test_extract_from_none(self) -> None:
        """Test extracting from None."""
        result = safe_get_query_text(None)
        self.assertEqual(result, "")

    def test_extract_fallback_to_string(self) -> None:
        """Test fallback to string conversion."""
        result = safe_get_query_text("plain string")
        self.assertEqual(result, "plain string")

    def test_extract_handles_none_values(self) -> None:
        """Test handling None values in attributes."""
        mock_query = Mock()
        mock_query.query_text = None

        result = safe_get_query_text(mock_query)
        self.assertEqual(result, "")


class TestIntegration(unittest.TestCase):
    """Test integration of query display functions."""

    def test_full_query_processing_pipeline(self) -> None:
        """Test the full pipeline from raw query to progress message."""
        # Start with raw query
        raw_query = "site:www.cnn.com (Sea) AND (Sand) AND (Sun) type:pdf"

        # Parse query
        query_details = parse_query_details(raw_query)

        # Build progress message
        progress_message = build_execution_progress_message(query_details, "Executing")

        # Verify result
        expected = "Executing www.cnn.com (Sea) AND (Sand) AND (Sun) type:pdf"
        self.assertEqual(progress_message, expected)

    def test_api_response_to_count_message(self) -> None:
        """Test processing API response to count message."""
        # Simulate API response
        api_response = {"organic": [{"title": f"Result {i}"} for i in range(23)]}

        # Extract count
        count = extract_result_count(api_response)

        # Format message
        message = format_result_count_message(count)

        # Verify result
        self.assertEqual(message, "23 results retrieved from Serper.dev")

    def test_edge_case_handling(self) -> None:
        """Test handling various edge cases."""
        # Empty query
        details = parse_query_details("")
        message = build_execution_progress_message(details)
        self.assertEqual(message, "Executing query")

        # Malformed query with extra spaces
        query = "site:www.example.com   (term1)   AND   (term2)   type:pdf"
        details = parse_query_details(query)
        self.assertIn("www.example.com", details["full_text"])
        self.assertIn("(term1)   AND   (term2)", details["full_text"])
        self.assertIn("pdf", details["full_text"])


if __name__ == "__main__":
    unittest.main()
