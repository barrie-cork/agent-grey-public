"""
Tests for review decision metrics instrumentation.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from prometheus_client import REGISTRY

from apps.core.metrics.enums import ReviewDecision
from apps.core.metrics.review_metrics import (
    record_review_decision,
    update_review_velocity,
)
from apps.core.tests.utils import create_test_user
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision

User = get_user_model()


class ReviewMetricsTest(TestCase):
    """Test cases for review metrics."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

    def test_record_review_decision_include(self):
        """Test recording include decision."""
        before = REGISTRY.get_sample_value(
            "agent_grey_review_decisions_total",
            {"decision": ReviewDecision.INCLUDE.value},
        )
        if before is None:
            before = 0

        record_review_decision(ReviewDecision.INCLUDE)

        after = REGISTRY.get_sample_value(
            "agent_grey_review_decisions_total",
            {"decision": ReviewDecision.INCLUDE.value},
        )

        self.assertEqual(after - before, 1.0)

    def test_record_review_decision_exclude(self):
        """Test recording exclude decision."""
        before = REGISTRY.get_sample_value(
            "agent_grey_review_decisions_total",
            {"decision": ReviewDecision.EXCLUDE.value},
        )
        if before is None:
            before = 0

        record_review_decision(ReviewDecision.EXCLUDE)

        after = REGISTRY.get_sample_value(
            "agent_grey_review_decisions_total",
            {"decision": ReviewDecision.EXCLUDE.value},
        )

        self.assertEqual(after - before, 1.0)

    def test_update_review_velocity_calculation(self):
        """Test review velocity is calculated correctly."""
        # Create a processed result
        _result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com",
            snippet="Test snippet",
        )

        # Create 3 different results with decisions in last hour
        for i in range(3):
            test_result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/{i}",
                snippet="Test snippet",
            )
            decision = SimpleReviewDecision.objects.create(
                session=self.session,
                result=test_result,
                decision="include",
                reviewer=self.user,
            )
            # Update reviewed_at to be within last hour
            decision.reviewed_at = timezone.now() - timedelta(minutes=30)
            decision.save()

        # Update velocity
        update_review_velocity()

        # Check gauge value
        velocity = REGISTRY.get_sample_value("agent_grey_review_velocity_per_hour")

        # Should be at least 3 decisions in last hour
        self.assertIsNotNone(velocity)
        self.assertGreaterEqual(velocity, 3.0)

    def test_update_review_velocity_zero_when_no_recent_decisions(self):
        """Test velocity is zero when no recent decisions."""
        # Create old decision (2 hours ago)
        result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com",
            snippet="Test snippet",
        )
        decision = SimpleReviewDecision.objects.create(
            session=self.session, result=result, decision="include", reviewer=self.user
        )
        # Set reviewed_at to 2 hours ago
        decision.reviewed_at = timezone.now() - timedelta(hours=2)
        decision.save()

        # Update velocity
        update_review_velocity()

        # Check gauge value
        velocity = REGISTRY.get_sample_value("agent_grey_review_velocity_per_hour")

        # Should be 0 (no decisions in last hour)
        self.assertEqual(velocity, 0.0)

    def test_record_review_decision_handles_errors(self):
        """Test decision recording doesn't raise on errors."""
        # Should not raise even with mock error
        try:
            record_review_decision(ReviewDecision.UNDECIDED)
        except Exception as e:
            self.fail(f"record_review_decision raised {e}")
