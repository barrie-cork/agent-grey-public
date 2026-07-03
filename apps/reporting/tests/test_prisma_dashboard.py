"""
Tests for PRISMA dashboard integration: view context, form rendering, and download buttons.

Covers:
- Dashboard renders with other methods form section
- Canvas data uses real query-based counts (database flow structure)
- Download buttons render correctly (database flow + disabled full PRISMA)
- Other methods form pre-populated with auto-populated or saved data
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.utils import create_test_user
from apps.reporting.forms import PrismaOtherMethodsForm
from apps.review_manager.models import SearchSession


PRISMA_FLOW_PATH = (
    "apps.reporting.services.prisma_reporting_service"
    ".PrismaReportingService.generate_prisma_flow_data"
)

AUTO_POP_PATH = (
    "apps.reporting.services.prisma_reporting_service"
    ".PrismaReportingService.auto_populate_other_methods"
)

EXCLUSION_PATH = (
    "apps.reporting.services.prisma_reporting_service"
    ".PrismaReportingService.get_exclusion_reasons"
)

MOCK_FLOW_DATA = {
    "raw_search_results": 100,
    "duplicates_removed": 10,
    "processed_results": 90,
    "results_included": 20,
    "results_excluded": 30,
    "results_maybe": 5,
    "results_pending": 35,
    "identification": {
        "database": 100,
        "other_sources": 3,
        "total": 103,
        "websites": 60,
        "organizations": 40,
        "citation_searching": 0,
    },
    "screening": {
        "records_screened": 90,
        "duplicates_removed": 10,
        "excluded": 0,
    },
    "retrieval": {
        "reports_sought": 90,
        "reports_not_retrieved": 5,
        "reports_retrieved": 85,
        "failure_reasons": {},
    },
    "eligibility": {
        "reports_assessed": 85,
        "full_text_assessed": 90,
        "excluded": 30,
        "exclusion_reasons": {"Not relevant": 20, "Duplicate": 10},
    },
    "included": {
        "studies_included": 20,
        "qualitative": 0,
        "quantitative": 0,
        "total": 20,
    },
    "summary": {"retrieval_rate": 94.4},
}

MOCK_AUTO_DATA = {
    "websites": 10,
    "organisations": 5,
    "other_sources": 2,
    "citation_searching": 0,
    "reports_sought": 17,
    "reports_not_retrieved": 3,
    "reports_assessed": 14,
    "reports_excluded": 4,
    "exclusion_reasons": {"Not relevant": 3, "Duplicate": 1},
}

MOCK_EXCLUSION_REASONS = {"Not relevant": 3, "Duplicate": 1}


class PrismaDashboardViewTest(TestCase):
    """Test ReportDashboardView context and rendering for PRISMA."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Dashboard Test",
            owner=self.user,
            status="completed",
        )
        self.url = reverse(
            "reporting:dashboard",
            kwargs={"session_id": self.session.id},
        )
        self.client.force_login(self.user)

    @patch(EXCLUSION_PATH, return_value=MOCK_EXCLUSION_REASONS)
    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    @patch(PRISMA_FLOW_PATH, return_value=MOCK_FLOW_DATA)
    def test_dashboard_renders_with_form_section(self, mock_flow, mock_auto, mock_excl):
        """Dashboard page includes the other methods form section."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-testid="other-methods-section"')
        self.assertContains(response, 'data-testid="other-methods-form"')
        self.assertContains(response, 'data-testid="save-other-methods-btn"')

    @patch(EXCLUSION_PATH, return_value=MOCK_EXCLUSION_REASONS)
    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    @patch(PRISMA_FLOW_PATH, return_value=MOCK_FLOW_DATA)
    def test_context_has_other_methods_form(self, mock_flow, mock_auto, mock_excl):
        """Context includes other_methods_form, has_other_methods, etc."""
        response = self.client.get(self.url)
        self.assertIsInstance(
            response.context["other_methods_form"], PrismaOtherMethodsForm
        )
        self.assertFalse(response.context["has_other_methods"])
        self.assertIsInstance(response.context["other_methods_auto"], dict)
        self.assertIsInstance(response.context["exclusion_reasons"], dict)

    @patch(EXCLUSION_PATH, return_value=MOCK_EXCLUSION_REASONS)
    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    @patch(PRISMA_FLOW_PATH, return_value=MOCK_FLOW_DATA)
    def test_has_other_methods_true_when_saved(self, mock_flow, mock_auto, mock_excl):
        """has_other_methods is True when session has saved prisma_other_methods."""
        self.session.prisma_other_methods = {"websites": 10}
        self.session.save(update_fields=["prisma_other_methods"])

        response = self.client.get(self.url)
        self.assertTrue(response.context["has_other_methods"])

    @patch(EXCLUSION_PATH, return_value=MOCK_EXCLUSION_REASONS)
    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    @patch(PRISMA_FLOW_PATH, return_value=MOCK_FLOW_DATA)
    def test_canvas_data_uses_database_flow_structure(
        self, mock_flow, mock_auto, mock_excl
    ):
        """Template inline JS uses database flow keys for Canvas data."""
        response = self.client.get(self.url)
        content = response.content.decode()
        # Inline JS passes database flow data structure to Canvas
        self.assertIn("databases:", content)
        self.assertIn("duplicates_removed:", content)
        self.assertIn("records_screened:", content)
        self.assertIn("records_excluded:", content)
        # External JS file referenced (contains "databases and registers" header)
        self.assertIn("prisma2020.js", content)

    @patch(EXCLUSION_PATH, return_value=MOCK_EXCLUSION_REASONS)
    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    @patch(PRISMA_FLOW_PATH, return_value=MOCK_FLOW_DATA)
    def test_download_buttons_render_correctly(self, mock_flow, mock_auto, mock_excl):
        """Export buttons include database flow PNG/PDF and disabled full PRISMA."""
        response = self.client.get(self.url)
        self.assertContains(response, 'data-testid="export-db-flow-png"')
        self.assertContains(response, 'data-testid="export-db-flow-pdf"')
        self.assertContains(response, 'data-testid="export-full-prisma"')
        self.assertContains(response, "Download Database Flow (PNG)")
        self.assertContains(response, "Download Database Flow (PDF)")
        self.assertContains(response, "Download Full PRISMA Diagram")

    @patch(EXCLUSION_PATH, return_value=MOCK_EXCLUSION_REASONS)
    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    @patch(PRISMA_FLOW_PATH, return_value=MOCK_FLOW_DATA)
    def test_exclusion_reasons_rendered(self, mock_flow, mock_auto, mock_excl):
        """Exclusion reasons displayed in the other methods form section."""
        response = self.client.get(self.url)
        self.assertContains(response, "Exclusion Reasons (auto-populated)")
        self.assertContains(response, "Not relevant: 3")
        self.assertContains(response, "Duplicate: 1")

    @patch(EXCLUSION_PATH, return_value=MOCK_EXCLUSION_REASONS)
    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    @patch(PRISMA_FLOW_PATH, return_value=MOCK_FLOW_DATA)
    def test_form_prepopulated_with_auto_data(self, mock_flow, mock_auto, mock_excl):
        """Form initial values come from auto-populated data."""
        response = self.client.get(self.url)
        form = response.context["other_methods_form"]
        self.assertEqual(form.initial.get("websites"), 10)
        self.assertEqual(form.initial.get("organisations"), 5)

    @patch(EXCLUSION_PATH, return_value=MOCK_EXCLUSION_REASONS)
    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    @patch(PRISMA_FLOW_PATH, return_value=MOCK_FLOW_DATA)
    def test_saved_overrides_auto_populated(self, mock_flow, mock_auto, mock_excl):
        """Saved values override auto-populated defaults in form initial."""
        self.session.prisma_other_methods = {"websites": 99}
        self.session.save(update_fields=["prisma_other_methods"])

        response = self.client.get(self.url)
        form = response.context["other_methods_form"]
        self.assertEqual(form.initial.get("websites"), 99)
        # Non-overridden field still uses auto value
        self.assertEqual(form.initial.get("organisations"), 5)
