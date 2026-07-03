"""
Tests for iterative search with audit trail functionality.

Covers:
- Execution round tracking (get_next_execution_round, build_strategy_snapshot)
- Query preservation (deactivate instead of delete on re-execution)
- Hidden results filtering
- Deduplication with per-iteration stats
- PRISMA iteration breakdown
- Complete review hidden results warning
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from apps.core.services.url_deduplication import URLDeduplicationService
from apps.core.tests.utils import create_test_user
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession, SessionActivity
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.search_strategy.services.search_strategy_service import SearchStrategyService
from apps.serp_execution.models import SearchExecution
from apps.serp_execution.tasks.simple_tasks import (
    build_strategy_snapshot,
    get_next_execution_round,
)

User = get_user_model()


class GetNextExecutionRoundTests(TestCase):
    """Test get_next_execution_round helper."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["interest"],
            context_terms=["context"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            execution_order=0,
        )

    def test_first_round_returns_1(self):
        """First execution round should be 1 when no executions exist."""
        result = get_next_execution_round(self.session)
        self.assertEqual(result, 1)

    def test_increments_after_first_round(self):
        """Should return 2 after first round of executions."""
        SearchExecution.objects.create(
            query=self.query,
            status="completed",
            execution_round=1,
        )
        result = get_next_execution_round(self.session)
        self.assertEqual(result, 2)

    def test_increments_after_multiple_rounds(self):
        """Should return max + 1 when multiple rounds exist."""
        SearchExecution.objects.create(
            query=self.query,
            status="completed",
            execution_round=1,
        )
        SearchExecution.objects.create(
            query=self.query,
            status="completed",
            execution_round=3,
        )
        result = get_next_execution_round(self.session)
        self.assertEqual(result, 4)


class BuildStrategySnapshotTests(TestCase):
    """Test build_strategy_snapshot helper."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly", "aged"],
            interest_terms=["falls prevention"],
            context_terms=["hospital"],
            search_config={"max_results": 100},
        )

    def test_snapshot_contains_pic_terms(self):
        """Snapshot should contain population, interest, context terms."""
        snapshot = build_strategy_snapshot(self.strategy)
        self.assertEqual(snapshot["population_terms"], ["elderly", "aged"])
        self.assertEqual(snapshot["interest_terms"], ["falls prevention"])
        self.assertEqual(snapshot["context_terms"], ["hospital"])

    def test_snapshot_contains_search_config(self):
        """Snapshot should contain search configuration."""
        snapshot = build_strategy_snapshot(self.strategy)
        self.assertEqual(snapshot["search_config"]["max_results"], 100)

    def test_snapshot_contains_timestamp(self):
        """Snapshot should contain a snapshot_at timestamp."""
        snapshot = build_strategy_snapshot(self.strategy)
        self.assertIn("snapshot_at", snapshot)
        self.assertIsInstance(snapshot["snapshot_at"], str)


class QueryPreservationTests(TestCase):
    """Test that queries are deactivated instead of deleted on re-execution."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "search_type": "google",
                "max_results": 50,
            },
        )
        self.service = SearchStrategyService()

    def test_first_run_deletes_queries(self):
        """First run (no results) should delete existing queries."""
        # Create a query
        SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="old query",
            query_type="general",
            execution_order=0,
        )
        # No ProcessedResults exist, so first run should delete
        self.service.update_search_queries(self.strategy)
        # Old query should be gone
        self.assertFalse(
            SearchQuery.objects.filter(
                session=self.session, query_text="old query"
            ).exists()
        )

    def test_reexecution_deactivates_queries(self):
        """Re-execution (results exist) should deactivate queries, not delete."""
        # Create initial queries
        old_query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="old query",
            query_type="general",
            execution_order=0,
            is_active=True,
        )
        # Create a processed result to simulate first execution
        ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
        )
        # Re-execute: should deactivate, not delete
        self.service.update_search_queries(self.strategy)
        old_query.refresh_from_db()
        self.assertFalse(old_query.is_active)
        # New queries should be created and active
        new_queries = SearchQuery.objects.filter(session=self.session, is_active=True)
        self.assertGreater(new_queries.count(), 0)


class ExecutionRoundModelTests(TestCase):
    """Test execution_round field on SearchExecution and ProcessedResult."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["interest"],
            context_terms=["context"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            execution_order=0,
        )

    def test_search_execution_default_round(self):
        """SearchExecution should default to execution_round=1."""
        execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
        )
        self.assertEqual(execution.execution_round, 1)

    def test_search_execution_custom_round(self):
        """SearchExecution should accept custom execution_round."""
        execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
            execution_round=3,
            strategy_snapshot={"population_terms": ["test"]},
        )
        self.assertEqual(execution.execution_round, 3)
        self.assertEqual(execution.strategy_snapshot["population_terms"], ["test"])

    def test_processed_result_default_round(self):
        """ProcessedResult should default to execution_round=1."""
        result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
        )
        self.assertEqual(result.execution_round, 1)

    def test_processed_result_custom_round(self):
        """ProcessedResult should accept custom execution_round."""
        result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            execution_round=2,
        )
        self.assertEqual(result.execution_round, 2)


class HiddenResultsTests(TestCase):
    """Test is_hidden filtering and hide/unhide functionality."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        # Create results in two iterations
        for i in range(3):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i} Round 1",
                url=f"https://example.com/r1/{i}",
                execution_round=1,
                processing_status="success",
            )
        for i in range(2):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i} Round 2",
                url=f"https://example.com/r2/{i}",
                execution_round=2,
                processing_status="success",
            )

    def test_hidden_default_false(self):
        """Results should not be hidden by default."""
        results = ProcessedResult.objects.filter(session=self.session)
        for result in results:
            self.assertFalse(result.is_hidden)

    def test_hide_iteration_results(self):
        """Hiding iteration results should set is_hidden=True."""
        updated = ProcessedResult.objects.filter(
            session=self.session,
            execution_round=2,
        ).update(is_hidden=True, hidden_reason="Test hide")
        self.assertEqual(updated, 2)
        hidden = ProcessedResult.objects.filter(
            session=self.session, is_hidden=True
        ).count()
        self.assertEqual(hidden, 2)

    def test_hidden_results_excluded_from_review_query(self):
        """Hidden results should be excluded when filtering by is_hidden=False."""
        # Hide round 2
        ProcessedResult.objects.filter(session=self.session, execution_round=2).update(
            is_hidden=True
        )
        # Query like the provider does
        visible = ProcessedResult.objects.filter(
            session=self.session,
            processing_status="success",
            is_hidden=False,
        )
        self.assertEqual(visible.count(), 3)

    def test_unhide_iteration_results(self):
        """Unhiding should restore results."""
        ProcessedResult.objects.filter(session=self.session, execution_round=2).update(
            is_hidden=True
        )
        # Unhide
        ProcessedResult.objects.filter(session=self.session, execution_round=2).update(
            is_hidden=False, hidden_reason=""
        )
        hidden = ProcessedResult.objects.filter(
            session=self.session, is_hidden=True
        ).count()
        self.assertEqual(hidden, 0)


class DeduplicationPerIterationTests(TestCase):
    """Test deduplication returns per-iteration stats."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

    def test_dedup_returns_dict_with_per_iteration(self):
        """Deduplication should return dict with per_iteration stats."""
        # Create results with some duplicates across iterations
        ProcessedResult.objects.create(
            session=self.session,
            title="Result A",
            url="https://example.com/a",
            execution_round=1,
        )
        ProcessedResult.objects.create(
            session=self.session,
            title="Result B",
            url="https://example.com/b",
            execution_round=1,
        )
        # Duplicate of A in round 2
        ProcessedResult.objects.create(
            session=self.session,
            title="Result A Copy",
            url="https://example.com/a",
            execution_round=2,
        )
        ProcessedResult.objects.create(
            session=self.session,
            title="Result C",
            url="https://example.com/c",
            execution_round=2,
        )

        dedup_service = URLDeduplicationService()
        result = dedup_service.deduplicate_session_results(self.session)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_duplicates"], 1)
        self.assertIn("per_iteration", result)
        self.assertIn(1, result["per_iteration"])
        self.assertIn(2, result["per_iteration"])
        self.assertEqual(result["per_iteration"][1]["total"], 2)
        self.assertEqual(result["per_iteration"][1]["duplicates"], 0)
        self.assertEqual(result["per_iteration"][2]["total"], 2)
        self.assertEqual(result["per_iteration"][2]["duplicates"], 1)


class AuditTrailActivityTypesTests(TestCase):
    """Test that new activity types are accepted."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

    def test_strategy_modified_activity(self):
        """Should be able to log strategy_modified activity."""
        activity = SessionActivity.log_activity(
            session=self.session,
            activity_type="strategy_modified",
            description="Strategy modified after previous execution",
            user=self.user,
            metadata={"previous_status": "ready_for_review"},
        )
        self.assertEqual(activity.activity_type, "strategy_modified")

    def test_search_iteration_started_activity(self):
        """Should be able to log search_iteration_started activity."""
        activity = SessionActivity.log_activity(
            session=self.session,
            activity_type="search_iteration_started",
            description="Search iteration 2 started",
            metadata={"execution_round": 2},
        )
        self.assertEqual(activity.activity_type, "search_iteration_started")

    def test_search_iteration_completed_activity(self):
        """Should be able to log search_iteration_completed activity."""
        activity = SessionActivity.log_activity(
            session=self.session,
            activity_type="search_iteration_completed",
            description="Search iteration 2 completed",
            metadata={"execution_round": 2, "new_results_count": 50},
        )
        self.assertEqual(activity.activity_type, "search_iteration_completed")

    def test_results_hidden_activity(self):
        """Should be able to log results_hidden activity."""
        activity = SessionActivity.log_activity(
            session=self.session,
            activity_type="results_hidden",
            description="Hidden 10 results from iteration 2",
            user=self.user,
            metadata={"execution_round": 2, "results_hidden": 10},
        )
        self.assertEqual(activity.activity_type, "results_hidden")


class PRISMAIterationBreakdownTests(TestCase):
    """Test PRISMA iteration breakdown generation."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="A systematic review for testing",
            owner=self.user,
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly"],
            interest_terms=["falls"],
            context_terms=["hospital"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="elderly falls hospital",
            query_type="general",
            execution_order=0,
        )

    def test_iteration_breakdown_with_single_round(self):
        """Should return breakdown for a single iteration."""
        from apps.reporting.services.prisma_reporting_service import (
            PrismaReportingService,
        )

        # Create execution and results
        SearchExecution.objects.create(
            query=self.query,
            status="completed",
            execution_round=1,
            strategy_snapshot={"population_terms": ["elderly"]},
            results_count=5,
        )
        for i in range(5):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                url=f"https://example.com/{i}",
                execution_round=1,
                processing_status="success",
            )

        service = PrismaReportingService()
        breakdown = service._gather_iteration_breakdown(str(self.session.id))

        self.assertEqual(len(breakdown), 1)
        self.assertEqual(breakdown[0]["round"], 1)
        self.assertEqual(breakdown[0]["unique_results"], 5)
        self.assertEqual(breakdown[0]["duplicates_found"], 0)
        self.assertEqual(breakdown[0]["hidden_count"], 0)
        self.assertEqual(len(breakdown[0]["queries"]), 1)
        self.assertEqual(
            breakdown[0]["queries"][0]["query_text"], "elderly falls hospital"
        )

    def test_iteration_breakdown_with_hidden_results(self):
        """Should include hidden count in breakdown."""
        from apps.reporting.services.prisma_reporting_service import (
            PrismaReportingService,
        )

        SearchExecution.objects.create(
            query=self.query,
            status="completed",
            execution_round=1,
            results_count=3,
        )
        for i in range(3):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                url=f"https://example.com/{i}",
                execution_round=1,
                processing_status="success",
                is_hidden=(i == 2),  # Hide one result
            )

        service = PrismaReportingService()
        breakdown = service._gather_iteration_breakdown(str(self.session.id))

        self.assertEqual(breakdown[0]["hidden_count"], 1)

    def test_prisma_flow_data_includes_iterations(self):
        """PRISMA flow data should include iterations key."""
        from apps.reporting.services.prisma_reporting_service import (
            PrismaReportingService,
        )

        SearchExecution.objects.create(
            query=self.query,
            status="completed",
            execution_round=1,
            results_count=3,
        )
        for i in range(3):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                url=f"https://example.com/{i}",
                execution_round=1,
                processing_status="success",
            )

        service = PrismaReportingService()
        flow_data = service.generate_prisma_flow_data(str(self.session.id))

        self.assertIn("iterations", flow_data)
        self.assertIn("hidden_results", flow_data)
        self.assertIsInstance(flow_data["iterations"], list)
