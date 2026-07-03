"""Tests for manual result addition (Issue #76)."""

import json

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import (
    ReviewConfiguration,
    SearchSession,
    SessionActivity,
)
from apps.review_results.models import ReviewerCompletion
from apps.review_results.services.manual_result_service import ManualResultService


class ManualResultServiceTestCase(TestCase):
    """Tests for ManualResultService."""

    def setUp(self):
        self.user = create_test_user(username_prefix="reviewer")
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org-manual"
        )
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org,
            role="RESEARCH_FELLOW",
            is_active=True,
        )
        self.session = SearchSession.objects.create(
            owner=self.user,
            organisation=self.org,
            title="Test Session",
            status="under_review",
        )

    def _create_wf1_config(self):
        config = ReviewConfiguration.objects.create(
            session=self.session,
            version=1,
            min_reviewers_per_result=1,
            conflict_resolution_method="CONSENSUS",
            created_by=self.user,
        )
        self.session.current_configuration = config
        self.session.save()
        return config

    def _create_wf2_config(self):
        config = ReviewConfiguration.objects.create(
            session=self.session,
            version=1,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            conflict_resolution_method="CONSENSUS",
            created_by=self.user,
        )
        self.session.current_configuration = config
        self.session.save()
        return config

    def test_add_manual_result_wf1(self):
        """Happy path: add a manual result in Workflow #1."""
        self._create_wf1_config()

        result = ManualResultService.add_manual_result(
            session=self.session,
            user=self.user,
            url="https://example.com/guideline",
            title="Test Guideline",
            justification="Found during screening",
        )

        self.assertTrue(result.is_manually_added)
        self.assertEqual(result.manually_added_by, self.user)
        self.assertEqual(result.manual_addition_justification, "Found during screening")
        self.assertEqual(result.review_mode, "SINGLE")
        self.assertEqual(result.min_reviewers_required, 1)
        self.assertEqual(result.processing_status, "success")
        self.assertEqual(result.execution_round, 0)
        self.assertEqual(result.session, self.session)

    def test_add_manual_result_wf2(self):
        """Happy path: add a manual result in Workflow #2."""
        self._create_wf2_config()

        # Create reviewer completions to verify increment
        reviewer2 = create_test_user(username_prefix="reviewer2")
        comp1 = ReviewerCompletion.objects.create(
            session=self.session,
            reviewer=self.user,
            total_results=10,
            reviewed_results=5,
        )
        comp2 = ReviewerCompletion.objects.create(
            session=self.session,
            reviewer=reviewer2,
            total_results=10,
            reviewed_results=3,
        )

        result = ManualResultService.add_manual_result(
            session=self.session,
            user=self.user,
            url="https://example.com/guideline",
            title="Test Guideline",
            justification="Found during screening",
            snippet="A relevant guideline",
        )

        self.assertTrue(result.is_manually_added)
        self.assertEqual(result.review_mode, "DUAL")
        self.assertEqual(result.min_reviewers_required, 2)
        self.assertEqual(result.snippet, "A relevant guideline")

        # Verify completion counts incremented
        comp1.refresh_from_db()
        comp2.refresh_from_db()
        self.assertEqual(comp1.total_results, 11)
        self.assertEqual(comp2.total_results, 11)

    def test_duplicate_url_rejected(self):
        """Duplicate URL within session raises ValueError."""
        self._create_wf1_config()
        ProcessedResult.objects.create(
            session=self.session,
            title="Existing",
            url="https://example.com/duplicate",
        )

        with self.assertRaises(ValueError) as ctx:
            ManualResultService.add_manual_result(
                session=self.session,
                user=self.user,
                url="https://example.com/duplicate",
                title="Duplicate",
                justification="Test",
            )
        self.assertIn("already exists", str(ctx.exception))

    def test_wrong_session_state(self):
        """Session in wrong state raises ValueError."""
        self._create_wf1_config()
        self.session.status = "draft"
        self.session.save()

        with self.assertRaises(ValueError) as ctx:
            ManualResultService.add_manual_result(
                session=self.session,
                user=self.user,
                url="https://example.com/test",
                title="Test",
                justification="Test",
            )
        self.assertIn("state", str(ctx.exception))

    def test_session_activity_logged(self):
        """SessionActivity is created when a manual result is added."""
        self._create_wf1_config()

        ManualResultService.add_manual_result(
            session=self.session,
            user=self.user,
            url="https://example.com/test",
            title="Test Guideline",
            justification="Found during screening",
        )

        activity = SessionActivity.objects.filter(
            session=self.session,
            activity_type="manual_result_added",
        ).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.user, self.user)
        self.assertIn("Test Guideline", activity.description)


class AddManualResultAPITestCase(TestCase):
    """Tests for AddManualResultView API endpoint."""

    def setUp(self):
        self.user = create_test_user(username_prefix="reviewer")
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org-api-manual"
        )
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org,
            role="RESEARCH_FELLOW",
            is_active=True,
        )
        self.session = SearchSession.objects.create(
            owner=self.user,
            organisation=self.org,
            title="Test Session",
            status="under_review",
        )
        config = ReviewConfiguration.objects.create(
            session=self.session,
            version=1,
            min_reviewers_per_result=1,
            conflict_resolution_method="CONSENSUS",
            created_by=self.user,
        )
        self.session.current_configuration = config
        self.session.save()

        self.client.login(username=self.user.username, password="testpass123")
        self.url = reverse("review_results_api:add-manual-result")

    def _post(self, data):
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_happy_path(self):
        """201 on successful manual result creation."""
        response = self._post(
            {
                "session_id": str(self.session.id),
                "url": "https://example.com/guideline",
                "title": "Test Guideline",
                "justification": "Found while browsing",
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Test Guideline")
        self.assertTrue(
            ProcessedResult.objects.filter(
                session=self.session, is_manually_added=True
            ).exists()
        )

    def test_duplicate_url_returns_400(self):
        """400 when URL already exists in session."""
        ProcessedResult.objects.create(
            session=self.session,
            title="Existing",
            url="https://example.com/duplicate",
        )
        response = self._post(
            {
                "session_id": str(self.session.id),
                "url": "https://example.com/duplicate",
                "title": "Duplicate",
                "justification": "Test",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.json()["message"])

    def test_wrong_session_state_returns_409(self):
        """409 when session is not in reviewable state."""
        self.session.status = "draft"
        self.session.save()

        response = self._post(
            {
                "session_id": str(self.session.id),
                "url": "https://example.com/test",
                "title": "Test",
                "justification": "Test",
            }
        )
        self.assertEqual(response.status_code, 409)

    def test_missing_required_fields_returns_400(self):
        """400 when required fields are missing."""
        response = self._post(
            {
                "session_id": str(self.session.id),
                "url": "https://example.com/test",
                # title and justification missing
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_returns_403(self):
        """403 when user is not authenticated."""
        self.client.logout()
        response = self._post(
            {
                "session_id": str(self.session.id),
                "url": "https://example.com/test",
                "title": "Test",
                "justification": "Test",
            }
        )
        self.assertEqual(response.status_code, 403)

    def test_non_member_returns_404(self):
        """404 when user is not a member of the session's organisation."""
        outsider = create_test_user(username_prefix="outsider")
        self.client.login(username=outsider.username, password="testpass123")

        response = self._post(
            {
                "session_id": str(self.session.id),
                "url": "https://example.com/test",
                "title": "Test",
                "justification": "Test",
            }
        )
        self.assertEqual(response.status_code, 404)


class PrismaManualResultTestCase(TestCase):
    """Test that PRISMA reporting counts manual results."""

    def setUp(self):
        self.user = create_test_user(username_prefix="reviewer")
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org-prisma-manual"
        )
        self.session = SearchSession.objects.create(
            owner=self.user,
            organisation=self.org,
            title="Test Session",
            status="under_review",
        )

    def test_other_sources_counts_manual_results(self):
        """PRISMA identification data includes manual results in other_sources."""
        from apps.reporting.services.prisma_reporting_service import (
            PrismaReportingService,
        )

        # Create a manual result
        ProcessedResult.objects.create(
            session=self.session,
            title="Manual Guideline",
            url="https://example.com/manual",
            is_manually_added=True,
            manually_added_by=self.user,
            processing_status="success",
        )
        # Create a normal result
        ProcessedResult.objects.create(
            session=self.session,
            title="Normal Result",
            url="https://example.com/normal",
            is_manually_added=False,
            processing_status="success",
        )

        service = PrismaReportingService()
        data = service._gather_identification_data(str(self.session.id))

        self.assertEqual(data["other_sources"], 1)
        self.assertGreaterEqual(data["total"], 1)
