"""
Tests for ProcessedResultSerializer.my_decision field.

Verifies that the serializer returns the requesting user's existing
decision for both Workflow #1 (SimpleReviewDecision) and
Workflow #2 (ReviewerDecision).
"""

from django.test import RequestFactory, TestCase

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import ReviewerDecision, SimpleReviewDecision
from apps.review_results.serializers import ProcessedResultSerializer


class TestProcessedResultSerializerMyDecision(TestCase):
    """Test my_decision field on ProcessedResultSerializer."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = create_test_user(username_prefix="reviewer1")
        self.user2 = create_test_user(username_prefix="reviewer2")

        self.org = Organisation.objects.create(
            name="Test Organisation",
        )

        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            organisation=self.org,
            status="under_review",
        )

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

    def _serialize(self, user):
        """Serialize self.result with a fake request for the given user."""
        request = self.factory.get("/fake/")
        request.user = user
        serializer = ProcessedResultSerializer(
            self.result, context={"request": request}
        )
        return serializer.data

    def test_my_decision_returns_null_when_no_decision(self):
        """R01: Returns null when user has not made a decision."""
        data = self._serialize(self.user)
        self.assertIsNone(data["my_decision"])

    def test_my_decision_returns_include_for_workflow1(self):
        """R01: Returns 'include' for Workflow #1 SimpleReviewDecision."""
        SimpleReviewDecision.objects.create(
            result=self.result,
            session=self.session,
            reviewer=self.user,
            decision="include",
        )
        data = self._serialize(self.user)
        self.assertEqual(data["my_decision"], "include")

    def test_my_decision_returns_exclude_for_workflow1(self):
        """R01: Returns 'exclude' for Workflow #1 SimpleReviewDecision."""
        SimpleReviewDecision.objects.create(
            result=self.result,
            session=self.session,
            reviewer=self.user,
            decision="exclude",
            exclusion_reason="not_relevant",
        )
        data = self._serialize(self.user)
        self.assertEqual(data["my_decision"], "exclude")

    def test_my_decision_returns_null_for_pending_workflow1(self):
        """R01: Returns null when decision is 'pending' in Workflow #1."""
        SimpleReviewDecision.objects.create(
            result=self.result,
            session=self.session,
            reviewer=self.user,
            decision="pending",
        )
        data = self._serialize(self.user)
        self.assertIsNone(data["my_decision"])

    def _setup_workflow2(self):
        """Configure session for Workflow #2."""
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            created_by=self.user,
        )
        self.session.current_configuration = config
        self.session.save()

    def test_my_decision_returns_include_for_workflow2(self):
        """R01: Returns 'include' (lowercase) for Workflow #2 ReviewerDecision."""
        self._setup_workflow2()
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user,
            organisation=self.org,
            decision="INCLUDE",
            confidence_level=2,
        )
        data = self._serialize(self.user)
        self.assertEqual(data["my_decision"], "include")

    def test_my_decision_returns_exclude_for_workflow2(self):
        """R01: Returns 'exclude' (lowercase) for Workflow #2 ReviewerDecision."""
        self._setup_workflow2()
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user,
            organisation=self.org,
            decision="EXCLUDE",
            exclusion_reason="wrong_population",
            confidence_level=2,
        )
        data = self._serialize(self.user)
        self.assertEqual(data["my_decision"], "exclude")

    def test_my_decision_only_returns_current_user_decision(self):
        """R01: Only returns the requesting user's decision, not other users'."""
        self._setup_workflow2()

        # user2 has a decision, user does not
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
            organisation=self.org,
            decision="INCLUDE",
            confidence_level=2,
        )
        data = self._serialize(self.user)
        self.assertIsNone(data["my_decision"])

    def test_my_decision_ignores_revote_decisions(self):
        """R01: Ignores revote decisions in Workflow #2."""
        self._setup_workflow2()

        # Original decision
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user,
            organisation=self.org,
            decision="INCLUDE",
            confidence_level=2,
            is_revote=False,
        )
        # Revote decision (should be ignored)
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user,
            organisation=self.org,
            decision="EXCLUDE",
            exclusion_reason="wrong_population",
            confidence_level=3,
            is_revote=True,
        )
        data = self._serialize(self.user)
        self.assertEqual(data["my_decision"], "include")

    def test_my_decision_returns_null_without_request_context(self):
        """R01: Returns null when no request context is provided."""
        serializer = ProcessedResultSerializer(self.result)
        data = serializer.data
        self.assertIsNone(data["my_decision"])
