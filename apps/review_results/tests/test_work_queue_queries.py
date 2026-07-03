"""Query-count regression tests for the dual-screening work queue (plan 003).

The work queue must issue a constant number of queries regardless of how many
results are on the page (no N+1 in serialization), and the serializer's
``my_decision`` value must still mirror ``active_for`` semantics (non-revote).
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import ReviewerDecision


class WorkQueueQueryCountTest(TestCase):
    def setUp(self):
        self.owner = create_test_user(username_prefix="owner")
        self.org = Organisation.objects.create(name="Test Org")
        self.url = reverse("review_results_api:work-queue")

    def _make_wf2_session(self, n_results, n_decided=0):
        session = SearchSession.objects.create(
            title="WQ Session",
            owner=self.owner,
            organisation=self.org,
            status="under_review",
        )
        config = ReviewConfiguration.objects.create(
            session=session,
            min_reviewers_per_result=2,
            created_by=self.owner,
        )
        session.current_configuration = config
        session.save()

        results = []
        for i in range(n_results):
            results.append(
                ProcessedResult.objects.create(
                    session=session,
                    title=f"Result {i}",
                    url=f"https://example.com/{session.id}/{i}",
                    snippet="snip",
                )
            )
        for result in results[:n_decided]:
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.owner,
                organisation=self.org,
                decision="INCLUDE",
                confidence_level=2,
                is_revote=False,
            )
        return session, results

    def _get_queue(self, session, count_queries=False):
        self.client.force_login(self.owner)
        params = {"session_id": str(session.id), "per_page": 100}
        if not count_queries:
            resp = self.client.get(self.url, params)
            self.assertEqual(resp.status_code, 200)
            return resp, None
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(self.url, params)
        self.assertEqual(resp.status_code, 200)
        return resp, len(ctx.captured_queries)

    def _entry_for(self, resp, result):
        return next(
            e for e in resp.json()["results"] if e["result"]["id"] == str(result.id)
        )

    def test_query_count_is_constant_in_result_count(self):
        small_session, _ = self._make_wf2_session(5, n_decided=3)
        large_session, _ = self._make_wf2_session(20, n_decided=12)

        # Warm up content-type / auth caches so the comparison isolates per-row
        # scaling rather than first-call cache population.
        self._get_queue(small_session)

        _, small_count = self._get_queue(small_session, count_queries=True)
        _, large_count = self._get_queue(large_session, count_queries=True)
        self.assertEqual(
            small_count,
            large_count,
            f"Work-queue query count scales with result count "
            f"({small_count} for 5 results vs {large_count} for 20)",
        )

    def test_my_decision_value_unchanged_for_decided_result(self):
        session, results = self._make_wf2_session(3, n_decided=1)
        resp, _ = self._get_queue(session)
        self.assertEqual(
            self._entry_for(resp, results[0])["result"]["my_decision"], "include"
        )

    def test_revote_serialises_to_non_revote_value(self):
        session, results = self._make_wf2_session(2, n_decided=0)
        result = results[0]
        ReviewerDecision.objects.create(
            result=result,
            reviewer=self.owner,
            organisation=self.org,
            decision="INCLUDE",
            confidence_level=2,
            is_revote=False,
        )
        ReviewerDecision.objects.create(
            result=result,
            reviewer=self.owner,
            organisation=self.org,
            decision="EXCLUDE",
            exclusion_reason="wrong_population",
            confidence_level=3,
            is_revote=True,
        )
        expected = (
            ReviewerDecision.objects.active_for(result, self.owner)
            .values_list("decision", flat=True)
            .first()
            .lower()
        )
        resp, _ = self._get_queue(session)
        my_decision = self._entry_for(resp, result)["result"]["my_decision"]
        self.assertEqual(my_decision, expected)
        self.assertEqual(my_decision, "include")
