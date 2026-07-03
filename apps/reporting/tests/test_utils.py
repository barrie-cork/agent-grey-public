"""
Utility functions and helpers for reporting app tests.

This module provides common test utilities, fixtures, and mock helpers
for testing report generation and export functionality.
"""

from datetime import timedelta
from unittest.mock import Mock

from django.utils import timezone

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution


class MockWeasyPrint:
    """Mock WeasyPrint HTML class for testing PDF generation."""

    def __init__(self, string=None, url=None, filename=None, encoding=None):
        """Initialize mock HTML object."""
        self.string = string
        self.url = url
        self.filename = filename
        self.encoding = encoding
        self._pdf_content = b"Mock PDF content"

    def write_pdf(self, target=None, stylesheets=None, **options):
        """Mock write_pdf method."""
        if target:
            # Write to file
            with open(target, "wb") as f:
                f.write(self._pdf_content)
            return None
        # Return bytes
        return self._pdf_content

    def set_pdf_content(self, content):
        """Set custom PDF content for testing."""
        self._pdf_content = content


class TestDataBuilder:
    """Helper class to build comprehensive test data."""

    def __init__(self, user, session=None):
        """Initialize builder with user and optional session."""
        self.user = user
        self.session = session or self._create_session()
        self.queries = []
        self.executions = []
        self.raw_results = []
        self.processed_results = []
        self.review_decisions = []

    def _create_session(self):
        """Create a default session."""
        return SearchSession.objects.create(
            title="Test Session",
            description="Test Description",
            owner=self.user,
            status="completed",
        )

    def create_search_strategy(self, num_concepts=3, synonyms_per_concept=3):
        """Create PIC search strategy using ArrayField terms."""
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=[
                f"Test Population synonym {j}" for j in range(synonyms_per_concept)
            ],
            interest_terms=[
                f"Test Interest synonym {j}" for j in range(synonyms_per_concept)
            ],
            context_terms=[
                f"Test Context synonym {j}" for j in range(synonyms_per_concept)
            ],
        )

    def create_search_queries(self, num_queries=3):
        """Create search queries."""
        for i in range(num_queries):
            query = SearchQuery.objects.create(
                strategy=self.strategy,
                session=self.session,
                query_text=f"test query {i} with boolean AND operators",
                is_active=(i == num_queries - 1),  # Last one active
            )
            self.queries.append(query)
        return self.queries

    def create_search_executions(self, results_per_execution=10):
        """Create search executions with results."""
        for query in self.queries:
            execution = SearchExecution.objects.create(
                query=query,
                status="completed",
                results_count=results_per_execution,
                duration_seconds=1.2,
                started_at=timezone.now() - timedelta(hours=2),
                completed_at=timezone.now() - timedelta(hours=1),
            )
            self.executions.append(execution)

            # Create raw results
            for i in range(results_per_execution):
                raw = RawSearchResult.objects.create(
                    execution=execution,
                    position=i + 1,
                    title=f"Result {i} for {query.query_text}",
                    link=f"https://example.com/{query.id}/{i}",
                    snippet=f"Snippet for result {i}",
                    source=f"Source {i % 3}",
                )
                self.raw_results.append(raw)

        return self.executions

    def create_processed_results(self, duplicate_rate=0.2):
        """Create processed results with some duplicates."""
        _seen_urls = set()

        for i, raw in enumerate(self.raw_results):
            # Determine if duplicate
            _is_duplicate = i / len(self.raw_results) < duplicate_rate and i > 0

            processed = ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw,
                title=raw.title,
                url=raw.link,
                snippet=raw.snippet,
            )
            self.processed_results.append(processed)

        return self.processed_results

    def create_review_decisions(self, review_rate=0.8, include_rate=0.7):
        """Create review decisions for processed results."""
        num_to_review = int(len(self.processed_results) * review_rate)

        for i, result in enumerate(self.processed_results[:num_to_review]):
            # Determine decision based on include rate
            decision = "include" if (i / num_to_review) < include_rate else "exclude"
            review = SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.user,
                decision=decision,
                exclusion_reason="not_relevant" if decision == "exclude" else "",
            )
            self.review_decisions.append(review)

        return self.review_decisions

    def build_complete_dataset(self):
        """Build a complete dataset for testing."""
        self.create_search_strategy()
        self.create_search_queries()
        self.create_search_executions()
        self.create_processed_results()
        self.create_review_decisions()

        return {
            "session": self.session,
            "queries": self.queries,
            "executions": self.executions,
            "raw_results": self.raw_results,
            "processed_results": self.processed_results,
            "review_decisions": self.review_decisions,
        }


def create_mock_storage():
    """Create a mock storage backend for testing file operations."""
    storage = Mock()
    storage.exists.return_value = True
    storage.open.return_value = Mock()
    storage.save.return_value = "mocked/file/path.pdf"
    storage.delete.return_value = None
    storage.size.return_value = 1024

    return storage


def assert_prisma_flow_structure(test_case, flow_data):
    """Assert PRISMA flow data has correct structure."""
    # Check main sections
    test_case.assertIn("identification", flow_data)
    test_case.assertIn("screening", flow_data)
    test_case.assertIn("eligibility", flow_data)
    test_case.assertIn("included", flow_data)

    # Check identification phase
    identification = flow_data["identification"]
    test_case.assertIn("databases_searched", identification)
    test_case.assertIn("records_identified", identification)
    test_case.assertIn("other_sources", identification)
    test_case.assertIn("total_records", identification)

    # Check screening phase
    screening = flow_data["screening"]
    test_case.assertIn("records_after_duplicates", screening)
    test_case.assertIn("records_screened", screening)
    test_case.assertIn("records_excluded", screening)

    # Check eligibility phase
    eligibility = flow_data["eligibility"]
    test_case.assertIn("full_text_assessed", eligibility)
    test_case.assertIn("full_text_excluded", eligibility)
    test_case.assertIn("exclusion_reasons", eligibility)

    # Check included phase
    included = flow_data["included"]
    test_case.assertIn("studies_included", included)
    test_case.assertIn("studies_in_synthesis", included)


def assert_report_export_structure(test_case, export_data):
    """Assert report export data has correct structure."""
    # Common fields for most exports
    if isinstance(export_data, dict):
        # Check for session info if present
        if "session_info" in export_data:
            session_info = export_data["session_info"]
            test_case.assertIn("title", session_info)
            test_case.assertIn("created_at", session_info)

        # Check for summary if present
        if "summary" in export_data:
            summary = export_data["summary"]
            test_case.assertIsInstance(summary, dict)

        # Check for results if present
        if "results" in export_data:
            results = export_data["results"]
            test_case.assertIsInstance(results, (list, type(None)))


def create_sample_report_data():
    """Create sample data for report generation."""
    return {
        "session": {
            "title": "Test Session",
            "description": "Test Description",
            "created_at": timezone.now(),
        },
        "prisma_flow": {
            "identification": {"records_identified": 100, "databases_searched": 3},
            "included": {"studies_included": 25},
        },
        "result_statistics": {
            "total_results": 100,
            "included_count": 25,
            "excluded_count": 50,
            "pending_count": 25,
            "review_completion_percentage": 75.0,
        },
        "performance_metrics": {
            "total_queries": 5,
            "avg_response_time": 1.2,
            "success_rate": 95.0,
        },
    }


class MockCeleryTask:
    """Mock Celery task for testing async operations."""

    def __init__(self, task_id=None):
        """Initialize mock task."""
        self.id = task_id or "mock-task-id"
        self.status = "PENDING"
        self.result = None
        self.info = {}

    def delay(self, *args, **kwargs):
        """Mock delay method."""
        self.status = "STARTED"
        return self

    def apply_async(self, *args, **kwargs):
        """Mock apply_async method."""
        self.status = "STARTED"
        return self

    def get(self, timeout=None):
        """Mock get method."""
        if self.status == "SUCCESS":
            return self.result
        raise Exception("Task not complete")


def create_mock_form_data(report_type="full_report", export_format="pdf"):
    """Create valid form data for report generation."""
    return {
        "report_type": report_type,
        "export_format": export_format,
        "title": f"Test {report_type.replace('_', ' ').title()} Report",
        "include_appendices": True,
        "include_raw_data": False,
    }
