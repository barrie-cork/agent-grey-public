"""
Tests for custom model managers in review_manager app.

Tests the SearchSessionQuerySet and SearchSessionManager for:
- Query optimization
- Annotation correctness
- Performance improvements
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SearchSessionManagerTests(TestCase):
    """Test custom SearchSession manager methods."""

    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = create_test_user(username_prefix="test@example.com")

        # Create multiple sessions with different statuses
        self.sessions = []
        statuses = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
            "archived",
        ]

        for i, status in enumerate(statuses):
            session = SearchSession.objects.create(
                title=f"Test Session {i}",
                description=f"Test session with status {status}",
                owner=self.user,
                status=status,
                total_results=100 * (i + 1),
                reviewed_results=50 * i,
            )

            # Create associated strategy
            strategy = SearchStrategy.objects.create(
                session=session,
                user=self.user,
                population_terms=["test population"],
                interest_terms=["test interest"],
                context_terms=["test context"],
            )

            # Create queries (is_active=False to avoid triggering auto-transition signal)
            query_ids = []
            for j in range(3):
                q = SearchQuery.objects.create(
                    strategy=strategy,
                    session=session,
                    query_text=f"test query {j}",
                    is_active=False,
                )
                query_ids.append(q.id)
            # Activate first 2 queries without triggering signal
            SearchQuery.objects.filter(id__in=query_ids[:2]).update(is_active=True)

            self.sessions.append(session)

    def test_with_statistics_annotation(self):
        """Test with_statistics() adds correct annotations."""
        sessions = SearchSession.objects.with_statistics()

        for session in sessions:
            # Check annotations exist
            self.assertTrue(hasattr(session, "query_count"))
            self.assertTrue(hasattr(session, "execution_count"))
            self.assertTrue(hasattr(session, "pending_reviews"))
            self.assertTrue(hasattr(session, "completion_percentage"))

            # Verify query_count (only active queries)
            self.assertEqual(session.query_count, 2)

            # Verify pending_reviews calculation
            expected_pending = session.total_results - session.reviewed_results
            self.assertEqual(session.pending_reviews, expected_pending)

    def test_active_filter(self):
        """Test active_only() filter returns correct sessions."""
        active_sessions = SearchSession.objects.active_only()

        # Should include all statuses except completed and archived
        expected_statuses = {
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
        }

        for session in active_sessions:
            self.assertIn(session.status, expected_statuses)

        # Should not include completed or archived
        self.assertNotIn("completed", [s.status for s in active_sessions])
        self.assertNotIn("archived", [s.status for s in active_sessions])

    def test_owned_by_filter(self):
        """Test owned_by() filter."""
        # Create another user with sessions
        other_user = create_test_user(username_prefix="other@example.com")
        SearchSession.objects.create(
            title="Other User Session", owner=other_user, status="draft"
        )

        # Test filtering by user
        user_sessions = SearchSession.objects.owned_by(self.user)
        self.assertEqual(user_sessions.count(), len(self.sessions))

        for session in user_sessions:
            self.assertEqual(session.owner, self.user)

    def test_for_dashboard_optimization(self):
        """Test for_dashboard() includes all optimizations."""
        sessions = SearchSession.objects.for_dashboard()

        # Check that statistics are included
        first_session = sessions.first()
        self.assertTrue(hasattr(first_session, "query_count"))
        self.assertTrue(hasattr(first_session, "pending_reviews"))

        # Verify queryset has select_related
        self.assertIn("owner", sessions.query.select_related)

        # Verify prefetch_related is set up
        self.assertTrue(
            len(sessions._prefetch_related_lookups) > 0,
            "Expected prefetch_related lookups to be configured",
        )

    def test_completion_percentage_calculation(self):
        """Test completion percentage calculation is correct."""
        sessions = SearchSession.objects.with_statistics()

        for session in sessions:
            if session.total_results > 0:
                expected_percentage = (
                    session.reviewed_results * 100.0 / session.total_results
                )
                self.assertAlmostEqual(
                    session.completion_percentage, expected_percentage, places=2
                )
            else:
                self.assertEqual(session.completion_percentage, 0)

    def test_query_performance(self):
        """Test that optimized queries reduce database hits."""
        # Reset queries
        from django.db import connection
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            # Clear query log
            connection.queries_log.clear()

            # Unoptimized query
            sessions = list(SearchSession.objects.all())
            for session in sessions:
                # This would trigger additional queries
                _ = session.search_strategy.search_queries.filter(
                    is_active=True
                ).count()

            unoptimized_count = len(connection.queries)

            # Clear again
            connection.queries_log.clear()

            # Optimized query
            sessions = list(SearchSession.objects.for_dashboard())
            for session in sessions:
                # This should not trigger additional queries
                _ = session.query_count

            optimized_count = len(connection.queries)

            # Optimized should have significantly fewer queries
            self.assertLess(optimized_count, unoptimized_count)
            # Should ideally be just 1-3 queries total
            self.assertLessEqual(optimized_count, 3)


class SearchSessionManagerErrorHandlingTests(TestCase):
    """Test error handling in custom managers."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user(username_prefix="test@example.com")

    def test_empty_queryset_handling(self):
        """Test managers work correctly with empty querysets."""
        # No sessions exist
        self.assertEqual(SearchSession.objects.count(), 0)

        # Methods should return empty querysets without errors
        self.assertEqual(SearchSession.objects.active_only().count(), 0)
        self.assertEqual(SearchSession.objects.with_statistics().count(), 0)
        self.assertEqual(SearchSession.objects.for_dashboard().count(), 0)

    def test_null_value_handling(self):
        """Test handling of null values in annotations."""
        # Create session with null/zero values
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            status="draft",
            total_results=0,
            reviewed_results=0,
        )

        # Get with statistics
        annotated = SearchSession.objects.with_statistics().get(id=session.id)

        # Should handle zero division
        self.assertEqual(annotated.completion_percentage, 0)
        self.assertEqual(annotated.pending_reviews, 0)
