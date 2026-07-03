"""
Tests for reporting models.

Tests for ExportReport and related models including
report generation and export functionality.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession

from ..models import ExportReport
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ExportReportModelTests(TestCase):
    """Test cases for ExportReport model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

    def test_export_report_creation(self):
        """Test creating an export report."""
        report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            report_type="prisma_flow",
            export_format="pdf",
            title="PRISMA Flow Diagram",
        )

        self.assertEqual(report.session, self.session)
        self.assertEqual(report.generated_by, self.user)
        self.assertEqual(report.report_type, "prisma_flow")
        self.assertEqual(report.export_format, "pdf")

    def test_maybe_results_field_default(self):
        """Test that maybe_results field defaults to 0."""
        report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            report_type="prisma_flow",
            export_format="pdf",
            title="Test Report",
            file_size_bytes=0,
        )

        self.assertEqual(report.maybe_results, 0)
        self.assertEqual(report.included_results, 0)
        self.assertEqual(report.excluded_results, 0)
        self.assertEqual(report.total_results, 0)

    def test_maybe_results_field_update(self):
        """Test updating maybe_results field."""
        report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            report_type="data_export",
            export_format="csv",
            title="Results Export",
            file_size_bytes=0,
        )

        # Update statistics including maybe results
        report.total_results = 10
        report.included_results = 3
        report.excluded_results = 2
        report.maybe_results = 5
        report.save()

        # Reload from database
        report.refresh_from_db()

        self.assertEqual(report.total_results, 10)
        self.assertEqual(report.included_results, 3)
        self.assertEqual(report.excluded_results, 2)
        self.assertEqual(report.maybe_results, 5)

    def test_statistics_calculation_with_maybe(self):
        """Test that statistics correctly include maybe results."""
        report = ExportReport.objects.create(
            session=self.session,
            generated_by=self.user,
            report_type="data_export",
            export_format="json",
            title="Statistics Report",
            file_size_bytes=0,
            total_results=20,
            included_results=8,
            excluded_results=7,
            maybe_results=5,
        )

        # Verify all statistics are stored correctly
        self.assertEqual(report.total_results, 20)
        self.assertEqual(report.included_results, 8)
        self.assertEqual(report.excluded_results, 7)
        self.assertEqual(report.maybe_results, 5)

        # Verify the sum matches total
        review_sum = (
            report.included_results + report.excluded_results + report.maybe_results
        )
        self.assertEqual(review_sum, report.total_results)

    def test_maybe_results_field_help_text(self):
        """Test that maybe_results field has proper help text."""
        field = ExportReport._meta.get_field("maybe_results")
        self.assertIn("maybe", field.help_text.lower())
