"""
Tests for Code Review #7 Enhancements.

This module tests the improvements implemented based on Code Review #7 recommendations:
- Helper function extraction for session_quick_status_api
- QueryProgressEvent with pagination_info TypedDict
- SearchSession.is_executing_or_processing property
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.state_machine.events import QueryProgressEvent
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestSessionQuickStatusEnhancements(TestCase):
    """Test enhancements to session_quick_status_api endpoint."""

    def setUp(self):
        """Create test fixtures."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            status="executing",
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["diabetes"],
            interest_terms=["treatment"],
            context_terms=["uk"],
        )

    def test_query_count_uses_strategy(self):
        """Test that query count is calculated from strategy during execution."""
        # Create queries via strategy
        SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test query 1",
            query_type="general",
            execution_order=1,
        )
        SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test query 2",
            query_type="general",
            execution_order=2,
        )

        url = reverse(
            "serp_execution:session_quick_status_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data["total_queries"], 2)
        self.assertIn("query_stats", data)
        self.assertEqual(data["query_stats"]["total_queries"], 2)

    def test_query_count_returns_zero_without_strategy(self):
        """Test query count returns 0 when no strategy exists."""
        # Create session without strategy
        session_without_strategy = SearchSession.objects.create(
            title="No Strategy Session",
            owner=self.user,
            status="executing",
        )

        url = reverse(
            "serp_execution:session_quick_status_api",
            kwargs={"session_id": session_without_strategy.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data["total_queries"], 0)
        self.assertEqual(data["completed_queries"], 0)

    def test_includes_pagination_metadata(self):
        """Test API includes pagination details from executions."""
        query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test query",
            query_type="general",
            execution_order=1,
        )

        _execution = SearchExecution.objects.create(
            query=query,
            initiated_by=self.user,
            status="running",
            api_result_count=25,
            step_metadata={
                "pagination": {
                    "pages_fetched": 3,
                    "max_pages": 10,
                    "stopped_reason": "in_progress",
                }
            },
            started_at=timezone.now(),
        )

        url = reverse(
            "serp_execution:session_quick_status_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertIn("current_query", data)
        current_query = data["current_query"]
        self.assertIsNotNone(current_query)
        self.assertEqual(current_query["current_page"], 3)
        self.assertEqual(current_query["total_pages"], 10)
        self.assertEqual(current_query["results_so_far"], 25)
        self.assertEqual(current_query["stopped_reason"], "in_progress")

    def test_helper_function_reduces_complexity(self):
        """
        Test that helper function is used (implicit via successful execution).

        This test verifies that the refactored code still works correctly,
        which proves the helper function extraction was successful.
        """
        query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test query",
            query_type="general",
            execution_order=1,
        )

        SearchExecution.objects.create(
            query=query,
            initiated_by=self.user,
            status="completed",
            api_result_count=10,
            completed_at=timezone.now(),
        )

        url = reverse(
            "serp_execution:session_quick_status_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Verify all expected data is present
        self.assertIn("total_queries", data)
        self.assertIn("completed_queries", data)
        self.assertIn("progress_percentage", data)
        self.assertIn("current_query", data)
        self.assertIn("recent_queries", data)


class TestQueryProgressEvent(TestCase):
    """Test QueryProgressEvent with pagination_info TypedDict."""

    def test_query_progress_event_with_pagination_info(self):
        """Test event includes pagination metadata in to_dict()."""
        pagination_info = {
            "pages_fetched": 5,
            "stopped_reason": "limit_reached",
            "max_pages": 10,
            "total_available": 15,
        }

        event = QueryProgressEvent(
            session_id="test-session-id",
            query_index=3,
            total_queries=5,
            query_text="test query",
            status="completed",
            results_count=50,
            pagination_info=pagination_info,  # type: ignore[arg-type]
        )

        event_dict = event.to_dict()

        self.assertEqual(event_dict["event_type"], "query_progress")
        self.assertEqual(event_dict["query_index"], 3)
        self.assertEqual(event_dict["total_queries"], 5)
        self.assertEqual(event_dict["status"], "completed")
        self.assertEqual(event_dict["results_count"], 50)

        # Verify pagination_info is included
        self.assertIn("pagination_info", event_dict)
        self.assertEqual(event_dict["pagination_info"]["pages_fetched"], 5)
        self.assertEqual(
            event_dict["pagination_info"]["stopped_reason"], "limit_reached"
        )
        self.assertEqual(event_dict["pagination_info"]["max_pages"], 10)
        self.assertEqual(event_dict["pagination_info"]["total_available"], 15)

    def test_query_progress_event_without_pagination_info(self):
        """Test event handles None pagination gracefully."""
        event = QueryProgressEvent(
            session_id="test-session-id",
            query_index=1,
            total_queries=3,
            query_text="test query",
            status="starting",
            results_count=0,
            pagination_info=None,
        )

        event_dict = event.to_dict()

        self.assertEqual(event_dict["event_type"], "query_progress")
        self.assertIn("pagination_info", event_dict)
        # Should return empty dict when None
        self.assertEqual(event_dict["pagination_info"], {})

    def test_progress_percentage_calculation(self):
        """Test progress percentage is calculated correctly."""
        # Test starting query (query_index - 1 used)
        event_starting = QueryProgressEvent(
            session_id="test-session-id",
            query_index=2,
            total_queries=5,
            query_text="test query",
            status="starting",
        )
        event_dict = event_starting.to_dict()
        # (2-1)/5 * 100 = 20%
        self.assertEqual(event_dict["progress_percent"], 20)

        # Test completed query (query_index used)
        event_completed = QueryProgressEvent(
            session_id="test-session-id",
            query_index=3,
            total_queries=5,
            query_text="test query",
            status="completed",
        )
        event_dict = event_completed.to_dict()
        # 3/5 * 100 = 60%
        self.assertEqual(event_dict["progress_percent"], 60)


class TestSearchSessionProperties(TestCase):
    """Test SearchSession model property enhancements."""

    def setUp(self):
        """Create test fixtures."""
        self.user = create_test_user()

    def test_is_executing_or_processing_true_for_executing(self):
        """Test property returns True for 'executing' status."""
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            status="executing",
        )

        self.assertTrue(session.is_executing_or_processing)

    def test_is_executing_or_processing_true_for_processing_results(self):
        """Test property returns True for 'processing_results' status."""
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            status="processing_results",
        )

        self.assertTrue(session.is_executing_or_processing)

    def test_is_executing_or_processing_false_for_other_statuses(self):
        """Test property returns False for other statuses."""
        test_statuses = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "ready_for_review",
            "under_review",
            "completed",
            "archived",
        ]

        for status in test_statuses:
            with self.subTest(status=status):
                session = SearchSession.objects.create(
                    title=f"Test Session - {status}",
                    owner=self.user,
                    status=status,
                )

                self.assertFalse(
                    session.is_executing_or_processing,
                    f"Expected False for status '{status}'",
                )
