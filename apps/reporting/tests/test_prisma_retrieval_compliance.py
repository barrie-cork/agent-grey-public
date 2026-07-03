"""
Tests for PRISMA-compliant retrieval statistics.

This test suite verifies that the PRISMA reporting service correctly implements
PRISMA compliance requirements for retrieval statistics by:

1. Using only actual user interaction data (URL clicks)
2. Not using theoretical PDF availability as fallback
3. Ensuring mathematical correctness of statistics
4. Properly tracking success/failure status from user interactions

Tests verify both edge cases (no clicks) and normal operation (with clicks).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.reporting.services.prisma_reporting_service import PrismaReportingService
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import URLAccessLog
from apps.core.tests.utils import create_test_user

User = get_user_model()


class PRISMARetrievalComplianceTests(TestCase):
    """Test PRISMA compliance in retrieval statistics reporting."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test PRISMA Session", owner=self.user, status="under_review"
        )

        # Create test results
        self.results = []
        for i in range(5):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"https://example.com/doc{i + 1}.pdf",
                is_pdf=(i < 2),  # First 2 are PDFs, rest are not
                processing_status="success",
            )
            self.results.append(result)

        self.service = PrismaReportingService()

    def test_no_url_clicks_returns_zero_statistics(self):
        """
        Test that when no URLs have been clicked, all retrieval statistics are 0.

        This is the core PRISMA compliance requirement - no fallback to
        theoretical PDF availability should occur.
        """
        stats = self.service.get_retrieval_statistics(str(self.session.id))

        # All statistics should be 0 when no clicks have occurred
        self.assertEqual(stats["reports_sought_for_retrieval"], 0)
        self.assertEqual(stats["reports_not_retrieved"], 0)
        self.assertEqual(stats["reports_retrieved"], 0)
        self.assertEqual(stats["reports_assessed_for_eligibility"], 0)
        self.assertEqual(stats["failure_reasons"], {})
        self.assertEqual(stats["retrieval_rate"], 0.0)

    def test_url_clicks_generate_correct_statistics(self):
        """
        Test that URL clicks generate correct retrieval statistics.

        Should only count actual user interactions, not theoretical availability.
        """
        # Simulate 3 URL clicks: 2 successful, 1 failed
        URLAccessLog.objects.create(
            result=self.results[0],
            user=self.user,
            session=self.session,
            access_successful=True,
        )

        URLAccessLog.objects.create(
            result=self.results[1],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="broken_link",
        )

        URLAccessLog.objects.create(
            result=self.results[2],
            user=self.user,
            session=self.session,
            access_successful=True,
        )

        stats = self.service.get_retrieval_statistics(str(self.session.id))

        # Should reflect actual clicks only
        self.assertEqual(stats["reports_sought_for_retrieval"], 3)
        self.assertEqual(stats["reports_retrieved"], 2)
        self.assertEqual(stats["reports_not_retrieved"], 1)
        self.assertEqual(stats["reports_assessed_for_eligibility"], 2)
        self.assertEqual(stats["failure_reasons"], {"Broken Link": 1})
        self.assertEqual(stats["retrieval_rate"], 66.7)

    def test_mathematical_correctness(self):
        """
        Test mathematical correctness of retrieval statistics.

        Sought = Retrieved + Not Retrieved should always be true.
        """
        # Create various click scenarios
        URLAccessLog.objects.create(
            result=self.results[0],
            user=self.user,
            session=self.session,
            access_successful=True,
        )

        URLAccessLog.objects.create(
            result=self.results[1],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="access_denied",
        )

        URLAccessLog.objects.create(
            result=self.results[2],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="timeout",
        )

        URLAccessLog.objects.create(
            result=self.results[3],
            user=self.user,
            session=self.session,
            access_successful=True,
        )

        stats = self.service.get_retrieval_statistics(str(self.session.id))

        # Mathematical correctness check
        sought = stats["reports_sought_for_retrieval"]
        retrieved = stats["reports_retrieved"]
        not_retrieved = stats["reports_not_retrieved"]

        self.assertEqual(sought, retrieved + not_retrieved)
        self.assertEqual(sought, 4)
        self.assertEqual(retrieved, 2)
        self.assertEqual(not_retrieved, 2)

    def test_unique_result_counting(self):
        """
        Test that multiple clicks on the same result are counted once.

        PRISMA statistics should count unique results, not individual clicks.
        """
        # Multiple clicks on same result
        URLAccessLog.objects.create(
            result=self.results[0],
            user=self.user,
            session=self.session,
            access_successful=True,
        )

        # Second user clicks same result (should still count as 1 unique result)
        other_user = create_test_user(username_prefix="otheruser")
        URLAccessLog.objects.create(
            result=self.results[0],
            user=other_user,
            session=self.session,
            access_successful=True,
        )

        # Different result clicked once
        URLAccessLog.objects.create(
            result=self.results[1],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="broken_link",
        )

        stats = self.service.get_retrieval_statistics(str(self.session.id))

        # Should count unique results, not total clicks
        self.assertEqual(stats["reports_sought_for_retrieval"], 2)
        self.assertEqual(stats["reports_retrieved"], 1)
        self.assertEqual(stats["reports_not_retrieved"], 1)

    def test_failure_reason_aggregation(self):
        """
        Test proper aggregation of failure reasons from actual failed attempts.
        """
        # Create failures with different reasons
        URLAccessLog.objects.create(
            result=self.results[0],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="broken_link",
        )

        URLAccessLog.objects.create(
            result=self.results[1],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="broken_link",
        )

        URLAccessLog.objects.create(
            result=self.results[2],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="access_denied",
        )

        stats = self.service.get_retrieval_statistics(str(self.session.id))

        expected_reasons = {"Broken Link": 2, "Access Denied": 1}

        self.assertEqual(stats["failure_reasons"], expected_reasons)
        self.assertEqual(stats["reports_not_retrieved"], 3)

    def test_prisma_flow_data_integration(self):
        """
        Test that PRISMA flow data uses the corrected retrieval statistics.
        """
        # Create some URL access logs
        URLAccessLog.objects.create(
            result=self.results[0],
            user=self.user,
            session=self.session,
            access_successful=True,
        )

        URLAccessLog.objects.create(
            result=self.results[1],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="broken_link",
        )

        flow_data = self.service.generate_prisma_flow_data(str(self.session.id))
        retrieval_section = flow_data["retrieval"]

        self.assertEqual(retrieval_section["reports_sought"], 2)
        self.assertEqual(retrieval_section["reports_retrieved"], 1)
        self.assertEqual(retrieval_section["reports_not_retrieved"], 1)
        self.assertEqual(retrieval_section["failure_reasons"], {"Broken Link": 1})

    def test_no_pdf_fallback_logic(self):
        """
        Test that the old PDF availability fallback logic is completely removed.

        Even with PDF results available, if no clicks occurred, statistics should be 0.
        """
        # Verify we have PDFs available (from setUp)
        pdf_count = ProcessedResult.objects.filter(
            session=self.session, is_pdf=True
        ).count()
        self.assertEqual(pdf_count, 2)  # First 2 results are PDFs

        # But with no URL clicks, statistics should be 0 (not using PDF fallback)
        stats = self.service.get_retrieval_statistics(str(self.session.id))

        self.assertEqual(stats["reports_sought_for_retrieval"], 0)
        self.assertEqual(stats["reports_retrieved"], 0)
        self.assertEqual(stats["reports_not_retrieved"], 0)

        # This confirms we're NOT falling back to PDF availability

    def test_edge_case_empty_session(self):
        """
        Test handling of edge case: session with no results.
        """
        empty_session = SearchSession.objects.create(
            title="Empty Session", owner=self.user, status="completed"
        )

        stats = self.service.get_retrieval_statistics(str(empty_session.id))

        self.assertEqual(stats["reports_sought_for_retrieval"], 0)
        self.assertEqual(stats["reports_retrieved"], 0)
        self.assertEqual(stats["reports_not_retrieved"], 0)
        self.assertEqual(stats["reports_assessed_for_eligibility"], 0)
        self.assertEqual(stats["failure_reasons"], {})
        self.assertEqual(stats["retrieval_rate"], 0.0)

    def test_retrieval_rate_calculation(self):
        """
        Test correct calculation of retrieval rate percentage.
        """
        # 3 successful, 1 failed = 75% success rate
        for i in range(3):
            URLAccessLog.objects.create(
                result=self.results[i],
                user=self.user,
                session=self.session,
                access_successful=True,
            )

        URLAccessLog.objects.create(
            result=self.results[3],
            user=self.user,
            session=self.session,
            access_successful=False,
            failure_reason="timeout",
        )

        stats = self.service.get_retrieval_statistics(str(self.session.id))

        self.assertEqual(stats["retrieval_rate"], 75.0)
        self.assertEqual(stats["reports_sought_for_retrieval"], 4)
        self.assertEqual(stats["reports_retrieved"], 3)
        self.assertEqual(stats["reports_not_retrieved"], 1)

    def test_different_session_isolation(self):
        """
        Test that statistics are properly isolated between different sessions.
        """
        # Create another session
        other_session = SearchSession.objects.create(
            title="Other Session", owner=self.user, status="under_review"
        )

        other_result = ProcessedResult.objects.create(
            session=other_session,
            title="Other Result",
            url="https://example.com/other.pdf",
            processing_status="success",
        )

        # Add clicks to original session
        URLAccessLog.objects.create(
            result=self.results[0],
            user=self.user,
            session=self.session,
            access_successful=True,
        )

        # Add clicks to other session
        URLAccessLog.objects.create(
            result=other_result,
            user=self.user,
            session=other_session,
            access_successful=False,
            failure_reason="broken_link",
        )

        # Test original session
        stats1 = self.service.get_retrieval_statistics(str(self.session.id))
        self.assertEqual(stats1["reports_sought_for_retrieval"], 1)
        self.assertEqual(stats1["reports_retrieved"], 1)

        # Test other session
        stats2 = self.service.get_retrieval_statistics(str(other_session.id))
        self.assertEqual(stats2["reports_sought_for_retrieval"], 1)
        self.assertEqual(stats2["reports_retrieved"], 0)
