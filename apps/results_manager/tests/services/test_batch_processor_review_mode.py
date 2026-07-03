"""
Regression tests for issue #178: WF2 dual-screening degrades to SINGLE on
real SERP search.

The BatchProcessor must inherit review_mode / min_reviewers_required from the
session's active ReviewConfiguration rather than falling through to the model
defaults (SINGLE / 1).
"""

from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult, ProcessingSession
from apps.results_manager.services.processors.batch_processor import BatchProcessor
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution


class BatchProcessorReviewModeTest(TestCase):
    """Verify that BatchProcessor sets review_mode/min_reviewers from session config."""

    def setUp(self):
        self.org = Organisation.objects.create(
            name="BP Review Mode Org", slug="bp-review-mode-org"
        )
        self.user = create_test_user(username_prefix="bp_rm", email="bp_rm@test.com")
        OrganisationMembership.objects.create(
            organisation=self.org,
            user=self.user,
            role="RESEARCHER",
            is_active=True,
        )

    def _make_session(self, min_reviewers: int) -> SearchSession:
        session = SearchSession.objects.create(
            organisation=self.org,
            title=f"Review mode test (reviewers={min_reviewers})",
            owner=self.user,
            status="processing_results",
        )
        config = ReviewConfiguration.objects.create(
            session=session,
            min_reviewers_per_result=min_reviewers,
            version=1,
            organisation=self.org,
            created_by=self.user,
        )
        session.current_configuration = config
        session.save(update_fields=["current_configuration"])
        return session

    def _make_raw_results(self, session: SearchSession, count: int = 3):
        session_prefix = str(session.pk)[:8]
        strategy = SearchStrategy.objects.create(
            session=session,
            user=self.user,
            population_terms=["population"],
            interest_terms=["interest"],
            context_terms=["context"],
        )
        query = SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="test query",
            query_type="domain-specific",
            execution_order=1,
        )
        execution = SearchExecution.objects.create(
            query=query,
            search_engine="serper",
            status="completed",
        )
        return [
            RawSearchResult.objects.create(
                execution=execution,
                title=f"Result {i}",
                link=f"https://unique-{session_prefix}-{i}.test/article",
                snippet=f"Snippet {i}",
                position=i + 1,
            )
            for i in range(count)
        ]

    def _run_batch(
        self, session: SearchSession, raw_results: list
    ) -> list[ProcessedResult]:
        proc_session = ProcessingSession.objects.create(
            search_session=session,
            status="in_progress",
            total_raw_results=len(raw_results),
        )
        processor = BatchProcessor()
        processor.process_batch(
            session_id=str(session.id),
            raw_result_ids=[str(r.id) for r in raw_results],
            processing_session=proc_session,
        )
        return list(ProcessedResult.objects.filter(session=session))

    def test_wf2_session_results_get_dual_review_mode(self):
        """SERP pipeline must set DUAL/2 for WF2 (min_reviewers_per_result=2)."""
        session = self._make_session(min_reviewers=2)
        raw_results = self._make_raw_results(session, count=3)

        results = self._run_batch(session, raw_results)

        self.assertEqual(len(results), 3)
        for r in results:
            self.assertEqual(
                r.review_mode,
                "DUAL",
                f"Expected DUAL, got {r.review_mode} for {r.url}",
            )
            self.assertEqual(
                r.min_reviewers_required,
                2,
                f"Expected 2, got {r.min_reviewers_required} for {r.url}",
            )

    def test_wf1_session_results_get_single_review_mode(self):
        """SERP pipeline must leave SINGLE/1 unchanged for WF1 (min_reviewers_per_result=1)."""
        session = self._make_session(min_reviewers=1)
        raw_results = self._make_raw_results(session, count=3)

        results = self._run_batch(session, raw_results)

        self.assertEqual(len(results), 3)
        for r in results:
            self.assertEqual(r.review_mode, "SINGLE")
            self.assertEqual(r.min_reviewers_required, 1)

    def test_wf2_no_config_falls_back_to_single(self):
        """When current_configuration is None, pipeline falls back to SINGLE/1 safely."""
        session = SearchSession.objects.create(
            organisation=self.org,
            title="No config test",
            owner=self.user,
            status="processing_results",
        )
        # Deliberately leave current_configuration = None

        raw_results = self._make_raw_results(session, count=2)
        results = self._run_batch(session, raw_results)

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r.review_mode, "SINGLE")
            self.assertEqual(r.min_reviewers_required, 1)
