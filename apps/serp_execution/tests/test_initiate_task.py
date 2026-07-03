"""
Tests for SERP execution initiation task.

Tests for initiate_search_session_execution_task (alias for execute_search_session_simple).
"""

from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.tasks import initiate_search_session_execution_task


class TestInitiateSearchSessionExecutionTask(TestCase):
    """Test cases for initiate_search_session_execution_task."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="ready_to_execute"
        )

        # Create SearchStrategy first
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers", "engineers"],
            interest_terms=["testing", "quality"],
            context_terms=["agile", "scrum"],
            search_config={
                "domains": ["example.com"],
                "file_types": ["pdf"],
                "include_general_search": True,
            },
        )

        self.query1 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="site:example.com (developers OR engineers) AND testing AND agile",
            query_type="domain-specific",
            target_domain="example.com",
            is_active=True,
            execution_order=1,
        )
        self.query2 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="(developers OR engineers) AND testing AND agile",
            query_type="general",
            target_domain=None,
            is_active=True,
            execution_order=2,
        )

    def test_invalid_session_status(self):
        """Test initiation with invalid session status returns error."""
        self.session.status = "draft"
        self.session.save()

        result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]

        self.assertFalse(result["success"])
        self.assertIn("Invalid status for execution", result["error"])

    def test_session_not_found(self):
        """Test initiation with non-existent session."""
        non_existent_uuid = "00000000-0000-0000-0000-000000000000"
        result = initiate_search_session_execution_task(non_existent_uuid)  # type: ignore[call-arg]

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    def test_successful_execution_transitions_session(self):
        """Test that successful initiation transitions session past executing."""
        _result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]

        self.session.refresh_from_db()
        # With CELERY_TASK_ALWAYS_EAGER, the task chain runs synchronously
        # so the session may transition all the way to ready_for_review
        self.assertIn(
            self.session.status,
            ["executing", "processing_results", "ready_for_review"],
        )

    def test_no_active_queries(self):
        """Test initiation with no active queries."""
        SearchQuery.objects.filter(session=self.session).update(is_active=False)

        result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]

        # Task still runs but with 0 queries
        # Check it doesn't crash
        self.assertIn("success", result)
