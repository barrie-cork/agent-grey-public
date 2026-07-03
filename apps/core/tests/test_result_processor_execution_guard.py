"""Tests for execution guard branches in SearchResultProcessor.process_search_results.

Covers lines 98-118 of result_processor.py:
- execution with query_id attribute -> query_id = execution.query_id
- execution is a str -> query_id = execution, then resolved via DB lookup
- execution is None -> query_id = None
"""

import uuid

from django.test import TestCase

from apps.core.services.result_processor import SearchResultProcessor
from apps.core.tests.utils import TestUserMixin
from apps.review_manager.models import SearchSession


def _create_execution(session, user):
    """Create a SearchExecution with required FK chain."""
    from apps.search_strategy.models import SearchQuery, SearchStrategy
    from apps.serp_execution.models import SearchExecution

    strategy = SearchStrategy.objects.create(
        session=session,
        user=user,
        population_terms=["test"],
        interest_terms=["test"],
        context_terms=["test"],
    )
    query = SearchQuery.objects.create(
        strategy=strategy,
        session=session,
        query_text="test query",
        query_type="general",
    )
    return SearchExecution.objects.create(
        query=query,
        status="completed",
    )


class ExecutionGuardTestCase(TestCase, TestUserMixin):
    """Test the execution/query_id guard branches in process_search_results."""

    def setUp(self):
        self.processor = SearchResultProcessor()
        self.user = self.create_test_user()
        self.session = SearchSession.objects.create(
            title="Guard Test Session",
            owner=self.user,
            status="processing_results",
        )
        self.single_result = [
            {
                "title": "Test Title",
                "link": "https://example.com/page",
                "snippet": "Test snippet",
            }
        ]

    # ------------------------------------------------------------------
    # Branch: execution is None (else branch, lines 103-104)
    # ------------------------------------------------------------------

    def test_execution_none_sets_query_id_none(self):
        """When execution is None, query_id resolves to None."""
        with self.assertLogs("SearchResultProcessor", level="INFO") as cm:
            processed, errors = self.processor.process_search_results(
                self.single_result,
                execution=None,
                session=self.session,
            )

        self.assertEqual(processed, 1)
        self.assertEqual(errors, [])
        self.assertTrue(
            any("query None" in msg for msg in cm.output),
            f"Expected 'query None' in log output, got: {cm.output}",
        )

    def test_execution_none_skips_raw_result_creation(self):
        """When execution is None, no RawSearchResult records are created."""
        from apps.serp_execution.models import RawSearchResult

        initial_count = RawSearchResult.objects.count()

        self.processor.process_search_results(
            self.single_result,
            execution=None,
            session=self.session,
        )

        self.assertEqual(
            RawSearchResult.objects.count(),
            initial_count,
            "RawSearchResult should not be created when execution is None",
        )

    # ------------------------------------------------------------------
    # Branch: execution is a str (elif branch, lines 101-102)
    # Then lines 107-118 resolve the string to a SearchExecution or None
    # ------------------------------------------------------------------

    def test_execution_string_not_found_sets_query_id_then_resolves_to_none(self):
        """When execution is a UUID string not in DB, query_id is set to
        that string, then execution resolves to None via DoesNotExist."""
        fake_uuid = str(uuid.uuid4())

        with self.assertLogs("SearchResultProcessor", level="INFO") as cm:
            processed, errors = self.processor.process_search_results(
                self.single_result,
                execution=fake_uuid,
                session=self.session,
            )

        # Result still processes via session (execution resolved to None)
        self.assertEqual(processed, 1)
        self.assertEqual(errors, [])
        # query_id was set to the string before resolution
        self.assertTrue(
            any(f"query {fake_uuid}" in msg for msg in cm.output),
            f"Expected 'query {fake_uuid}' in log output, got: {cm.output}",
        )

    def test_execution_string_not_found_skips_raw_result(self):
        """When execution string resolves to DoesNotExist, no RawSearchResult."""
        from apps.serp_execution.models import RawSearchResult

        initial_count = RawSearchResult.objects.count()

        self.processor.process_search_results(
            self.single_result,
            execution=str(uuid.uuid4()),
            session=self.session,
        )

        self.assertEqual(
            RawSearchResult.objects.count(),
            initial_count,
            "RawSearchResult should not be created when execution UUID not found",
        )

    def test_execution_string_found_resolves_and_creates_raw_result(self):
        """When execution is a UUID string of a real SearchExecution,
        it resolves to that object and RawSearchResult is created."""
        from apps.serp_execution.models import RawSearchResult

        execution = _create_execution(self.session, self.user)
        initial_count = RawSearchResult.objects.count()

        processed, errors = self.processor.process_search_results(
            self.single_result,
            execution=str(execution.id),
            session=self.session,
        )

        self.assertEqual(processed, 1)
        self.assertEqual(errors, [])
        self.assertEqual(
            RawSearchResult.objects.count(),
            initial_count + 1,
            "RawSearchResult should be created when execution UUID resolves",
        )

    # ------------------------------------------------------------------
    # Branch: execution has query_id attr (if branch, lines 99-100)
    # SearchExecution has query_id from the Django FK to SearchQuery.
    # ------------------------------------------------------------------

    def test_execution_object_uses_query_id_attribute(self):
        """When execution is a SearchExecution, query_id is its FK value."""
        execution = _create_execution(self.session, self.user)

        with self.assertLogs("SearchResultProcessor", level="INFO") as cm:
            processed, errors = self.processor.process_search_results(
                self.single_result,
                execution=execution,
                session=self.session,
            )

        self.assertEqual(processed, 1)
        self.assertEqual(errors, [])
        # query_id should be execution.query_id (the FK to SearchQuery)
        self.assertTrue(
            any(f"query {execution.query_id}" in msg for msg in cm.output),
            f"Expected 'query {execution.query_id}' in log, got: {cm.output}",
        )

    def test_execution_object_creates_raw_result(self):
        """When execution is a real SearchExecution, RawSearchResult is created."""
        from apps.serp_execution.models import RawSearchResult

        execution = _create_execution(self.session, self.user)
        initial_count = RawSearchResult.objects.count()

        processed, errors = self.processor.process_search_results(
            self.single_result,
            execution=execution,
            session=self.session,
        )

        self.assertEqual(processed, 1)
        self.assertEqual(errors, [])
        self.assertEqual(
            RawSearchResult.objects.count(),
            initial_count + 1,
        )

    # ------------------------------------------------------------------
    # Edge: execution is truthy object without query_id (else branch)
    # ------------------------------------------------------------------

    def test_execution_object_without_query_id_falls_to_none(self):
        """An object without query_id that isn't a string -> query_id = None."""
        execution_like = object()  # no query_id, not a str

        with self.assertLogs("SearchResultProcessor", level="INFO") as cm:
            processed, errors = self.processor.process_search_results(
                self.single_result,
                execution=execution_like,
                session=self.session,
            )

        # query_id is None
        self.assertTrue(
            any("query None" in msg for msg in cm.output),
            f"Expected 'query None' in log output, got: {cm.output}",
        )
        # execution is truthy so RawSearchResult.objects.create is attempted
        # but object() isn't a valid FK, causing per-result errors
        self.assertGreater(len(errors), 0)

    # ------------------------------------------------------------------
    # Edge: empty results with each execution variant
    # ------------------------------------------------------------------

    def test_empty_results_with_none_execution(self):
        """Empty results with execution=None returns (0, [])."""
        processed, errors = self.processor.process_search_results(
            [], execution=None, session=self.session
        )
        self.assertEqual(processed, 0)
        self.assertEqual(errors, [])

    def test_empty_results_with_string_execution(self):
        """Empty results with a UUID string execution returns (0, [])."""
        processed, errors = self.processor.process_search_results(
            [], execution=str(uuid.uuid4()), session=self.session
        )
        self.assertEqual(processed, 0)
        self.assertEqual(errors, [])

    def test_empty_results_with_object_execution(self):
        """Empty results with a real SearchExecution returns (0, [])."""
        execution = _create_execution(self.session, self.user)

        processed, errors = self.processor.process_search_results(
            [], execution=execution, session=self.session
        )
        self.assertEqual(processed, 0)
        self.assertEqual(errors, [])
