"""
Test cases for CSVReportGenerator.

Tests IRR metrics CSV export and decision audit trail CSV export
for PRISMA 2020 compliance and dual-screening support.
"""

from datetime import datetime
from io import StringIO
from unittest.mock import Mock
from uuid import uuid4

from django.test import TestCase

from apps.reporting.services.report_generators.csv_generator import CSVReportGenerator


class CSVReportGeneratorBaseTest(TestCase):
    """Base test class with common setup."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = CSVReportGenerator()
        self.mock_report = Mock()
        self.mock_report.parameters = {}


class TestIRRMetricsCSV(CSVReportGeneratorBaseTest):
    """Tests for IRR metrics CSV generation."""

    def test_generate_irr_metrics_csv_with_model_objects(self):
        """Test IRR metrics CSV generation with model-like objects."""
        # Create mock IRR metric objects
        mock_metric = Mock()
        mock_metric.cohens_kappa = 0.85
        mock_metric.percentage_agreement = 92.5
        mock_metric.total_comparisons = 100
        mock_metric.agreements = 92
        mock_metric.disagreements = 8
        mock_metric.screening_stage = "title_abstract"
        mock_metric.calculated_at = datetime(2025, 12, 26, 10, 0, 0)
        mock_metric.reviewer_a = Mock()
        mock_metric.reviewer_a.get_full_name.return_value = "John Doe"
        mock_metric.reviewer_b = Mock()
        mock_metric.reviewer_b.get_full_name.return_value = "Jane Smith"

        output = StringIO()
        self.generator._generate_irr_metrics_csv(output, [mock_metric])
        content = output.getvalue()

        # Verify headers present
        self.assertIn("Reviewer A", content)
        self.assertIn("Cohen's Kappa", content)
        self.assertIn("Percentage Agreement", content)
        self.assertIn("Meets Cochrane Threshold", content)

        # Verify data present
        self.assertIn("John Doe", content)
        self.assertIn("Jane Smith", content)
        self.assertIn("0.850", content)  # Kappa value
        self.assertIn("92.5%", content)  # Agreement percentage
        self.assertIn("Yes", content)  # Meets threshold (>= 0.70)

    def test_generate_irr_metrics_csv_with_dict_data(self):
        """Test IRR metrics CSV generation with dictionary data."""
        irr_data = [
            {
                "reviewer_a": "Reviewer 1",
                "reviewer_b": "Reviewer 2",
                "cohens_kappa": 0.65,
                "percentage_agreement": 85.0,
                "total_comparisons": 50,
                "agreements": 42,
                "disagreements": 8,
                "screening_stage": "full_text",
                "calculated_at": "2025-12-26 10:00:00",
            }
        ]

        output = StringIO()
        self.generator._generate_irr_metrics_csv(output, irr_data)
        content = output.getvalue()

        # Verify data present
        self.assertIn("Reviewer 1", content)
        self.assertIn("Reviewer 2", content)
        self.assertIn("0.650", content)  # Kappa value
        self.assertIn("85.0%", content)
        self.assertIn("No", content)  # Below threshold (< 0.70)

    def test_generate_irr_metrics_csv_empty_list(self):
        """Test IRR metrics CSV generation with empty list."""
        output = StringIO()
        self.generator._generate_irr_metrics_csv(output, [])
        content = output.getvalue()

        # Should have headers but no data rows
        self.assertIn("Reviewer A", content)
        self.assertIn("Cohen's Kappa", content)
        # Should not have summary section
        self.assertNotIn("Average Cohen's Kappa", content)

    def test_generate_irr_metrics_csv_includes_summary(self):
        """Test that IRR summary is included with metrics."""
        mock_metric1 = Mock()
        mock_metric1.cohens_kappa = 0.80
        mock_metric1.percentage_agreement = 90.0
        mock_metric1.total_comparisons = 100
        mock_metric1.agreements = 90
        mock_metric1.disagreements = 10
        mock_metric1.screening_stage = "title_abstract"
        mock_metric1.calculated_at = datetime(2025, 12, 26, 10, 0, 0)
        mock_metric1.reviewer_a = Mock()
        mock_metric1.reviewer_a.get_full_name.return_value = "User A"
        mock_metric1.reviewer_b = Mock()
        mock_metric1.reviewer_b.get_full_name.return_value = "User B"

        mock_metric2 = Mock()
        mock_metric2.cohens_kappa = 0.75
        mock_metric2.percentage_agreement = 87.0
        mock_metric2.total_comparisons = 50
        mock_metric2.agreements = 43
        mock_metric2.disagreements = 7
        mock_metric2.screening_stage = "title_abstract"
        mock_metric2.calculated_at = datetime(2025, 12, 26, 11, 0, 0)
        mock_metric2.reviewer_a = Mock()
        mock_metric2.reviewer_a.get_full_name.return_value = "User C"
        mock_metric2.reviewer_b = Mock()
        mock_metric2.reviewer_b.get_full_name.return_value = "User D"

        output = StringIO()
        self.generator._generate_irr_metrics_csv(output, [mock_metric1, mock_metric2])
        content = output.getvalue()

        # Verify summary section present
        self.assertIn("## IRR Summary", content)
        self.assertIn("Average Cohen's Kappa", content)
        self.assertIn("Total Comparisons", content)
        self.assertIn("All Pairs Meet Cochrane Threshold", content)

    def test_has_irr_data_with_queryset(self):
        """Test _has_irr_data with QuerySet-like object."""
        mock_queryset = Mock()
        mock_queryset.exists.return_value = True
        self.assertTrue(self.generator._has_irr_data(mock_queryset))

        mock_queryset.exists.return_value = False
        self.assertFalse(self.generator._has_irr_data(mock_queryset))

    def test_has_irr_data_with_list(self):
        """Test _has_irr_data with list."""
        self.assertTrue(self.generator._has_irr_data([{"cohens_kappa": 0.8}]))
        self.assertFalse(self.generator._has_irr_data([]))

    def test_has_irr_data_with_none(self):
        """Test _has_irr_data with None."""
        self.assertFalse(self.generator._has_irr_data(None))


class TestAuditTrailCSV(CSVReportGeneratorBaseTest):
    """Tests for decision audit trail CSV generation."""

    def test_generate_audit_trail_csv_with_model_objects(self):
        """Test audit trail CSV with model-like objects."""
        mock_decision = Mock()
        mock_decision.decision_type = "include"
        mock_decision.result_id = uuid4()
        mock_decision.result = Mock()
        mock_decision.result.title = "Test Result"
        mock_decision.result.url = "https://example.com/result"
        mock_decision.reviewer = Mock()
        mock_decision.reviewer.get_full_name.return_value = "John Reviewer"
        mock_decision.created_at = datetime(2025, 12, 26, 10, 0, 0)
        mock_decision.exclusion_reason = None
        mock_decision.notes = "Relevant study"
        mock_decision.version = 1
        mock_decision.is_current = True

        data = {"decisions": [mock_decision]}

        output = StringIO()
        self.generator._generate_audit_trail_csv(output, data)
        content = output.getvalue()

        # Verify headers present
        self.assertIn("Result ID", content)
        self.assertIn("Reviewer", content)
        self.assertIn("Decision", content)
        self.assertIn("Version", content)

        # Verify data present
        self.assertIn("Test Result", content)
        self.assertIn("John Reviewer", content)
        self.assertIn("include", content)
        self.assertIn("Relevant study", content)

    def test_generate_audit_trail_csv_with_dict_data(self):
        """Test audit trail CSV with dictionary data."""
        data = {
            "decisions": [
                {
                    "result_id": str(uuid4()),
                    "result_title": "Sample Result",
                    "result_url": "https://example.com",
                    "reviewer": "Reviewer Name",
                    "decision": "exclude",
                    "decision_date": "2025-12-26 10:00:00",
                    "exclusion_reason": "Not relevant",
                    "notes": "Out of scope",
                    "version": 2,
                    "is_current": True,
                }
            ]
        }

        output = StringIO()
        self.generator._generate_audit_trail_csv(output, data)
        content = output.getvalue()

        # Verify data present
        self.assertIn("Sample Result", content)
        self.assertIn("Reviewer Name", content)
        self.assertIn("exclude", content)
        self.assertIn("Not relevant", content)

    def test_generate_audit_trail_csv_empty_decisions(self):
        """Test audit trail CSV with no decisions."""
        data = {"decisions": []}

        output = StringIO()
        self.generator._generate_audit_trail_csv(output, data)
        content = output.getvalue()

        # Should have headers only
        self.assertIn("Result ID", content)
        lines = [line for line in content.strip().split("\n") if line]
        self.assertEqual(len(lines), 1)  # Only header row


class TestCSVGeneratorIntegration(CSVReportGeneratorBaseTest):
    """Integration tests for CSV generator report type routing."""

    def test_results_summary_includes_irr_when_present(self):
        """Test that results_summary includes IRR metrics when available."""
        self.mock_report.report_type = "results_summary"

        mock_irr = Mock()
        mock_irr.exists.return_value = True

        # Create iterator for the QuerySet mock
        mock_metric = Mock()
        mock_metric.cohens_kappa = 0.85
        mock_metric.percentage_agreement = 90.0
        mock_metric.total_comparisons = 100
        mock_metric.agreements = 90
        mock_metric.disagreements = 10
        mock_metric.screening_stage = "title_abstract"
        mock_metric.calculated_at = datetime(2025, 12, 26, 10, 0, 0)
        mock_metric.reviewer_a = Mock()
        mock_metric.reviewer_a.get_full_name.return_value = "User A"
        mock_metric.reviewer_b = Mock()
        mock_metric.reviewer_b.get_full_name.return_value = "User B"

        mock_irr.__iter__ = Mock(return_value=iter([mock_metric]))

        data = {
            "results": [
                {
                    "id": "1",
                    "query_text": "test query",
                    "title": "Test",
                    "url": "http://test.com",
                    "decision": "include",
                    "exclusion_reason": "",
                    "notes": "",
                }
            ],
            "irr_metrics": mock_irr,
        }

        result = self.generator.generate(self.mock_report, data)
        content = result.decode("utf-8")

        # Should include both results and IRR sections
        self.assertIn("SERP Identifier", content)  # Results header
        self.assertIn("## Inter-Rater Reliability Metrics", content)
        self.assertIn("Cohen's Kappa", content)

    def test_irr_metrics_report_type(self):
        """Test dedicated irr_metrics report type."""
        self.mock_report.report_type = "irr_metrics"

        data = {
            "irr_metrics": [
                {
                    "reviewer_a": "User A",
                    "reviewer_b": "User B",
                    "cohens_kappa": 0.78,
                    "percentage_agreement": 88.0,
                    "total_comparisons": 50,
                    "agreements": 44,
                    "disagreements": 6,
                    "screening_stage": "title_abstract",
                    "calculated_at": "2025-12-26 10:00:00",
                }
            ]
        }

        result = self.generator.generate(self.mock_report, data)
        content = result.decode("utf-8")

        self.assertIn("## Inter-Rater Reliability Metrics", content)
        self.assertIn("User A", content)

    def test_audit_trail_report_type(self):
        """Test dedicated audit_trail report type."""
        self.mock_report.report_type = "audit_trail"

        data = {
            "decisions": [
                {
                    "result_id": str(uuid4()),
                    "result_title": "Test Result",
                    "result_url": "https://example.com",
                    "reviewer": "Reviewer",
                    "decision": "include",
                    "decision_date": "2025-12-26 10:00:00",
                    "exclusion_reason": "",
                    "notes": "",
                    "version": 1,
                    "is_current": True,
                }
            ]
        }

        result = self.generator.generate(self.mock_report, data)
        content = result.decode("utf-8")

        self.assertIn("Result ID", content)
        self.assertIn("Test Result", content)


class TestGetReviewerName(CSVReportGeneratorBaseTest):
    """Tests for _get_reviewer_name helper method."""

    def test_get_reviewer_name_with_full_name(self):
        """Test getting reviewer name when full name exists."""
        mock_user = Mock()
        mock_user.get_full_name.return_value = "John Doe"
        mock_user.username = "jdoe"

        name = self.generator._get_reviewer_name(mock_user)
        self.assertEqual(name, "John Doe")

    def test_get_reviewer_name_falls_back_to_username(self):
        """Test fallback to username when full name is empty."""
        mock_user = Mock()
        mock_user.get_full_name.return_value = ""
        mock_user.username = "jdoe"

        name = self.generator._get_reviewer_name(mock_user)
        self.assertEqual(name, "jdoe")

    def test_get_reviewer_name_with_none(self):
        """Test handling None reviewer (for aggregate metrics)."""
        name = self.generator._get_reviewer_name(None)
        self.assertEqual(name, "All Reviewers")
