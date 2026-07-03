"""Tests for ReviewConfiguration SLA fields (R01)."""

from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation
from apps.review_manager.models import ReviewConfiguration, SearchSession


class TestReviewConfigurationSlaFields(TestCase):
    """Tests for SLA fields on ReviewConfiguration (R01)."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Test Org", slug="test-org-rc-sla")
        self.user = create_test_user(username_prefix="rc_sla", email="rc_sla@test.com")
        self.session = SearchSession.objects.create(
            organisation=self.org,
            title="SLA Config Test",
            owner=self.user,
            status="under_review",
        )

    def test_default_discussion_sla_hours_R01(self):
        """discussion_sla_hours defaults to 72."""
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            version=1,
            organisation=self.org,
            created_by=self.user,
        )
        self.assertEqual(config.discussion_sla_hours, 72)

    def test_default_revote_sla_hours_R01(self):
        """revote_sla_hours defaults to 24."""
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            version=1,
            organisation=self.org,
            created_by=self.user,
        )
        self.assertEqual(config.revote_sla_hours, 24)

    def test_default_arbitration_sla_hours_R01(self):
        """arbitration_sla_hours defaults to 48."""
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            version=1,
            organisation=self.org,
            created_by=self.user,
        )
        self.assertEqual(config.arbitration_sla_hours, 48)

    def test_sla_fields_accept_custom_values_R01(self):
        """SLA fields should accept custom values."""
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            version=1,
            organisation=self.org,
            created_by=self.user,
            discussion_sla_hours=120,
            revote_sla_hours=48,
            arbitration_sla_hours=96,
        )
        config.refresh_from_db()
        self.assertEqual(config.discussion_sla_hours, 120)
        self.assertEqual(config.revote_sla_hours, 48)
        self.assertEqual(config.arbitration_sla_hours, 96)
