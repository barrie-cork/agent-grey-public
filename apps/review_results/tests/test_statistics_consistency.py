"""
Test statistics consistency to fix review results display bug.

This test reproduces the exact scenario described in the bug report:
- 50 total results
- User makes decisions on all results
- UI shows contradictory statistics

Tests based on Issue UI-001: Review Results Statistics Display Bug
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision
from apps.review_results.services.simple_review_progress_service import (
    SimpleReviewProgressService,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class StatisticsConsistencyTest(TestCase):
    """Test statistics consistency across all UI components."""

    def setUp(self):
        """Set up test data matching the bug report scenario."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="under_review"
        )

        # Create 50 processed results (matching bug report)
        self.results = []
        for i in range(50):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"https://example.com/result{i + 1}",
                snippet=f"Test snippet {i + 1}",
                processing_status="success",
            )
            self.results.append(result)

    def test_all_results_reviewed_shows_correct_statistics(self):
        """Test that when all results are reviewed, statistics are consistent."""
        # Make decisions on all 50 results (matching bug report)
        for i, result in enumerate(self.results):
            if i < 20:
                decision = "include"
            elif i < 45:
                decision = "exclude"
            else:
                decision = "maybe"

            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.user,
                decision=decision,
                exclusion_reason="not_relevant" if decision == "exclude" else "",
                notes=f"Test notes for result {i + 1}",
            )

        # Get statistics from the service
        service = SimpleReviewProgressService()
        progress = service.get_progress_summary(str(self.session.id))

        # Verify consistency - no contradictions allowed
        self.assertEqual(progress["total_results"], 50, "Total results should be 50")
        self.assertEqual(
            progress["reviewed_count"],
            50,
            "All 50 results should be marked as reviewed",
        )
        self.assertEqual(
            progress["pending_count"], 0, "No pending results when all reviewed"
        )
        self.assertEqual(
            progress["completion_percentage"], 100.0, "Should be 100% complete"
        )

        # Verify decision counts add up correctly
        total_decisions = (
            progress["include_count"]
            + progress["exclude_count"]
            + progress["maybe_count"]
        )
        self.assertEqual(
            total_decisions, 50, "Decision counts should add up to total results"
        )

        # Verify specific decision counts
        self.assertEqual(
            progress["include_count"], 20, "Should have 20 included results"
        )
        self.assertEqual(
            progress["exclude_count"], 25, "Should have 25 excluded results"
        )
        self.assertEqual(progress["maybe_count"], 5, "Should have 5 maybe results")

        # Test retrieved count (initially 0 since no URLs clicked)
        self.assertEqual(progress["retrieved_count"], 0, "No URLs clicked yet")

    def test_retrieved_count_updates_when_urls_clicked(self):
        """Test that retrieved count updates when users click URLs."""
        # Make decisions on first 10 results
        for i in range(10):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=self.user,
                decision="include",
            )

        # Mark first 5 results as retrieved (user clicked URLs)
        from django.utils import timezone

        for i in range(5):
            self.results[i].is_retrieved = True
            self.results[i].retrieved_at = timezone.now()
            self.results[i].save()

        service = SimpleReviewProgressService()
        progress = service.get_progress_summary(str(self.session.id))

        self.assertEqual(
            progress["retrieved_count"], 5, "Should show 5 retrieved results"
        )
        self.assertEqual(
            progress["include_count"], 10, "Should still show 10 included results"
        )
        self.assertEqual(
            progress["reviewed_count"], 10, "Should show 10 reviewed results"
        )

    def test_partial_review_shows_correct_progress(self):
        """Test statistics when only some results are reviewed."""
        # Review only 25 out of 50 results
        for i in range(25):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=self.user,
                decision="include" if i < 10 else "exclude",
                exclusion_reason="not_relevant" if i >= 10 else "",
            )

        service = SimpleReviewProgressService()
        progress = service.get_progress_summary(str(self.session.id))

        self.assertEqual(progress["total_results"], 50)
        self.assertEqual(progress["reviewed_count"], 25)
        self.assertEqual(progress["pending_count"], 25)
        self.assertEqual(progress["completion_percentage"], 50.0)
        self.assertEqual(progress["include_count"], 10)
        self.assertEqual(progress["exclude_count"], 15)
        self.assertEqual(progress["maybe_count"], 0)

    def test_statistics_with_duplicates(self):
        """Test that duplicate handling doesn't break statistics."""
        # Mark 5 results as filtered duplicates
        for i in range(5):
            self.results[i].processing_status = "filtered"
            self.results[i].processing_error_category = "duplicate"
            self.results[i].save()

        # Make decisions on all remaining successful results (45)
        successful_results = ProcessedResult.objects.filter(
            session=self.session, processing_status="success"
        )
        for result in successful_results:
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.user,
                decision="include",
            )

        service = SimpleReviewProgressService()
        progress = service.get_progress_summary(str(self.session.id))

        # With 5 filtered duplicates: unique results = 50 - 5 = 45
        expected_unique = 45
        self.assertEqual(progress["total_results"], expected_unique)
        self.assertEqual(progress["reviewed_count"], 45, "45 unique results reviewed")
        self.assertEqual(progress["pending_count"], 0, "No pending results")
        self.assertEqual(progress["duplicates_removed"], 5, "5 duplicates removed")


class ViewContextConsistencyTest(TestCase):
    """Test that view context uses the same data as template tags."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user(username_prefix="testuser2")

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="under_review"
        )

        # Create test results
        for i in range(10):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i + 1}",
                url=f"https://example.com/{i + 1}",
                processing_status="success",
            )

    def test_view_context_matches_service_data(self):
        """Test that view context variables match service statistics."""
        from django.test import RequestFactory

        from apps.review_results.views.review_views import ResultsReviewView

        # Create a mock request
        factory = RequestFactory()
        request = factory.get("/")
        request.user = self.user

        # Create view instance and get context
        view = ResultsReviewView()
        view.request = request
        view.kwargs = {"session_id": str(self.session.id)}

        context = view.get_context_data()

        # Get service data for comparison
        service = SimpleReviewProgressService()
        progress = service.get_progress_summary(str(self.session.id))

        # Verify consistency between view context and service data
        self.assertEqual(context["pending_count"], progress["pending_count"])
        self.assertEqual(context["included_count"], progress["include_count"])
        self.assertEqual(context["excluded_count"], progress["exclude_count"])
        self.assertEqual(context["maybe_count"], progress["maybe_count"])
