"""
Tests for ExportService.

Tests data export functionality in various formats (CSV, JSON).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.reporting.services.export_service import ExportService
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestExportService(TestCase):
    """Test cases for ExportService."""

    def setUp(self):
        """Set up test data."""
        self.service = ExportService()

        # Create test user
        self.user = create_test_user()

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test description",
            owner=self.user,
            status="completed",
        )

        # Create test results
        self.result1 = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result 1",
            url="https://example.com/1",
            snippet="Test snippet 1",
        )

        self.result2 = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result 2",
            url="https://example.com/2",
            snippet="Test snippet 2",
        )

        # Create review decisions
        SimpleReviewDecision.objects.create(
            result=self.result1,
            session=self.session,
            decision="include",
            reviewer=self.user,
            notes="Good quality result",
        )

        SimpleReviewDecision.objects.create(
            result=self.result2,
            session=self.session,
            decision="exclude",
            reviewer=self.user,
            exclusion_reason="not_relevant",
        )

    def test_export_to_csv_studies(self):
        """Test CSV export with studies data."""
        data = {
            "studies": [
                {"title": "Result 1", "url": "http://example.com/1"},
                {"title": "Result 2", "url": "http://example.com/2"},
            ]
        }

        result = self.service.export_to_csv(data, export_type="studies")

        self.assertIsInstance(result, str)
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 3)  # Header + 2 rows
        self.assertIn("title", lines[0])
        self.assertIn("url", lines[0])
        self.assertIn("Result 1", lines[1])

    def test_export_to_csv_queries(self):
        """Test CSV export with queries data."""
        data = {
            "queries": [
                {
                    "id": "1",
                    "query_text": "test query",
                    "pic_framework": {
                        "population": "pop",
                        "interest": "int",
                        "context": "ctx",
                    },
                    "parameters": {"search_engines": ["google"]},
                    "execution_results": {"total_results": 10, "success_rate": 100},
                },
            ]
        }

        result = self.service.export_to_csv(data, export_type="queries")

        self.assertIsInstance(result, str)
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 2)  # Header + 1 row
        self.assertIn("query_text", lines[0])
        self.assertIn("test query", lines[1])

    def test_export_to_csv_empty_studies(self):
        """Test CSV export with empty studies list."""
        data = {"studies": []}

        result = self.service.export_to_csv(data, export_type="studies")

        self.assertIsInstance(result, str)
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 1)  # Header only

    def test_export_to_csv_no_matching_key(self):
        """Test CSV export when data doesn't match export type."""
        data = {"other_data": []}

        result = self.service.export_to_csv(data, export_type="studies")

        self.assertIsInstance(result, str)
        self.assertEqual(result, "")  # No output when key not found

    def test_generate_export_formats_json(self):
        """Test generating export in JSON format."""
        data = {"key": "value"}

        result = self.service.generate_export_formats(data, "json")

        self.assertIsInstance(result, dict)
        self.assertEqual(result["format"], "json")
        self.assertIn("generated_at", result)
        self.assertEqual(result["data"], data)
        self.assertIn("file_info", result)
        self.assertIn("filename", result["file_info"])
        self.assertIn(".json", result["file_info"]["filename"])
        self.assertEqual(result["file_info"]["content_type"], "application/json")

    def test_generate_export_formats_csv(self):
        """Test generating export in CSV format."""
        data = {"key": "value"}

        result = self.service.generate_export_formats(data, "csv")

        self.assertIsInstance(result, dict)
        self.assertEqual(result["format"], "csv")
        self.assertIn("file_info", result)
        self.assertIn(".csv", result["file_info"]["filename"])

    def test_get_content_type(self):
        """Test content type resolution."""
        self.assertEqual(self.service.get_content_type("json"), "application/json")
        self.assertEqual(self.service.get_content_type("csv"), "text/csv")

    def test_estimate_file_size(self):
        """Test file size estimation."""
        data = {"key": "value"}

        size = self.service.estimate_file_size(data, "json")

        self.assertIsInstance(size, int)
        self.assertGreater(size, 0)

    def test_generate_export_summary(self):
        """Test export summary generation."""
        export_types = ["prisma_flow", "study_characteristics"]

        result = self.service.generate_export_summary(
            str(self.session.id), export_types
        )

        self.assertIn("session_id", result)
        self.assertIn("data_available", result)
        self.assertIn("export_options", result)
        self.assertIn("recommended_formats", result)

        self.assertEqual(result["data_available"]["total_results"], 2)
        self.assertEqual(result["data_available"]["included_studies"], 1)

    def test_generate_export_summary_empty_session(self):
        """Test export summary for session with no results."""
        empty_session = SearchSession.objects.create(
            title="Empty Session",
            owner=self.user,
            status="completed",
        )

        result = self.service.generate_export_summary(
            str(empty_session.id), ["prisma_flow"]
        )

        self.assertEqual(result["data_available"]["total_results"], 0)
        self.assertEqual(result["data_available"]["included_studies"], 0)
