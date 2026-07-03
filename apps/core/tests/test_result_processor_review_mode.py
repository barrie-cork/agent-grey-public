"""Regression tests for issue #178 at the live create-path.

The real SERP pipeline creates ProcessedResult rows via
``SearchResultProcessor.process_search_results`` (dispatched by
``execute_search_session_simple``), NOT via BatchProcessor. Those rows must
inherit review_mode / min_reviewers_required from the session's active
ReviewConfiguration rather than falling through to the model defaults
(SINGLE / 1), or dual screening silently degrades to single.
"""

from django.test import TestCase

from apps.core.services.result_processor import SearchResultProcessor
from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession


class ProcessSearchResultsReviewModeTest(TestCase):
    """SearchResultProcessor must set review_mode/min_reviewers from session config."""

    def setUp(self):
        self.org = Organisation.objects.create(
            name="RP Review Mode Org", slug="rp-review-mode-org"
        )
        self.user = create_test_user(username_prefix="rp_rm", email="rp_rm@test.com")
        OrganisationMembership.objects.create(
            organisation=self.org,
            user=self.user,
            role="RESEARCHER",
            is_active=True,
        )
        self.processor = SearchResultProcessor()

    def _make_session(self, min_reviewers: int | None) -> SearchSession:
        session = SearchSession.objects.create(
            organisation=self.org,
            title=f"RP review mode (reviewers={min_reviewers})",
            owner=self.user,
            status="processing_results",
        )
        if min_reviewers is not None:
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

    @staticmethod
    def _raw_results(count: int = 3) -> list[dict]:
        return [
            {
                "title": f"Result {i}",
                "link": f"https://example.com/article-{i}",
                "snippet": f"Snippet {i}",
            }
            for i in range(count)
        ]

    def _process(self, session: SearchSession, count: int = 3) -> list[ProcessedResult]:
        processed, errors = self.processor.process_search_results(
            self._raw_results(count), execution=None, session=session
        )
        self.assertEqual(processed, count)
        self.assertEqual(errors, [])
        return list(ProcessedResult.objects.filter(session=session))

    def test_wf2_dual_inherits_dual(self):
        """WF2 (min=2): every created row is DUAL / 2."""
        results = self._process(self._make_session(min_reviewers=2))
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertEqual(r.review_mode, "DUAL", r.url)
            self.assertEqual(r.min_reviewers_required, 2, r.url)

    def test_wf2_triple_inherits_triple(self):
        """WF2 (min=3): proves the reviewer-count mapping, not a DUAL hardcode."""
        results = self._process(self._make_session(min_reviewers=3))
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertEqual(r.review_mode, "TRIPLE", r.url)
            self.assertEqual(r.min_reviewers_required, 3, r.url)

    def test_wf1_stays_single(self):
        """WF1 (min=1): unchanged SINGLE / 1."""
        results = self._process(self._make_session(min_reviewers=1))
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertEqual(r.review_mode, "SINGLE")
            self.assertEqual(r.min_reviewers_required, 1)

    def test_no_config_falls_back_to_single(self):
        """No current_configuration: safe SINGLE / 1 fallback (no regression)."""
        results = self._process(self._make_session(min_reviewers=None), count=2)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r.review_mode, "SINGLE")
            self.assertEqual(r.min_reviewers_required, 1)
