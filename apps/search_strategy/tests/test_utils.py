"""Tests for search_strategy utility functions."""

from django.test import TestCase

from ..utils import optimize_query_string


class OptimizeQueryStringTests(TestCase):
    """Test cases for optimize_query_string."""

    def test_optimize_query_string(self):
        """Test query string optimization."""
        long_query = "elderly adults with chronic conditions using digital health interventions in primary care settings with mobile applications"
        analysis = optimize_query_string(long_query)

        self.assertIn("original_query", analysis)
        self.assertIn("word_count", analysis)
        self.assertIn("suggestions", analysis)
        self.assertGreater(analysis["word_count"], 10)

        # Should suggest shortening
        suggestions_text = " ".join(analysis["suggestions"])
        self.assertIn("shortening", suggestions_text.lower())
