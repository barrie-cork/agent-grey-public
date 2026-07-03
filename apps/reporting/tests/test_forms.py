"""
Test cases for reporting app forms.

This module tests form validation, initialization, and
custom cleaning methods for report generation forms.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.reporting.forms import (
    BulkExportForm,
    ReportGenerationForm,
    ReportSchedulingForm,
)
from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession

User = get_user_model()


class ReportGenerationFormTest(TestCase):
    """Test the main report generation form."""

    def setUp(self):
        """Create test user and session."""
        self.user = create_test_user(username_prefix="test@example.com")
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test Description",
            owner=self.user,
            status="completed",
        )

    def test_form_initialization_with_session(self):
        """Test form initializes with session context."""
        form = ReportGenerationForm(session=self.session)

        # Check title is pre-filled
        self.assertEqual(form.fields["title"].initial, "Test Session - Report")

    def test_valid_form_submission(self):
        """Test valid form data."""
        form_data = {
            "report_type": "full_report",
            "export_format": "pdf",
            "title": "My Test Report",
            "include_appendices": True,
            "include_raw_data": False,
        }

        form = ReportGenerationForm(data=form_data, session=self.session)
        self.assertTrue(form.is_valid())

    def test_format_compatibility_validation(self):
        """Test format compatibility validation."""
        # Test invalid format for report type
        form_data = {
            "report_type": "prisma_flow",
            "export_format": "csv",  # CSV not valid for PRISMA flow
            "title": "Invalid Format Report",
        }

        form = ReportGenerationForm(data=form_data, session=self.session)
        self.assertFalse(form.is_valid())
        self.assertIn(
            "CSV format not supported for PRISMA Flow Diagram",
            form.non_field_errors()[0],
        )

    def test_all_format_compatibilities(self):
        """Test all defined format compatibilities."""
        compatibility_tests = [
            # (report_type, valid_formats, invalid_format)
            ("prisma_flow", ["pdf", "json"], "csv"),
            ("full_report", ["pdf"], "csv"),
            ("search_strategy", ["pdf", "json"], "csv"),
            ("results_summary", ["csv", "json"], "pdf"),
            ("bibliography", ["json", "csv"], "pdf"),
        ]

        for report_type, valid_formats, invalid_format in compatibility_tests:
            # Test valid formats
            for valid_format in valid_formats:
                form_data = {
                    "report_type": report_type,
                    "export_format": valid_format,
                    "title": f"Test {report_type} - {valid_format}",
                }
                form = ReportGenerationForm(data=form_data)
                self.assertTrue(
                    form.is_valid(), f"{valid_format} should be valid for {report_type}"
                )

            # Test invalid format
            form_data = {
                "report_type": report_type,
                "export_format": invalid_format,
                "title": f"Test {report_type} - {invalid_format}",
            }
            form = ReportGenerationForm(data=form_data)
            self.assertFalse(
                form.is_valid(), f"{invalid_format} should be invalid for {report_type}"
            )

    def test_raw_data_validation_for_prisma_flow(self):
        """Test that raw data export is not allowed for PRISMA flow."""
        form_data = {
            "report_type": "prisma_flow",
            "export_format": "pdf",
            "title": "PRISMA Flow Report",
            "include_raw_data": True,  # Should cause validation error
        }

        form = ReportGenerationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn(
            "Raw data export is not available for PRISMA Flow Diagram",
            form.non_field_errors()[0],
        )

    def test_required_fields(self):
        """Test that required fields are enforced."""
        form = ReportGenerationForm(data={})
        self.assertFalse(form.is_valid())

        # Check required field errors
        self.assertIn("report_type", form.errors)
        self.assertIn("export_format", form.errors)
        self.assertIn("title", form.errors)

    def test_optional_fields(self):
        """Test that optional fields work correctly."""
        form_data = {
            "report_type": "full_report",
            "export_format": "pdf",
            "title": "Test Report",
            # Omitting include_appendices and include_raw_data
        }

        form = ReportGenerationForm(data=form_data)
        self.assertTrue(form.is_valid())

        # Check defaults
        self.assertFalse(form.cleaned_data["include_appendices"])
        self.assertFalse(form.cleaned_data["include_raw_data"])

    def test_title_max_length(self):
        """Test title field max length validation."""
        form_data = {
            "report_type": "full_report",
            "export_format": "pdf",
            "title": "x" * 201,  # Exceeds max length of 200
        }

        form = ReportGenerationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)


class BulkExportFormTest(TestCase):
    """Test the bulk export form."""

    def test_valid_complete_package(self):
        """Test valid complete package export."""
        form_data = {"export_package": "complete_package", "unified_format": "pdf"}

        form = BulkExportForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_custom_package_requires_selection(self):
        """Test custom package requires report selection."""
        # Test without selection
        form_data = {
            "export_package": "custom",
            "unified_format": "pdf",
            "selected_reports": [],
        }

        form = BulkExportForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("Please select at least one report", form.non_field_errors()[0])

    def test_custom_package_with_selection(self):
        """Test valid custom package with selections."""
        form_data = {
            "export_package": "custom",
            "unified_format": "pdf",
            "selected_reports": ["prisma_flow", "full_report"],
        }

        form = BulkExportForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_non_custom_package_ignores_selection(self):
        """Test non-custom packages don't require selection."""
        form_data = {
            "export_package": "prisma_bundle",
            "unified_format": "pdf",
            "selected_reports": [],  # Empty is OK for non-custom
        }

        form = BulkExportForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_unified_format_choices(self):
        """Test unified format is limited to PDF only."""
        # Valid formats
        for format_choice in ["pdf"]:
            form_data = {
                "export_package": "complete_package",
                "unified_format": format_choice,
            }
            form = BulkExportForm(data=form_data)
            self.assertTrue(form.is_valid())

        # Invalid format
        form = BulkExportForm(
            data={
                "export_package": "complete_package",
                "unified_format": "txt",  # Not in choices
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("unified_format", form.errors)


class ReportSchedulingFormTest(TestCase):
    """Test the report scheduling form."""

    def test_valid_one_time_report(self):
        """Test valid one-time report scheduling."""
        form_data = {
            "frequency": "once",
            "start_date": date.today(),
            "email_notification": True,
            "auto_download": False,
        }

        form = ReportSchedulingForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_valid_recurring_report(self):
        """Test valid recurring report scheduling."""
        form_data = {
            "frequency": "weekly",
            "start_date": date.today(),
            "email_notification": True,
            "auto_download": True,
        }

        form = ReportSchedulingForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_required_fields(self):
        """Test required fields are enforced."""
        form = ReportSchedulingForm(data={})
        self.assertFalse(form.is_valid())

        self.assertIn("frequency", form.errors)
        self.assertIn("start_date", form.errors)

    def test_frequency_choices(self):
        """Test all frequency choices are valid."""
        frequencies = ["once", "weekly", "monthly", "quarterly"]

        for frequency in frequencies:
            form_data = {"frequency": frequency, "start_date": date.today()}
            form = ReportSchedulingForm(data=form_data)
            self.assertTrue(form.is_valid(), f"Frequency '{frequency}' should be valid")

    def test_date_field_format(self):
        """Test date field accepts various formats."""
        form_data = {
            "frequency": "once",
            "start_date": "2025-01-27",  # ISO format
        }

        form = ReportSchedulingForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["start_date"], date(2025, 1, 27))

    def test_optional_notification_fields(self):
        """Test notification fields are optional."""
        form_data = {
            "frequency": "monthly",
            "start_date": date.today(),
            # Omitting email_notification and auto_download
        }

        form = ReportSchedulingForm(data=form_data)
        self.assertTrue(form.is_valid())

        # Check defaults
        self.assertFalse(form.cleaned_data["email_notification"])
        self.assertFalse(form.cleaned_data["auto_download"])


class FormFieldAttributesTest(TestCase):
    """Test form field HTML attributes and widgets."""

    def test_report_generation_form_widgets(self):
        """Test ReportGenerationForm has correct widget attributes."""
        form = ReportGenerationForm()

        # Check radio select for report type
        report_type_widget = form.fields["report_type"].widget
        self.assertEqual(report_type_widget.attrs.get("class"), "form-check-input")

        # Check select for export format
        export_format_widget = form.fields["export_format"].widget
        self.assertEqual(export_format_widget.attrs.get("class"), "form-control")

        # Check text input for title
        title_widget = form.fields["title"].widget
        self.assertEqual(title_widget.attrs.get("class"), "form-control")
        self.assertEqual(title_widget.attrs.get("placeholder"), "Enter report title")

        # Check checkboxes
        appendices_widget = form.fields["include_appendices"].widget
        self.assertEqual(appendices_widget.attrs.get("class"), "form-check-input")

    def test_bulk_export_form_widgets(self):
        """Test BulkExportForm has correct widget attributes."""
        form = BulkExportForm()

        # Check radio select
        package_widget = form.fields["export_package"].widget
        self.assertEqual(package_widget.attrs.get("class"), "form-check-input")

        # Check multiple checkbox
        reports_widget = form.fields["selected_reports"].widget
        self.assertEqual(reports_widget.attrs.get("class"), "form-check-input")

    def test_report_scheduling_form_widgets(self):
        """Test ReportSchedulingForm has correct widget attributes."""
        form = ReportSchedulingForm()

        # Check date input
        date_widget = form.fields["start_date"].widget
        self.assertEqual(date_widget.attrs.get("class"), "form-control")
        # Django 4.2 uses input_type property instead of attrs['type']
        self.assertEqual(date_widget.input_type, "date")


class FormHelpTextTest(TestCase):
    """Test form help text is appropriate."""

    def test_report_generation_help_text(self):
        """Test ReportGenerationForm help text."""
        form = ReportGenerationForm()

        self.assertEqual(
            form.fields["report_type"].help_text,
            "Select the type of report to generate",
        )
        self.assertEqual(
            form.fields["export_format"].help_text,
            "Select the file format for the report",
        )
        self.assertEqual(
            form.fields["title"].help_text, "A descriptive title for your report"
        )
        self.assertEqual(
            form.fields["include_appendices"].help_text,
            "Add supplementary data and detailed breakdowns",
        )
        self.assertEqual(
            form.fields["include_raw_data"].help_text,
            "Export complete search results and metadata",
        )

    def test_bulk_export_help_text(self):
        """Test BulkExportForm help text."""
        form = BulkExportForm()

        self.assertEqual(
            form.fields["selected_reports"].help_text,
            "Choose specific reports to include (for custom packages)",
        )

    def test_report_scheduling_help_text(self):
        """Test ReportSchedulingForm help text."""
        form = ReportSchedulingForm()

        self.assertEqual(
            form.fields["start_date"].help_text, "When to generate the first report"
        )
        self.assertEqual(
            form.fields["email_notification"].help_text,
            "Receive email when reports are ready",
        )
        self.assertEqual(
            form.fields["auto_download"].help_text,
            "Automatically download reports when generated",
        )
