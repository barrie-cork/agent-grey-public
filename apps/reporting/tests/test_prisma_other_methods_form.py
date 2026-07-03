"""
Tests for PrismaOtherMethodsForm and PrismaOtherMethodsSaveView.

Covers:
- Form validation: valid data, arithmetic mismatch warnings, negative values
- Save view: POST saves correctly, GET returns JSON, ownership enforced
- Integration: saved data overrides auto-populated defaults
"""

import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.utils import create_test_user
from apps.reporting.forms import PrismaOtherMethodsForm
from apps.review_manager.models import SearchSession


class PrismaOtherMethodsFormTest(TestCase):
    """Test PrismaOtherMethodsForm validation."""

    def test_valid_data(self):
        """Consistent arithmetic data passes with no warnings."""
        form = PrismaOtherMethodsForm(
            data={
                "websites": 10,
                "organisations": 5,
                "citation_searching": 3,
                "other_sources": 2,
                "reports_sought": 20,
                "reports_not_retrieved": 5,
                "reports_assessed": 15,
                "reports_excluded": 3,
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.warnings, [])

    def test_all_fields_optional(self):
        """All fields are optional -- empty form is valid."""
        form = PrismaOtherMethodsForm(data={})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.warnings, [])

    def test_arithmetic_mismatch_warning(self):
        """assessed != sought - not_retrieved produces a warning, not an error."""
        form = PrismaOtherMethodsForm(
            data={
                "reports_sought": 20,
                "reports_not_retrieved": 5,
                "reports_assessed": 10,  # should be 15
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.warnings), 1)
        self.assertIn("does not equal", form.warnings[0])

    def test_excluded_exceeds_assessed_warning(self):
        """excluded > assessed produces a warning, not an error."""
        form = PrismaOtherMethodsForm(
            data={
                "reports_assessed": 10,
                "reports_excluded": 15,
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.warnings), 1)
        self.assertIn("exceeds", form.warnings[0])

    def test_negative_values_rejected(self):
        """Negative values are hard errors (min_value=0)."""
        form = PrismaOtherMethodsForm(data={"websites": -1})
        self.assertFalse(form.is_valid())
        self.assertIn("websites", form.errors)

    def test_multiple_warnings(self):
        """Both arithmetic checks can fire simultaneously."""
        form = PrismaOtherMethodsForm(
            data={
                "reports_sought": 10,
                "reports_not_retrieved": 2,
                "reports_assessed": 5,  # should be 8
                "reports_excluded": 9,  # exceeds 5
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.warnings), 2)

    def test_consistent_arithmetic_no_warning(self):
        """Exact match: assessed == sought - not_retrieved, no warning."""
        form = PrismaOtherMethodsForm(
            data={
                "reports_sought": 30,
                "reports_not_retrieved": 10,
                "reports_assessed": 20,
                "reports_excluded": 5,
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.warnings, [])


AUTO_POP_PATH = (
    "apps.reporting.services.prisma_reporting_service"
    ".PrismaReportingService.auto_populate_other_methods"
)

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


class PrismaOtherMethodsSaveViewTest(TestCase):
    """Test PrismaOtherMethodsSaveView GET and POST."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="PRISMA Form Test",
            owner=self.user,
            status="completed",
        )
        self.url = reverse(
            "reporting:prisma_other_methods_save",
            kwargs={"session_id": self.session.id},
        )
        self.client.force_login(self.user)

    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    def test_get_returns_merged_json(self, mock_auto):
        """GET returns auto-populated data merged with saved overrides."""
        self.session.prisma_other_methods = {"websites": 99}
        self.session.save(update_fields=["prisma_other_methods"])

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Saved override takes precedence
        self.assertEqual(data["websites"], 99)
        # Auto-populated value used when not overridden
        self.assertEqual(data["organisations"], 5)
        # exclusion_reasons always from auto-populate
        self.assertEqual(data["exclusion_reasons"], {"Not relevant": 3, "Duplicate": 1})

    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    def test_get_without_saved_data(self, mock_auto):
        """GET returns pure auto-populated data when nothing is saved."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["websites"], 10)

    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    def test_post_saves_data(self, mock_auto):
        """POST saves form data to session.prisma_other_methods."""
        response = self.client.post(
            self.url,
            data={
                "websites": 25,
                "organisations": 10,
                "reports_sought": 35,
                "reports_not_retrieved": 5,
                "reports_assessed": 30,
                "reports_excluded": 8,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "saved")

        self.session.refresh_from_db()
        self.assertEqual(self.session.prisma_other_methods["websites"], 25)
        # exclusion_reasons preserved from auto-populate
        self.assertEqual(
            self.session.prisma_other_methods["exclusion_reasons"],
            {"Not relevant": 3, "Duplicate": 1},
        )

    @patch(AUTO_POP_PATH, return_value=MOCK_AUTO_DATA)
    def test_post_returns_warnings(self, mock_auto):
        """POST returns arithmetic warnings but still saves."""
        response = self.client.post(
            self.url,
            data={
                "reports_sought": 20,
                "reports_not_retrieved": 5,
                "reports_assessed": 10,  # mismatch
            },
        )
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "saved")
        self.assertTrue(len(body["warnings"]) > 0)

    def test_post_invalid_data_returns_400(self):
        """POST with negative values returns 400."""
        response = self.client.post(self.url, data={"websites": -5})
        self.assertEqual(response.status_code, 400)
        body = json.loads(response.content)
        self.assertIn("errors", body)

    def test_ownership_enforced(self):
        """Other users cannot access the endpoint."""
        other_user = create_test_user(username_prefix="other")
        self.client.force_login(other_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_redirects(self):
        """Unauthenticated requests redirect to login."""
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)


class PrismaOtherMethodsIntegrationTest(TestCase):
    """Test that saved data overrides auto-populated defaults in full flow."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Integration Test",
            owner=self.user,
            status="completed",
        )

    def test_saved_data_overrides_in_generate_full_prisma(self):
        """generate_full_prisma_flow_data uses saved overrides instead of auto-populate."""
        from apps.reporting.services.prisma_reporting_service import (
            PrismaReportingService,
        )

        self.session.prisma_other_methods = {
            "websites": 99,
            "organisations": 50,
            "other_sources": 2,
            "citation_searching": 0,
            "reports_sought": 151,
            "reports_not_retrieved": 10,
            "reports_assessed": 141,
            "reports_excluded": 20,
            "exclusion_reasons": {"Irrelevant": 20},
        }
        self.session.save(update_fields=["prisma_other_methods"])

        service = PrismaReportingService()
        stub = {"database": 0, "other": 0, "organizations": 0, "total": 0}
        with (
            patch.object(service, "_gather_identification_data", return_value=stub),
            patch.object(
                service,
                "_gather_screening_data",
                return_value={
                    "duplicates_removed": 0,
                    "records_screened": 0,
                    "excluded": 0,
                },
            ),
            patch.object(
                service,
                "get_retrieval_statistics",
                return_value={
                    "reports_sought_for_retrieval": 0,
                    "reports_not_retrieved": 0,
                    "reports_assessed_for_eligibility": 0,
                },
            ),
            patch.object(
                service, "_gather_eligibility_data", return_value={"excluded": 0}
            ),
            patch.object(
                service,
                "_gather_included_data",
                return_value={"studies_included": 0, "total": 0},
            ),
            patch.object(service, "get_exclusion_reasons", return_value={}),
        ):
            result = service.generate_full_prisma_flow_data(str(self.session.id))

        # Saved data used (not auto-populated)
        self.assertTrue(result["session_metadata"]["has_user_overrides"])
        self.assertEqual(result["other_methods_flow"]["identification"]["websites"], 99)
        self.assertEqual(
            result["other_methods_flow"]["identification"]["organisations"], 50
        )
