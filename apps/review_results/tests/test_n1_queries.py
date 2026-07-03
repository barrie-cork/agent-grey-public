"""
Tests for N+1 query prevention in review_results views.

This module verifies that filtering operations in ResultsReviewView use
O(1) queries instead of N+1 patterns where N is the number of results.

NOTE: The view has many other operations (progress calculations, template
rendering, pagination) that generate queries. This test focuses on ensuring
the FILTERING logic doesn't scale with result count (O(1) not O(N)).
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organisation.models import Organisation
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.results_manager.models import ProcessedResult

from ..models import ReviewerDecision, SimpleReviewDecision
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ReviewViewN1QueryTest(TestCase):
    """Test that review filtering doesn't cause N+1 queries."""

    def setUp(self):
        """Create test data with many results."""
        self.user = create_test_user()
        self.other_user = create_test_user(username_prefix="otheruser")
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create Workflow #1 session (single reviewer)
        self.session_workflow1 = SearchSession.objects.create(
            title="Workflow 1 Session",
            owner=self.user,
            organisation=self.org,
            status="under_review",
        )
        self.config_workflow1 = ReviewConfiguration.objects.create(
            session=self.session_workflow1,
            min_reviewers_per_result=1,
            created_by=self.user,
            organisation=self.org,
        )
        self.session_workflow1.current_configuration = self.config_workflow1
        self.session_workflow1.save()

        # Create Workflow #2 session (dual screening)
        self.session_workflow2 = SearchSession.objects.create(
            title="Workflow 2 Session",
            owner=self.user,
            organisation=self.org,
            status="under_review",
        )
        self.config_workflow2 = ReviewConfiguration.objects.create(
            session=self.session_workflow2,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            created_by=self.user,
            organisation=self.org,
        )
        self.session_workflow2.current_configuration = self.config_workflow2
        self.session_workflow2.save()

        # Create 50 results for each session
        self.result_count = 50
        self._create_results(self.session_workflow1, self.result_count)
        self._create_results(self.session_workflow2, self.result_count)

        # Create some review decisions for filtering tests
        self._create_workflow1_decisions()
        self._create_workflow2_decisions()

        self.client = Client()
        self.client.login(username=self.user.username, password="testpass123")

    def _create_results(self, session, count):
        """Create test results for a session."""
        ProcessedResult.objects.bulk_create(
            [
                ProcessedResult(
                    session=session,
                    title=f"Result {i + 1}",
                    url=f"http://example.com/{session.id}/{i + 1}",
                    processing_status="success",
                )
                for i in range(count)
            ]
        )

    def _create_workflow1_decisions(self):
        """Create SimpleReviewDecision records for Workflow #1 session."""
        results = ProcessedResult.objects.filter(session=self.session_workflow1)[:25]
        SimpleReviewDecision.objects.bulk_create(
            [
                SimpleReviewDecision(
                    result=result,
                    session=self.session_workflow1,
                    reviewer=self.user,
                    decision="include" if i % 3 == 0 else "exclude",
                )
                for i, result in enumerate(results)
            ]
        )

    def _create_workflow2_decisions(self):
        """Create ReviewerDecision records for Workflow #2 session."""
        results = ProcessedResult.objects.filter(session=self.session_workflow2)[:25]
        ReviewerDecision.objects.bulk_create(
            [
                ReviewerDecision(
                    result=result,
                    organisation=self.org,
                    reviewer=self.user,
                    decision="INCLUDE" if i % 3 == 0 else "EXCLUDE",
                    is_revote=False,
                )
                for i, result in enumerate(results)
            ]
        )

    def test_filter_query_count_scales_constant_workflow1(self):
        """
        Verify Workflow #1 filter query count is O(1), not O(N).

        This is the key test - with database-level filtering, the query count
        should NOT increase significantly when we double the result count.
        Previously with Python list comprehensions, adding more results would
        add proportionally more queries.
        """
        url = reverse("review_results:overview", args=[self.session_workflow1.id])

        # Test with 50 results (already created)
        with CaptureQueriesContext(connection) as context_50:
            response = self.client.get(url, {"review_status": "pending"})
        self.assertEqual(response.status_code, 200)
        queries_50 = len(context_50)

        # Add 50 more results (now 100 total)
        self._create_results(self.session_workflow1, 50)

        with CaptureQueriesContext(connection) as context_100:
            response = self.client.get(url, {"review_status": "pending"})
        self.assertEqual(response.status_code, 200)
        queries_100 = len(context_100)

        # If O(N), queries would roughly double. If O(1), should stay similar.
        # Allow for some variance but not 2x increase
        self.assertLess(
            queries_100,
            queries_50 * 1.5,  # Allow 50% increase for minor variations
            f"Query count scaled from {queries_50} to {queries_100}. "
            f"This suggests O(N) complexity instead of O(1).",
        )

    def test_filter_query_count_scales_constant_workflow2(self):
        """
        Verify Workflow #2 filter query count is O(1), not O(N).

        This was the main N+1 problem area - previously the view would
        call ReviewerDecision.objects.filter(...).exists() inside a loop
        for each result. Now it uses database-level Exists() subquery.
        """
        url = reverse("review_results:overview", args=[self.session_workflow2.id])

        # Test with 50 results (already created)
        with CaptureQueriesContext(connection) as context_50:
            response = self.client.get(url, {"review_status": "pending"})
        self.assertEqual(response.status_code, 200)
        queries_50 = len(context_50)

        # Add 50 more results (now 100 total)
        self._create_results(self.session_workflow2, 50)

        with CaptureQueriesContext(connection) as context_100:
            response = self.client.get(url, {"review_status": "pending"})
        self.assertEqual(response.status_code, 200)
        queries_100 = len(context_100)

        # Key assertion: query count should NOT double when result count doubles
        self.assertLess(
            queries_100,
            queries_50 * 1.5,  # Allow 50% increase for minor variations
            f"Workflow #2 query count scaled from {queries_50} to {queries_100}. "
            f"This suggests O(N) complexity instead of O(1). "
            f"The Exists() subquery optimization may not be working.",
        )

    def test_include_filter_query_count_scales_constant(self):
        """Verify include filter also uses O(1) queries."""
        url = reverse("review_results:overview", args=[self.session_workflow2.id])

        # Test with 50 results
        with CaptureQueriesContext(connection) as context_50:
            response = self.client.get(url, {"review_status": "include"})
        self.assertEqual(response.status_code, 200)
        queries_50 = len(context_50)

        # Add 50 more results (now 100 total)
        self._create_results(self.session_workflow2, 50)

        with CaptureQueriesContext(connection) as context_100:
            response = self.client.get(url, {"review_status": "include"})
        self.assertEqual(response.status_code, 200)
        queries_100 = len(context_100)

        # Query count should not scale linearly with result count
        self.assertLess(
            queries_100,
            queries_50 * 1.5,
            f"Include filter query count scaled from {queries_50} to {queries_100}. "
            f"This suggests O(N) complexity instead of O(1).",
        )

    def test_view_renders_with_filters(self):
        """Verify the view renders correctly with various filters."""
        # Test all filter options work without errors
        filters = ["pending", "include", "exclude", "retrieved"]
        sessions = [self.session_workflow1, self.session_workflow2]

        for session in sessions:
            url = reverse("review_results:overview", args=[session.id])
            for filter_value in filters:
                with self.subTest(session=session.title, filter=filter_value):
                    response = self.client.get(url, {"review_status": filter_value})
                    self.assertEqual(
                        response.status_code,
                        200,
                        f"Filter '{filter_value}' failed for {session.title}",
                    )
