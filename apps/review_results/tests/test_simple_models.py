"""
Tests for simplified review results models.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SimpleReviewDecisionTest(TestCase):
    """Test the simplified review decision model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

    def test_create_simple_decision(self):
        """Test creating a simple review decision."""
        decision = SimpleReviewDecision.objects.create(
            result=self.result,
            session=self.session,
            reviewer=self.user,
            decision="include",
            notes="This looks relevant",
        )

        self.assertEqual(decision.decision, "include")
        self.assertEqual(decision.reviewer, self.user)
        self.assertEqual(decision.notes, "This looks relevant")
        self.assertTrue(decision.result.is_reviewed)

    def test_all_decision_choices(self):
        """Test all 4 decision choices work."""
        choices = ["pending", "include", "exclude", "maybe"]

        for choice in choices:
            with self.subTest(choice=choice):
                result = ProcessedResult.objects.create(
                    session=self.session,
                    title=f"Result for {choice}",
                    url=f"https://example.com/{choice}",
                    snippet=f"Snippet for {choice}",
                )

                # Provide exclusion reason for exclude decision
                kwargs = {
                    "result": result,
                    "session": self.session,
                    "reviewer": self.user,
                    "decision": choice,
                }
                if choice == "exclude":
                    kwargs["exclusion_reason"] = "not_relevant"

                decision = SimpleReviewDecision.objects.create(**kwargs)

                self.assertEqual(decision.decision, choice)
                # Only non-pending decisions mark result as reviewed
                expected_reviewed = choice != "pending"
                self.assertEqual(result.is_reviewed, expected_reviewed)

    def test_exclusion_validation(self):
        """Test that exclusion reason is required when excluding."""
        decision = SimpleReviewDecision(
            result=self.result,
            reviewer=self.user,
            decision="exclude",
            # Missing exclusion_reason
        )

        with self.assertRaises(ValidationError):
            decision.full_clean()

    def test_exclusion_with_reason(self):
        """Test excluding with valid reason."""
        decision = SimpleReviewDecision.objects.create(
            result=self.result,
            session=self.session,
            reviewer=self.user,
            decision="exclude",
            exclusion_reason="not_relevant",
            notes="Not related to our research question",
        )

        self.assertEqual(decision.decision, "exclude")
        self.assertEqual(decision.exclusion_reason, "not_relevant")
        self.assertTrue(decision.result.is_reviewed)

    def test_exclusion_reasons(self):
        """Test all exclusion reason choices."""
        reasons = ["not_relevant", "not_grey_lit", "duplicate", "no_access", "other"]

        for reason in reasons:
            with self.subTest(reason=reason):
                result = ProcessedResult.objects.create(
                    session=self.session,
                    title=f"Result for {reason}",
                    url=f"https://example.com/{reason}",
                    snippet=f"Snippet for {reason}",
                )

                decision = SimpleReviewDecision.objects.create(
                    result=result,
                    session=self.session,
                    reviewer=self.user,
                    decision="exclude",
                    exclusion_reason=reason,
                )

                self.assertEqual(decision.exclusion_reason, reason)

    def test_string_representation(self):
        """Test the string representation of decisions."""
        decision = SimpleReviewDecision.objects.create(
            result=self.result,
            session=self.session,
            reviewer=self.user,
            decision="include",
        )

        expected = f"Include - {self.result.title[:50]}..."
        self.assertEqual(str(decision), expected)
