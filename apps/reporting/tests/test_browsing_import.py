"""
Tests for the Phase 0 JSON browsing-visit import endpoint and service.

Covers:
- BrowsingImportService: basic import, idempotency, URL canonicalization,
  Stream-2 queue promotion, invalid-state guard.
- ImportBrowsingVisitsView: auth, JSON parsing, session ownership, HTTP status.
"""

import json

from django.test import Client, TestCase
from django.urls import reverse

from apps.core.tests.utils import create_test_user
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import BrowsingVisit
from apps.review_results.services.browsing_import_service import (
    BrowsingImportService,
    canonicalize_url,
)


# ---------------------------------------------------------------------------
# Unit tests: canonicalize_url
# ---------------------------------------------------------------------------


class CanonicalizationTest(TestCase):
    """URL canonicalization utility."""

    def test_lowercases_scheme_and_host(self):
        self.assertEqual(
            canonicalize_url("HTTPS://EXAMPLE.COM/page"),
            "https://example.com/page",
        )

    def test_strips_trailing_path_slash(self):
        self.assertEqual(
            canonicalize_url("https://example.com/page/"),
            "https://example.com/page",
        )

    def test_root_path_preserved(self):
        self.assertEqual(
            canonicalize_url("https://example.com/"),
            "https://example.com/",
        )

    def test_removes_fragment(self):
        self.assertEqual(
            canonicalize_url("https://example.com/page#section"),
            "https://example.com/page",
        )

    def test_preserves_query_string(self):
        url = "https://example.com/page?q=test&lang=en"
        self.assertIn("q=test", canonicalize_url(url))

    def test_graceful_on_malformed_url(self):
        """Should return the original string on parse failure."""
        result = canonicalize_url("not-a-url")
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# Unit tests: BrowsingImportService
# ---------------------------------------------------------------------------


class BrowsingImportServiceTest(TestCase):
    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Import Service Test",
            owner=self.user,
            status="under_review",
        )

    def _import(self, visits: list) -> object:
        return BrowsingImportService.import_from_json(
            self.session, self.user, {"visits": visits}
        )

    def _visit(self, **kwargs):
        defaults = {
            "url": "https://nice.org.uk/guidance/ng1",
            "title": "NICE NG1",
            "access_successful": True,
            "visit_source": "auto",
        }
        defaults.update(kwargs)
        return defaults

    # --- basic creation ---

    def test_creates_browsing_visit(self):
        result = self._import([self._visit()])
        self.assertEqual(result.visits_created, 1)
        self.assertEqual(BrowsingVisit.objects.filter(session=self.session).count(), 1)

    def test_multiple_visits_created(self):
        visits = [self._visit(url=f"https://example{i}.com/") for i in range(5)]
        result = self._import(visits)
        self.assertEqual(result.visits_created, 5)
        self.assertEqual(result.visits_skipped, 0)

    def test_url_canonicalized_on_storage(self):
        result = self._import([self._visit(url="HTTPS://NICE.ORG.UK/guidance/")])
        self.assertEqual(result.visits_created, 1)
        visit = BrowsingVisit.objects.get(session=self.session)
        self.assertEqual(visit.canonical_url, "https://nice.org.uk/guidance")

    def test_metadata_persisted(self):
        result = self._import(
            [
                self._visit(
                    author="Editorial Board",
                    published_date="2024-03-15",
                    document_type="report",
                    site_name="NICE",
                )
            ]
        )
        self.assertEqual(result.visits_created, 1)
        visit = BrowsingVisit.objects.get(session=self.session)
        self.assertEqual(visit.author, "Editorial Board")
        self.assertEqual(str(visit.published_date), "2024-03-15")
        self.assertEqual(visit.document_type, "report")
        self.assertEqual(visit.site_name, "NICE")

    def test_access_successful_false_stored(self):
        result = self._import([self._visit(access_successful=False)])
        self.assertEqual(result.visits_created, 1)
        visit = BrowsingVisit.objects.get(session=self.session)
        self.assertFalse(visit.access_successful)

    def test_captured_incognito_stored(self):
        self._import([self._visit(captured_incognito=True)])
        visit = BrowsingVisit.objects.get(session=self.session)
        self.assertTrue(visit.captured_incognito)

    def test_captured_incognito_defaults_false_when_omitted(self):
        self._import([self._visit()])
        visit = BrowsingVisit.objects.get(session=self.session)
        self.assertFalse(visit.captured_incognito)

    # --- idempotency ---

    def test_duplicate_client_capture_id_skipped(self):
        self._import([self._visit(client_capture_id="abc123")])
        result = self._import([self._visit(client_capture_id="abc123")])
        self.assertEqual(result.visits_created, 0)
        self.assertEqual(result.visits_skipped, 1)
        self.assertEqual(BrowsingVisit.objects.filter(session=self.session).count(), 1)

    def test_no_client_capture_id_allows_duplicate_url(self):
        """Without client_capture_id two identical-URL visits are both stored."""
        self._import([self._visit()])
        result = self._import([self._visit()])
        self.assertEqual(result.visits_created, 1)
        self.assertEqual(BrowsingVisit.objects.filter(session=self.session).count(), 2)

    # --- Stream-2 promotion ---

    def test_add_to_queue_creates_processed_result(self):
        result = self._import(
            [
                self._visit(
                    add_to_queue=True,
                    justification="Found during search",
                )
            ]
        )
        self.assertEqual(result.visits_created, 1)
        self.assertEqual(result.queue_items_added, 1)
        self.assertEqual(result.errors, [])
        self.assertTrue(ProcessedResult.objects.filter(session=self.session).exists())

    def test_add_to_queue_links_promoted_result(self):
        self._import([self._visit(url="https://who.int/report", add_to_queue=True)])
        visit = BrowsingVisit.objects.get(session=self.session)
        self.assertIsNotNone(visit.promoted_result)
        self.assertEqual(visit.promoted_result.url, "https://who.int/report")

    def test_add_to_queue_passes_metadata(self):
        self._import(
            [
                self._visit(
                    add_to_queue=True,
                    author="WHO",
                    published_date="2023-05-01",
                    publisher="World Health Organisation",
                    document_type="guideline",
                    justification="Key guideline",
                )
            ]
        )
        result_obj = ProcessedResult.objects.get(session=self.session)
        self.assertIn("WHO", result_obj.authors)
        self.assertEqual(result_obj.source_organization, "World Health Organisation")

    def test_add_to_queue_duplicate_url_noted_not_fatal(self):
        """If URL already in queue, queue add fails gracefully; visit still counted."""
        # Pre-add the URL
        ProcessedResult.objects.create(
            session=self.session,
            url="https://nice.org.uk/guidance/ng1",
            title="Already there",
            processing_status="success",
        )
        result = self._import([self._visit(add_to_queue=True)])
        self.assertEqual(result.visits_created, 1)
        self.assertEqual(result.queue_items_added, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Queue promotion skipped", result.errors[0])

    # --- session state guard ---

    def test_wrong_session_state_returns_error(self):
        self.session.status = "draft"
        self.session.save()
        result = self._import([self._visit()])
        self.assertEqual(result.visits_created, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("draft", result.errors[0])

    def test_missing_url_noted(self):
        result = self._import([{"title": "No URL here"}])
        self.assertEqual(result.visits_created, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("url", result.errors[0])

    def test_empty_visits_list_is_ok(self):
        result = self._import([])
        self.assertEqual(result.visits_created, 0)
        self.assertEqual(result.errors, [])


# ---------------------------------------------------------------------------
# Integration tests: ImportBrowsingVisitsView
# ---------------------------------------------------------------------------


class ImportBrowsingVisitsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="View Import Test",
            owner=self.user,
            status="under_review",
        )
        self.url = reverse(
            "reporting:api_import_browsing_visits",
            args=[self.session.id],
        )

    def _post(self, payload: dict, *, authenticated: bool = True) -> object:
        if authenticated:
            self.client.force_login(self.user)
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_unauthenticated_redirects(self):
        response = self._post({"visits": []}, authenticated=False)
        self.assertIn(response.status_code, (302, 403))

    def test_wrong_owner_404(self):
        other = create_test_user(username_prefix="other")
        self.client.force_login(other)
        response = self.client.post(
            self.url,
            data=json.dumps({"visits": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_json_400(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url, data="not-json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_visits_returns_200(self):
        response = self._post({"visits": []})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["visits_created"], 0)

    def test_valid_import_returns_201(self):
        response = self._post(
            {
                "visits": [
                    {
                        "url": "https://example.com/report",
                        "title": "Example Report",
                        "access_successful": True,
                    }
                ]
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["visits_created"], 1)
        self.assertEqual(data["queue_items_added"], 0)

    def test_response_contains_all_keys(self):
        response = self._post({"visits": []})
        data = response.json()
        for key in ("visits_created", "visits_skipped", "queue_items_added", "errors"):
            self.assertIn(key, data)

    def test_wrong_session_state_returns_400(self):
        self.session.status = "draft"
        self.session.save()
        response = self._post(
            {"visits": [{"url": "https://example.com", "title": "X"}]}
        )
        self.assertEqual(response.status_code, 400)

    def test_add_to_queue_reflected_in_response(self):
        response = self._post(
            {
                "visits": [
                    {
                        "url": "https://who.int/report",
                        "title": "WHO Report",
                        "add_to_queue": True,
                        "justification": "Key source",
                    }
                ]
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["visits_created"], 1)
        self.assertEqual(data["queue_items_added"], 1)
