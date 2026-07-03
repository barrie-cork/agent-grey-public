"""
Tests for duplicate handling in review progress calculations.
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


class DuplicateHandlingTestCase(TestCase):
    """Test that duplicates are handled correctly in progress calculations."""

    def setUp(self):
        """Set up test data."""
        # Create user and session
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session",
            status="under_review",
            owner=self.user,
        )

        # Create 10 ProcessedResults (8 successful, 2 filtered as duplicates)
        self.results = []
        for i in range(8):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i + 1}",
                url=f"http://example.com/{i + 1}",
                processing_status="success",
            )
            self.results.append(result)

        # Create 2 filtered duplicate results
        for i in range(2):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Duplicate Result {i + 1}",
                url=f"http://example.com/dup{i + 1}",
                processing_status="filtered",
                processing_error_category="duplicate",
            )
            self.results.append(result)

        # Create SimpleReviewDecisions for all successful results
        for result in self.results[:8]:
            SimpleReviewDecision.objects.create(
                session=self.session,
                result=result,
                decision="exclude",
                reviewer=self.user,
                exclusion_reason="not_relevant",
            )

    def test_progress_calculation_with_duplicates(self):
        """Test that progress is calculated correctly when duplicates exist."""
        service = SimpleReviewProgressService()
        progress = service.get_progress_summary(str(self.session.id))

        # We have 10 results total: 8 successful + 2 filtered duplicates
        # Unique (reviewable) results = 8
        self.assertEqual(progress["total_results"], 8, "Should show 8 unique results")
        self.assertEqual(
            progress["duplicates_removed"], 2, "Should show 2 duplicates removed"
        )

        # We marked all 8 successful results as reviewed
        self.assertEqual(
            progress["reviewed_count"],
            8,
            "Should count 8 reviewed (excluding duplicates)",
        )
        self.assertEqual(progress["pending_count"], 0, "Should have 0 pending")

        # Completion should be 100% (8/8)
        self.assertEqual(
            progress["completion_percentage"],
            100.0,
            "Should be 100% complete, not over 100%",
        )

    def test_progress_with_partial_review(self):
        """Test progress calculation when only some results are reviewed."""
        # Reset some decisions to pending
        decisions = SimpleReviewDecision.objects.filter(
            session=self.session, result__in=self.results[4:7]
        )
        decisions.update(decision="pending")

        service = SimpleReviewProgressService()
        progress = service.get_progress_summary(str(self.session.id))

        # 8 unique results, 5 reviewed (8 total successful - 3 set to pending)
        self.assertEqual(progress["total_results"], 8)
        self.assertEqual(progress["reviewed_count"], 5)
        self.assertEqual(progress["pending_count"], 3)
        self.assertEqual(
            progress["completion_percentage"],
            62.5,  # 5/8 * 100
            "Should be 62.5% complete",
        )

    def test_no_duplicates(self):
        """Test that the service works correctly when there are no duplicates."""
        # Create a fresh session with no duplicates
        session = SearchSession.objects.create(
            title="No Duplicates Session",
            status="under_review",
            owner=self.user,
        )

        # Create 10 successful results
        results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=session,
                title=f"Result {i + 1}",
                url=f"http://example.com/nodup/{i + 1}",
                processing_status="success",
            )
            results.append(result)

        # Create decisions for all
        for result in results:
            SimpleReviewDecision.objects.create(
                session=session,
                result=result,
                decision="exclude",
                reviewer=self.user,
                exclusion_reason="not_relevant",
            )

        service = SimpleReviewProgressService()
        progress = service.get_progress_summary(str(session.id))

        # All 10 results should count
        self.assertEqual(progress["total_results"], 10)
        self.assertEqual(progress["reviewed_count"], 10)
        self.assertEqual(progress["duplicates_removed"], 0)
        self.assertEqual(progress["completion_percentage"], 100.0)
