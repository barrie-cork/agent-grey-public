"""
Tests for the browser-extension ingestion API (Phase 1 – S4).

Covers:
- Knox token authentication (authorised + unauthorised)
- GET /api/extension/sessions/  -- lists user's reviewable sessions
- POST /api/extension/visits/   -- batch ingest BrowsingVisit records
- POST /api/extension/add-result/ -- Stream-2 promotion
"""

from django.test import TestCase
from django.urls import reverse

from knox.models import AuthToken

from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession
from apps.review_results.models import BrowsingVisit
from apps.results_manager.models import ProcessedResult


def _make_token(user):
    """Issue a Knox token for a test user. Returns the plaintext token string."""
    _, token = AuthToken.objects.create(user=user)
    return token


class ExtensionSessionListViewTest(TestCase):
    def setUp(self):
        self.user = create_test_user()
        self.token = _make_token(self.user)
        self.url = reverse("extension_sessions")

    def _get(self, token=None):
        headers = {}
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = f"Token {token}"
        return self.client.get(self.url, **headers)

    def test_unauthenticated_returns_401(self):
        self.assertEqual(self._get().status_code, 401)

    def test_wrong_token_returns_401(self):
        self.assertEqual(self._get("bad-token").status_code, 401)

    def test_returns_empty_list_when_no_sessions(self):
        resp = self._get(self.token)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_returns_reviewable_sessions_only(self):
        SearchSession.objects.create(title="Draft", owner=self.user, status="draft")
        s1 = SearchSession.objects.create(
            title="Ready", owner=self.user, status="ready_for_review"
        )
        s2 = SearchSession.objects.create(
            title="Under Review", owner=self.user, status="under_review"
        )
        resp = self._get(self.token)
        self.assertEqual(resp.status_code, 200)
        ids = {s["id"] for s in resp.json()}
        self.assertIn(str(s1.id), ids)
        self.assertIn(str(s2.id), ids)
        self.assertEqual(len(ids), 2)

    def test_does_not_return_other_users_sessions(self):
        other = create_test_user(username_prefix="other")
        SearchSession.objects.create(title="Theirs", owner=other, status="under_review")
        resp = self._get(self.token)
        self.assertEqual(resp.json(), [])

    def test_revoked_token_returns_401(self):
        # Gap 5: a working token returns 401 once it has been revoked.
        self.assertEqual(self._get(self.token).status_code, 200)
        AuthToken.objects.filter(user=self.user).delete()
        self.assertEqual(self._get(self.token).status_code, 401)


class ExtensionVisitIngestViewTest(TestCase):
    def setUp(self):
        self.user = create_test_user()
        self.token = _make_token(self.user)
        self.session = SearchSession.objects.create(
            title="Ingest Test", owner=self.user, status="under_review"
        )
        self.url = reverse("extension_visits")

    def _post(self, payload, token=None):
        import json

        headers = {"content_type": "application/json"}
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = f"Token {token}"
        return self.client.post(self.url, json.dumps(payload), **headers)

    def test_unauthenticated_returns_401(self):
        self.assertEqual(self._post({}).status_code, 401)

    def test_missing_session_id_returns_400(self):
        resp = self._post({"visits": []}, self.token)
        self.assertEqual(resp.status_code, 400)

    def test_unknown_session_returns_404(self):
        resp = self._post(
            {"session_id": "00000000-0000-0000-0000-000000000000", "visits": []},
            self.token,
        )
        self.assertEqual(resp.status_code, 404)

    def test_empty_visits_returns_200(self):
        resp = self._post(
            {"session_id": str(self.session.id), "visits": []}, self.token
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["visits_created"], 0)

    def test_visits_created_returns_201(self):
        resp = self._post(
            {
                "session_id": str(self.session.id),
                "visits": [
                    {"url": "https://nice.org.uk/guidance", "title": "NICE"},
                    {"url": "https://who.int/report", "title": "WHO"},
                ],
            },
            self.token,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["visits_created"], 2)
        self.assertEqual(BrowsingVisit.objects.filter(session=self.session).count(), 2)

    def test_cannot_ingest_to_other_users_session(self):
        other = create_test_user(username_prefix="other")
        other_session = SearchSession.objects.create(
            title="Theirs", owner=other, status="under_review"
        )
        resp = self._post(
            {"session_id": str(other_session.id), "visits": []}, self.token
        )
        self.assertEqual(resp.status_code, 404)

    def test_duplicate_batch_skips_on_second_ingest(self):
        # Gap 1: dedup is keyed on client_capture_id. Re-POSTing the same batch
        # skips the already-imported visits and creates no duplicate rows.
        batch = {
            "session_id": str(self.session.id),
            "visits": [
                {"url": "https://nice.org.uk/a", "client_capture_id": "cap-1"},
                {"url": "https://who.int/b", "client_capture_id": "cap-2"},
            ],
        }
        first = self._post(batch, self.token)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["visits_created"], 2)

        second = self._post(batch, self.token)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["visits_created"], 0)
        self.assertGreater(second.json()["visits_skipped"], 0)
        self.assertEqual(BrowsingVisit.objects.filter(session=self.session).count(), 2)

    def test_batch_over_500_returns_400(self):
        # Gap 2: BatchVisitSerializer caps the list at max_length=500.
        visits = [{"url": f"https://example.com/{i}"} for i in range(501)]
        resp = self._post(
            {"session_id": str(self.session.id), "visits": visits}, self.token
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(BrowsingVisit.objects.filter(session=self.session).count(), 0)

    def test_partial_batch_reports_errors_but_creates_valid(self):
        # Gap 3: one valid + one malformed (missing 'url') visit. The valid one
        # is created and the malformed one is reported in errors -> still 201.
        resp = self._post(
            {
                "session_id": str(self.session.id),
                "visits": [
                    {"url": "https://nice.org.uk/valid"},
                    {"title": "missing url"},
                ],
            },
            self.token,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["visits_created"], 1)
        self.assertTrue(data["errors"])
        self.assertEqual(BrowsingVisit.objects.filter(session=self.session).count(), 1)


class ExtensionAddResultViewTest(TestCase):
    def setUp(self):
        self.user = create_test_user()
        self.token = _make_token(self.user)
        self.session = SearchSession.objects.create(
            title="Add Result Test", owner=self.user, status="under_review"
        )
        self.url = reverse("extension_add_result")

    def _post(self, payload, token=None):
        import json

        headers = {"content_type": "application/json"}
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = f"Token {token}"
        return self.client.post(self.url, json.dumps(payload), **headers)

    def test_unauthenticated_returns_401(self):
        self.assertEqual(self._post({}).status_code, 401)

    def test_adds_result_returns_201(self):
        resp = self._post(
            {
                "session_id": str(self.session.id),
                "url": "https://nice.org.uk/guidance/ng1",
                "title": "NICE NG1",
                "justification": "Found browsing",
            },
            self.token,
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertIn("result_id", data)
        self.assertTrue(ProcessedResult.objects.filter(session=self.session).exists())

    def test_duplicate_url_returns_409(self):
        payload = {
            "session_id": str(self.session.id),
            "url": "https://nice.org.uk/guidance/ng1",
            "title": "NICE NG1",
            "justification": "Found browsing",
        }
        self._post(payload, self.token)
        resp = self._post(payload, self.token)
        self.assertEqual(resp.status_code, 409)

    def test_metadata_persisted(self):
        resp = self._post(
            {
                "session_id": str(self.session.id),
                "url": "https://who.int/report",
                "title": "WHO Report",
                "justification": "Grey lit source",
                "metadata": {
                    "author": "WHO Editorial",
                    "published_date": "2023-05-01",
                    "publisher": "World Health Organisation",
                    "document_type": "guideline",
                },
            },
            self.token,
        )
        self.assertEqual(resp.status_code, 201)
        result = ProcessedResult.objects.get(session=self.session)
        self.assertIn("WHO Editorial", result.authors)
        self.assertEqual(result.source_organization, "World Health Organisation")

    def test_add_result_missing_required_field_returns_400(self):
        # Gap 4: valid token but no 'url' -> serializer validation 400 (not 401).
        resp = self._post(
            {"session_id": str(self.session.id), "title": "No URL"}, self.token
        )
        self.assertEqual(resp.status_code, 400)
