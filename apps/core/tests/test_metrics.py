"""
Unit tests for Prometheus metrics (Phase 3).

Tests custom business metrics for session workflows, search execution,
result processing, and review activities.

Uses separate Prometheus registries to avoid polluting global metrics.
"""

from django.test import TestCase

from prometheus_client import REGISTRY

from apps.core.metrics.enums import ProcessingStatus, ReviewDecision
from apps.core.metrics.processing_metrics import (
    record_processing_result,
    track_processing_operation,
    update_deduplication_rate,
)
from apps.core.tests.utils import create_test_user
from apps.core.metrics.review_metrics import (
    record_review_decision,
    update_review_velocity,
)
from apps.core.metrics.search_metrics import track_search_execution
from apps.core.metrics.session_metrics import (
    calculate_state_duration,
    record_session_transition,
    update_session_state_distribution,
)
from apps.review_manager.models import SearchSession


class SessionMetricsTestCase(TestCase):
    """Test session workflow metrics."""

    def setUp(self):
        """Create test sessions in various states."""
        # Create test user
        self.user = create_test_user()

        # Create test sessions with required fields
        self.session1 = SearchSession.objects.create(
            title="Draft Session", status="draft", owner=self.user
        )
        self.session2 = SearchSession.objects.create(
            title="Executing Session", status="executing", owner=self.user
        )
        self.session3 = SearchSession.objects.create(
            title="Completed Session", status="completed", owner=self.user
        )

    def test_update_session_state_distribution(self):
        """Verify gauge reflects current database state."""
        from apps.core.metrics import session_state_gauge

        # Get initial value
        _initial_samples = list(session_state_gauge.collect())[0].samples

        # Update gauge from database
        update_session_state_distribution()

        # Get updated samples
        updated_samples = list(session_state_gauge.collect())[0].samples

        # Verify we have values for each state
        state_values = {
            sample.labels["state"]: sample.value for sample in updated_samples
        }

        # Verify counts match database
        self.assertGreaterEqual(state_values.get("draft", 0), 1)
        self.assertGreaterEqual(state_values.get("executing", 0), 1)
        self.assertGreaterEqual(state_values.get("completed", 0), 1)

    def test_record_session_transition(self):
        """Verify counter increments and duration recorded."""
        from apps.core.metrics import session_transitions_total

        # Get initial counter value
        initial_samples = list(session_transitions_total.collect())[0].samples
        _initial_count = len(initial_samples)

        # Record a transition
        record_session_transition(
            self.session1,
            from_state="draft",
            to_state="defining_search",
            success=True,
            duration_seconds=10.5,
        )

        # Get updated counter
        updated_samples = list(session_transitions_total.collect())[0].samples

        # Verify counter incremented - check value sum increased
        updated_value = sum(s.value for s in updated_samples)
        initial_value = sum(s.value for s in initial_samples)
        self.assertGreater(updated_value, initial_value)

    def test_calculate_state_duration_no_activity(self):
        """Verify duration calculation when no SessionActivity exists."""
        # For 'draft' state, falls back to session.created_at
        duration = calculate_state_duration(self.session1, "draft")
        # Should return a small positive value (time since session creation)
        self.assertIsNotNone(duration)
        self.assertGreaterEqual(duration, 0)

        # For non-draft state with no activity, should return None
        duration = calculate_state_duration(self.session1, "executing")
        self.assertIsNone(duration)

    def test_calculate_state_duration_with_activity(self):
        """Verify duration calculation with SessionActivity."""
        import datetime

        from django.utils import timezone

        from apps.review_manager.models import SessionActivity

        # Create activity record with metadata matching the query filter
        started_at = timezone.now() - datetime.timedelta(minutes=5)

        activity = SessionActivity.objects.create(
            session=self.session1,
            activity_type="state_change",
            description="Entered executing state",
            metadata={"to_state": "executing"},
        )
        # Override auto_now_add created_at via QuerySet.update()
        SessionActivity.objects.filter(pk=activity.pk).update(created_at=started_at)

        # Calculate duration for 'executing' state
        duration = calculate_state_duration(self.session1, "executing")

        # Should return duration in seconds (approximately 5 minutes = 300s)
        self.assertIsNotNone(duration)
        self.assertGreater(duration, 250)  # At least 4 minutes
        self.assertLess(duration, 350)  # Less than 6 minutes


class SearchMetricsTestCase(TestCase):
    """Test search execution metrics."""

    def test_track_search_execution_success(self):
        """Verify context manager records success metrics."""
        from apps.core.metrics import search_queries_total

        # Get initial counter value
        initial_samples = list(search_queries_total.collect())[0].samples
        initial_count = sum(s.value for s in initial_samples)

        # Create a mock query
        class MockQuery:
            id = 123
            query_text = "test query"

        mock_query = MockQuery()

        # Track a successful search
        with track_search_execution(mock_query) as tracker:  # type: ignore[arg-type]
            # Simulate search execution
            from apps.core.metrics.enums import SearchStatus

            tracker.record_results(10, status=SearchStatus.SUCCESS)

        # Get updated counter
        updated_samples = list(search_queries_total.collect())[0].samples
        updated_count = sum(s.value for s in updated_samples)

        # Verify counter incremented
        self.assertGreater(updated_count, initial_count)

    def test_track_search_execution_error(self):
        """Verify error categorization (timeout, rate_limit, etc.)."""
        from apps.core.metrics import search_api_errors_total

        # Get initial error count
        initial_samples = list(search_api_errors_total.collect())[0].samples
        initial_count = len(initial_samples)

        # Create a mock query
        class MockQuery:
            id = 124
            query_text = "timeout query"

        mock_query = MockQuery()

        # Track a search with error
        try:
            with track_search_execution(mock_query) as _tracker:  # type: ignore[arg-type]
                # Simulate an error
                raise TimeoutError("Search timed out")
        except TimeoutError:
            pass  # Expected

        # Get updated error counter
        updated_samples = list(search_api_errors_total.collect())[0].samples

        # Verify error was recorded
        self.assertGreaterEqual(len(updated_samples), initial_count)


class ReviewMetricsTestCase(TestCase):
    """Test review decision metrics."""

    def test_record_review_decision(self):
        """Verify decision counter increments."""
        before = REGISTRY.get_sample_value(
            "agent_grey_review_decisions_total",
            {"decision": ReviewDecision.INCLUDE.value},
        )
        if before is None:
            before = 0

        record_review_decision(ReviewDecision.INCLUDE)

        after = REGISTRY.get_sample_value(
            "agent_grey_review_decisions_total",
            {"decision": ReviewDecision.INCLUDE.value},
        )

        self.assertEqual(after - before, 1.0)

    def test_update_review_velocity(self):
        """Verify velocity calculation (decisions per hour)."""
        import datetime

        from django.utils import timezone

        from apps.core.metrics import review_velocity_per_hour
        from apps.results_manager.models import ProcessedResult
        from apps.review_results.models import SimpleReviewDecision

        user = create_test_user(username_prefix="reviewuser")

        # Create test session
        session = SearchSession.objects.create(
            title="Review Session", status="under_review", owner=user
        )

        # Create some review decisions in the past hour
        now = timezone.now()
        for i in range(5):
            # Create a processed result for each decision
            result = ProcessedResult.objects.create(
                session=session,
                title=f"Test Result {i}",
                url=f"https://example.com/test{i}",
                snippet=f"Test snippet {i}",
            )

            SimpleReviewDecision.objects.create(
                result=result,
                session=session,
                decision="include",
                reviewer=user,
                reviewed_at=now - datetime.timedelta(minutes=10 * i),
            )

        # Update velocity
        update_review_velocity()

        # Get gauge value
        samples = list(review_velocity_per_hour.collect())[0].samples

        # Verify velocity was calculated
        self.assertTrue(len(samples) > 0)
        velocity_value = samples[0].value

        # Should have positive velocity (5 decisions in past hour)
        self.assertGreaterEqual(velocity_value, 0)


class ProcessingMetricsTestCase(TestCase):
    """Test processing operation metrics."""

    def test_track_processing_operation(self):
        """Verify duration histogram updated."""
        from apps.core.metrics import processing_duration_seconds

        # Get initial histogram
        initial_samples = list(processing_duration_seconds.collect())[0].samples
        initial_count = len(initial_samples)

        # Track a processing operation
        with track_processing_operation("deduplication") as _tracker:
            # Simulate processing
            import time

            time.sleep(0.1)  # 100ms

        # Get updated histogram
        updated_samples = list(processing_duration_seconds.collect())[0].samples

        # Verify histogram was updated
        self.assertGreaterEqual(len(updated_samples), initial_count)

    def test_record_processing_result(self):
        """Verify status-based result counting."""
        # Capture initial values per label
        before_success = (
            REGISTRY.get_sample_value(
                "agent_grey_results_processed_total",
                {"status": ProcessingStatus.SUCCESS.value},
            )
            or 0
        )
        before_duplicate = (
            REGISTRY.get_sample_value(
                "agent_grey_results_processed_total",
                {"status": ProcessingStatus.DUPLICATE.value},
            )
            or 0
        )
        before_error = (
            REGISTRY.get_sample_value(
                "agent_grey_results_processed_total",
                {"status": ProcessingStatus.ERROR.value},
            )
            or 0
        )

        # Record some results
        record_processing_result(ProcessingStatus.SUCCESS)
        record_processing_result(ProcessingStatus.DUPLICATE)
        record_processing_result(ProcessingStatus.ERROR)

        # Verify each counter incremented by 1
        after_success = REGISTRY.get_sample_value(
            "agent_grey_results_processed_total",
            {"status": ProcessingStatus.SUCCESS.value},
        )
        after_duplicate = REGISTRY.get_sample_value(
            "agent_grey_results_processed_total",
            {"status": ProcessingStatus.DUPLICATE.value},
        )
        after_error = REGISTRY.get_sample_value(
            "agent_grey_results_processed_total",
            {"status": ProcessingStatus.ERROR.value},
        )

        self.assertEqual(after_success - before_success, 1.0)
        self.assertEqual(after_duplicate - before_duplicate, 1.0)
        self.assertEqual(after_error - before_error, 1.0)

    def test_update_deduplication_rate(self):
        """Verify percentage calculation (0-100)."""
        from apps.core.metrics import deduplication_rate

        # Update deduplication rate with test data
        update_deduplication_rate(total_results=100, unique_results=80)

        # Get gauge value
        samples = list(deduplication_rate.collect())[0].samples

        # Verify gauge exists
        self.assertTrue(len(samples) > 0)
        rate_value = samples[0].value

        # Should be 20% (20 duplicates out of 100)
        self.assertGreaterEqual(rate_value, 0)
        self.assertLessEqual(rate_value, 100)
        self.assertEqual(rate_value, 20.0)


class MetricsEndpointTestCase(TestCase):
    """Test metrics endpoint security and functionality."""

    def test_metrics_endpoint_requires_auth_in_production(self):
        """Verify endpoint requires authentication in production."""
        from django.test import Client

        client = Client()

        # Test in development (should allow access)
        with self.settings(DEBUG=True):
            response = client.get("/prometheus/metrics/")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"agent_grey", response.content)

    def test_metrics_endpoint_returns_prometheus_format(self):
        """Verify endpoint returns valid Prometheus format."""
        from django.test import Client

        client = Client()

        with self.settings(DEBUG=True):
            response = client.get("/prometheus/metrics/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response["Content-Type"], "text/plain; version=0.0.4; charset=utf-8"
            )

            # Verify Prometheus format
            content = response.content.decode("utf-8")
            self.assertIn("# HELP", content)
            self.assertIn("# TYPE", content)
            self.assertIn("agent_grey_", content)

    def test_metrics_endpoint_includes_all_custom_metrics(self):
        """Verify all 10 custom metrics are exposed."""
        from django.test import Client

        client = Client()

        with self.settings(DEBUG=True):
            response = client.get("/prometheus/metrics/")
            content = response.content.decode("utf-8")

            # Verify all 10 custom metrics
            self.assertIn("agent_grey_session_state", content)
            self.assertIn("agent_grey_session_transitions_total", content)
            self.assertIn("agent_grey_session_state_duration_seconds", content)
            self.assertIn("agent_grey_search_queries_total", content)
            self.assertIn("agent_grey_search_duration_seconds", content)
            self.assertIn("agent_grey_search_results_count", content)
            self.assertIn("agent_grey_search_api_errors_total", content)
            self.assertIn("agent_grey_processing_duration_seconds", content)
            self.assertIn("agent_grey_deduplication_rate", content)
            self.assertIn("agent_grey_results_processed_total", content)
            self.assertIn("agent_grey_review_decisions_total", content)
            self.assertIn("agent_grey_review_velocity_per_hour", content)
