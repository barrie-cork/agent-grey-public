"""Tests for the session_quick_status_api endpoint."""

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestSessionQuickStatusAPI(TestCase):
    """Validate real-time data returned by session_quick_status_api."""

    def setUp(self):
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        self.session = SearchSession.objects.create(
            title="Streaming Session",
            owner=self.user,
            status="executing",
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["term"],
            interest_terms=["interest"],
            context_terms=["context"],
        )

        self.query_running = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="site:nice.org.uk diabetes",
            query_type="general",
            execution_order=1,
        )

        self.query_completed = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="site:who.int diabetes",
            query_type="general",
            execution_order=2,
        )

        pagination_meta_running = {
            "pagination": {
                "pages_fetched": 3,
                "max_pages": 10,
                "stopped_reason": "limit_reached",
            }
        }
        pagination_meta_completed = {
            "pagination": {
                "pages_fetched": 5,
                "max_pages": 10,
                "stopped_reason": "limit_reached",
            }
        }

        now = timezone.now()

        self.execution_running = SearchExecution.objects.create(
            query=self.query_running,
            initiated_by=self.user,
            status="running",
            api_result_count=42,
            step_metadata=pagination_meta_running,
            started_at=now - timedelta(seconds=30),
        )

        self.execution_completed = SearchExecution.objects.create(
            query=self.query_completed,
            initiated_by=self.user,
            status="completed",
            api_result_count=87,
            step_metadata=pagination_meta_completed,
            started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=4, seconds=30),
            duration_seconds=30,
        )

        # Older completion to ensure ordering
        older_query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="site:hiqa.ie diabetes",
            query_type="general",
            execution_order=0,
        )
        SearchExecution.objects.create(
            query=older_query,
            initiated_by=self.user,
            status="completed",
            api_result_count=12,
            step_metadata={
                "pagination": {
                    "pages_fetched": 2,
                    "max_pages": 10,
                    "stopped_reason": "no_more_results",
                }
            },
            started_at=now - timedelta(minutes=15),
            completed_at=now - timedelta(minutes=14, seconds=30),
            duration_seconds=30,
        )

    def test_quick_status_includes_current_query_details(self):
        """API should expose real-time details for the running query."""
        url = reverse(
            "serp_execution:session_quick_status_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEqual(data["status"], "executing")
        self.assertIn("current_query", data)
        current = data["current_query"]
        self.assertIsNotNone(current)
        self.assertEqual(current["execution_id"], str(self.execution_running.id))
        self.assertEqual(current["query_text"], self.query_running.query_text)
        self.assertEqual(current["current_page"], 3)
        self.assertEqual(current["total_pages"], 10)
        self.assertEqual(current["results_so_far"], 42)
        self.assertEqual(current["stopped_reason"], "limit_reached")

        # Existing fields remain
        self.assertIn("query_stats", data)
        self.assertIn("metadata", data)

        # Timestamp for UI freshness
        self.assertIn("timestamp", data)
        self.assertTrue(data["timestamp"])  # non-empty string

    def test_quick_status_includes_recent_completed_queries(self):
        """API should return timeline-ready data for recently finished queries."""
        url = reverse(
            "serp_execution:session_quick_status_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        self.assertIn("recent_queries", data)
        recent = data["recent_queries"]
        self.assertGreaterEqual(len(recent), 2)

        # Most recent first
        self.assertEqual(recent[0]["query_text"], self.query_completed.query_text)
        self.assertEqual(recent[0]["results_count"], 87)
        self.assertEqual(recent[0]["pages_fetched"], 5)
        self.assertEqual(recent[0]["stopped_reason"], "limit_reached")
        self.assertTrue(recent[0]["completed_at"])  # ISO string for timestamp

        # Ensure ordering by completion timestamp
        self.assertEqual(recent[1]["query_text"], "site:hiqa.ie diabetes")

        # Limit to top 3 entries
        self.assertLessEqual(len(recent), 3)

    def test_quick_status_handles_absent_running_query(self):
        """Current query should be null when no execution is running."""
        self.execution_running.status = "completed"
        self.execution_running.completed_at = timezone.now()
        self.execution_running.save()

        url = reverse(
            "serp_execution:session_quick_status_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIsNone(data["current_query"])
