"""
Unit tests for OrganisationService.

Tests all public methods of the service including health checks,
default org management, metrics, and quota checking.
"""

from django.test import TestCase

from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.organisation.services.organisation_service import OrganisationService


class TestOrganisationService(DisablePersonalOrgSignalMixin, TestCase):
    """Tests for OrganisationService methods."""

    def setUp(self):
        self.service = OrganisationService()
        self.user = create_test_user(username_prefix="org_svc")
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org-svc"
        )
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )

    def test_health_check_returns_true(self):
        """Health check returns True when database is accessible."""
        self.assertTrue(self.service.health_check())

    def test_get_or_create_default_org_creates_new(self):
        """Creates default organisation when none exists."""
        # Ensure no default org exists
        Organisation.objects.filter(slug="default").delete()

        org = self.service.get_or_create_default_org()

        self.assertEqual(org.slug, "default")
        self.assertEqual(org.name, "Default Organisation")
        self.assertEqual(org.default_min_reviewers, 1)
        self.assertFalse(org.require_dual_review)

    def test_get_or_create_default_org_returns_existing(self):
        """Returns existing default organisation (idempotent)."""
        org1 = self.service.get_or_create_default_org()
        org2 = self.service.get_or_create_default_org()

        self.assertEqual(org1.id, org2.id)
        self.assertEqual(Organisation.objects.filter(slug="default").count(), 1)

    def test_get_org_metrics_returns_complete_structure(self):
        """Metrics dict has all expected keys."""
        metrics = self.service.get_org_metrics(self.org)

        self.assertEqual(metrics["organisation_id"], str(self.org.id))
        self.assertEqual(metrics["organisation_name"], self.org.name)
        self.assertIn("total_reviews", metrics)
        self.assertIn("active_reviews", metrics)
        self.assertIn("status_breakdown", metrics)
        self.assertIn("total_members", metrics)
        self.assertIn("role_breakdown", metrics)
        self.assertIn("quota_status", metrics)
        self.assertIn("average_completion_hours", metrics)
        self.assertIn("calculated_at", metrics)

    def test_get_org_metrics_with_active_reviews(self):
        """Metrics correctly count reviews in various states."""
        from apps.review_manager.models import SearchSession

        # Create sessions in different states
        SearchSession.objects.create(
            title="Draft", owner=self.user, organisation=self.org, status="draft"
        )
        SearchSession.objects.create(
            title="Under Review",
            owner=self.user,
            organisation=self.org,
            status="under_review",
        )
        SearchSession.objects.create(
            title="Executing",
            owner=self.user,
            organisation=self.org,
            status="executing",
        )

        # Clear cache to get fresh metrics
        self.service.invalidate_cache()

        metrics = self.service.get_org_metrics(self.org)

        self.assertEqual(metrics["total_reviews"], 3)
        self.assertEqual(metrics["active_reviews"], 2)  # under_review + executing

    def test_get_org_metrics_caches_result(self):
        """Second call returns cached result without re-querying."""
        metrics1 = self.service.get_org_metrics(self.org)
        metrics2 = self.service.get_org_metrics(self.org)

        # Same calculated_at means cache was used
        self.assertEqual(metrics1["calculated_at"], metrics2["calculated_at"])

    def test_check_review_quota_under_limit(self):
        """Returns (True, None) when under review quota."""
        self.org.max_active_reviews = 5
        self.org.save()

        can_create, error = self.service.check_review_quota(self.org)

        self.assertTrue(can_create)
        self.assertIsNone(error)

    def test_check_review_quota_at_limit(self):
        """Returns (False, message) when at review quota."""
        from apps.review_manager.models import SearchSession

        self.org.max_active_reviews = 1
        self.org.save()

        SearchSession.objects.create(
            title="Active",
            owner=self.user,
            organisation=self.org,
            status="under_review",
        )

        can_create, error = self.service.check_review_quota(self.org)

        self.assertFalse(can_create)
        self.assertIn("quota reached", error)

    def test_check_review_quota_unlimited(self):
        """Returns (True, None) when no quota is set (max_active_reviews=None)."""
        self.org.max_active_reviews = None
        self.org.save()

        can_create, error = self.service.check_review_quota(self.org)

        self.assertTrue(can_create)
        self.assertIsNone(error)

    def test_check_user_quota_under_limit(self):
        """Returns (True, None) when under user quota."""
        self.org.max_users = 10
        self.org.save()

        can_add, error = self.service.check_user_quota(self.org)

        self.assertTrue(can_add)
        self.assertIsNone(error)

    def test_check_user_quota_at_limit(self):
        """Returns (False, message) when at user quota."""
        self.org.max_users = 1  # Already have 1 member
        self.org.save()

        can_add, error = self.service.check_user_quota(self.org)

        self.assertFalse(can_add)
        self.assertIn("quota reached", error)

    def test_check_user_quota_unlimited(self):
        """Returns (True, None) when no quota is set (max_users=None)."""
        self.org.max_users = None
        self.org.save()

        can_add, error = self.service.check_user_quota(self.org)

        self.assertTrue(can_add)
        self.assertIsNone(error)

    def test_get_quality_metrics_returns_placeholder(self):
        """Quality metrics returns placeholder structure (Phase 2 pending)."""
        metrics = self.service.get_quality_metrics(self.org)

        self.assertEqual(metrics["organisation_id"], str(self.org.id))
        self.assertIsNone(metrics["average_irr"])
        self.assertEqual(metrics["reviews_below_threshold"], 0)
        self.assertEqual(metrics["pending_conflicts"], 0)
        self.assertEqual(metrics["total_results_reviewed"], 0)
        self.assertIn("note", metrics)
