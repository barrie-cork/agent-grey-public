"""
Tests for simplified review results services.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision
from apps.review_results.services.simple_export_service import SimpleExportService
from apps.review_results.services.simple_review_progress_service import (
    SimpleReviewProgressService,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SimpleReviewProgressServiceTest(TestCase):
    """Test the simple progress service."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        # Create 10 test results
        self.results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/test{i}",
                snippet=f"Test snippet {i}",
            )
            self.results.append(result)

        self.service = SimpleReviewProgressService()

    def test_empty_progress(self):
        """Test progress with no decisions made."""
        progress = self.service.get_progress_summary(str(self.session.id))

        self.assertEqual(progress["total_results"], 10)
        self.assertEqual(progress["reviewed_count"], 0)
        self.assertEqual(progress["pending_count"], 10)
        self.assertEqual(progress["include_count"], 0)
        self.assertEqual(progress["exclude_count"], 0)
        self.assertEqual(progress["maybe_count"], 0)
        self.assertEqual(progress["completion_percentage"], 0.0)

    def test_partial_progress(self):
        """Test progress with some decisions made."""
        # Make some decisions
        SimpleReviewDecision.objects.create(
            result=self.results[0],
            session=self.session,
            reviewer=self.user,
            decision="include",
        )
        SimpleReviewDecision.objects.create(
            result=self.results[1],
            session=self.session,
            reviewer=self.user,
            decision="exclude",
            exclusion_reason="not_relevant",
        )
        SimpleReviewDecision.objects.create(
            result=self.results[2],
            session=self.session,
            reviewer=self.user,
            decision="maybe",
        )
        # results[3] stays pending (no decision created)

        progress = self.service.get_progress_summary(str(self.session.id))

        self.assertEqual(progress["total_results"], 10)
        self.assertEqual(progress["reviewed_count"], 3)  # include + exclude + maybe
        self.assertEqual(progress["pending_count"], 7)
        self.assertEqual(progress["include_count"], 1)
        self.assertEqual(progress["exclude_count"], 1)
        self.assertEqual(progress["maybe_count"], 1)
        self.assertEqual(progress["completion_percentage"], 30.0)

    def test_complete_progress(self):
        """Test progress with all decisions made."""
        # Review all results
        for i, result in enumerate(self.results):
            if i < 3:
                decision = "include"
                exclusion_reason = ""
            elif i < 6:
                decision = "exclude"
                exclusion_reason = "not_relevant"
            else:
                decision = "maybe"
                exclusion_reason = ""

            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.user,
                decision=decision,
                exclusion_reason=exclusion_reason,
            )

        progress = self.service.get_progress_summary(str(self.session.id))

        self.assertEqual(progress["total_results"], 10)
        self.assertEqual(progress["reviewed_count"], 10)
        self.assertEqual(progress["pending_count"], 0)
        self.assertEqual(progress["include_count"], 3)
        self.assertEqual(progress["exclude_count"], 3)
        self.assertEqual(progress["maybe_count"], 4)
        self.assertEqual(progress["completion_percentage"], 100.0)


class SimpleExportServiceTest(TestCase):
    """Test the simple export service."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        # Create test results with decisions
        self.result1 = ProcessedResult.objects.create(
            session=self.session,
            title="Included Result",
            url="https://example.com/include",
            snippet="This should be included",
            publication_year=2023,
            document_type="report",
        )

        self.result2 = ProcessedResult.objects.create(
            session=self.session,
            title="Excluded Result",
            url="https://example.com/exclude",
            snippet="This should be excluded",
            publication_year=2022,
            document_type="thesis",
        )

        # Create decisions
        self.decision1 = SimpleReviewDecision.objects.create(
            result=self.result1,
            session=self.session,
            reviewer=self.user,
            decision="include",
            notes="Highly relevant to our research",
        )

        self.decision2 = SimpleReviewDecision.objects.create(
            result=self.result2,
            session=self.session,
            reviewer=self.user,
            decision="exclude",
            exclusion_reason="not_relevant",
            notes="Not related to our topic",
        )

        self.service = SimpleExportService()

    def test_export_decisions(self):
        """Test exporting review decisions."""
        export_data = self.service.export_review_decisions(str(self.session.id))

        self.assertEqual(export_data["session_id"], str(self.session.id))
        self.assertEqual(export_data["total_records"], 2)

        records = export_data["export_data"]
        self.assertEqual(len(records), 2)

        # Check first record (include decision)
        include_record = next(r for r in records if r["decision"] == "Include")
        self.assertEqual(include_record["title"], "Included Result")
        self.assertEqual(include_record["url"], "https://example.com/include")
        self.assertEqual(include_record["publication_year"], 2023)
        self.assertEqual(include_record["document_type"], "report")
        self.assertEqual(include_record["exclusion_reason"], "")
        self.assertEqual(include_record["notes"], "Highly relevant to our research")
        self.assertEqual(include_record["reviewer"], self.user.username)

        # Check second record (exclude decision)
        exclude_record = next(r for r in records if r["decision"] == "Exclude")
        self.assertEqual(exclude_record["title"], "Excluded Result")
        self.assertEqual(
            exclude_record["exclusion_reason"], "Not relevant to research question"
        )
        self.assertEqual(exclude_record["notes"], "Not related to our topic")

    def test_export_empty_session(self):
        """Test exporting from session with no decisions."""
        empty_session = SearchSession.objects.create(
            title="Empty Session", owner=self.user, status="draft"
        )

        export_data = self.service.export_review_decisions(str(empty_session.id))

        self.assertEqual(export_data["session_id"], str(empty_session.id))
        self.assertEqual(export_data["total_records"], 0)
        self.assertEqual(len(export_data["export_data"]), 0)
