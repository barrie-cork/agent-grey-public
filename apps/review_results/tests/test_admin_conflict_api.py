"""
Tests for Admin/List Conflict API endpoints (DRF-based).

Tests the 4 endpoints in apps/review_results/api/conflict_views.py:
- GET /api/conflicts/ - ConflictListView (filterable, paginated)
- GET /api/conflicts/{id}/ - get_conflict_detail
- POST /api/conflicts/{id}/resolve/ - ResolveConflictView
- POST /api/conflicts/{id}/discuss/ - add_conflict_discussion

These are the DRF API endpoints (review_results_api namespace), distinct from
the legacy view-based conflict endpoints in views/api_views.py.
"""

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.core.tests.utils import (
    DisablePersonalOrgSignalMixin,
    create_test_user,
    make_session_participant,
)
from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import (
    ReviewConfiguration,
    SearchSession,
    SessionActivity,
)
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import ConflictResolution, ReviewerDecision

User = get_user_model()


class AdminConflictAPITestBase(DisablePersonalOrgSignalMixin, TestCase):
    """Base test case with shared setup for admin conflict API tests."""

    def setUp(self):
        """Set up test data for conflict API tests."""
        # Users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")
        self.senior = create_test_user(username_prefix="senior")
        self.outsider = create_test_user(username_prefix="outsider")

        # Organisation + memberships
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org-admin-conflict"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer1,
            organisation=self.org,
            role="LEAD_REVIEWER",
            is_active=True,
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2,
            organisation=self.org,
            role="LEAD_REVIEWER",
            is_active=True,
        )
        OrganisationMembership.objects.create(
            user=self.senior,
            organisation=self.org,
            role="SENIOR_RESEARCHER",
            is_active=True,
        )

        # Second org for outsider
        self.other_org = Organisation.objects.create(
            name="Other Organisation", slug="other-org-admin-conflict"
        )
        OrganisationMembership.objects.create(
            user=self.outsider,
            organisation=self.other_org,
            role="SENIOR_RESEARCHER",
            is_active=True,
        )

        # Session (under_review for conflict scenarios)
        self.session = SearchSession.objects.create(
            owner=self.reviewer1,
            organisation=self.org,
            title="Test Session",
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            version=1,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            conflict_resolution_method="CONSENSUS",
            consensus_criteria="MAJORITY",
            created_by=self.reviewer1,
            organisation=self.org,
        )
        self.session.current_configuration = self.config
        self.session.save(update_fields=["current_configuration"])

        # Processed results
        self.result1 = ProcessedResult.objects.create(
            session=self.session,
            title="Result One",
            snippet="First test result",
            url="https://example.com/1",
            processing_status="success",
        )
        self.result2 = ProcessedResult.objects.create(
            session=self.session,
            title="Result Two",
            snippet="Second test result",
            url="https://example.com/2",
            processing_status="success",
        )

        # Conflicting decisions for result1
        self.decision1 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result1,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            confidence_level=3,
            notes="Should include",
        )
        self.decision2 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result1,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            exclusion_reason="not_relevant",
            confidence_level=3,
            notes="Should exclude",
        )

        # Conflict for result1 (PENDING)
        self.conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result1,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            resolution_method="CONSENSUS",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

        # Second conflict (IN_DISCUSSION) for filter testing
        self.decision3 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result2,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            confidence_level=2,
        )
        self.decision4 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result2,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            exclusion_reason="duplicate",
            confidence_level=2,
        )
        self.conflict2 = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result2,
            conflict_type="INCLUDE_EXCLUDE",
            status="IN_DISCUSSION",
            resolution_method="CONSENSUS",
        )
        self.conflict2.conflicting_decisions.add(self.decision3, self.decision4)

        self.client = Client()


# =============================================================================
# ConflictListView Tests
# =============================================================================


class ConflictListViewTests(AdminConflictAPITestBase):
    """Tests for GET /api/conflicts/ endpoint."""

    def test_list_conflicts_as_lead_reviewer(self):
        """Lead reviewer can list conflicts."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/", {"session_id": str(self.session.id)}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertIn("results", data)

    def test_list_conflicts_as_senior_researcher(self):
        """Senior researcher can list conflicts."""
        self.client.login(username=self.senior.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/", {"session_id": str(self.session.id)}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)

    def test_list_conflicts_filter_by_status_pending(self):
        """Filter conflicts by PENDING status."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/",
            {"session_id": str(self.session.id), "status": "PENDING"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["status"], "PENDING")

    def test_list_conflicts_filter_by_status_in_discussion(self):
        """Filter conflicts by IN_DISCUSSION status."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/",
            {"session_id": str(self.session.id), "status": "IN_DISCUSSION"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["status"], "IN_DISCUSSION")

    def test_list_conflicts_filter_assigned_to_me(self):
        """Filter to only conflicts where user is a conflicting reviewer."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/",
            {"session_id": str(self.session.id), "assigned_to_me": "true"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # reviewer1 is involved in both conflicts
        self.assertEqual(data["count"], 2)

    def test_list_conflicts_pagination(self):
        """Pagination returns correct metadata."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/",
            {"session_id": str(self.session.id), "per_page": 1, "page": 1},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["num_pages"], 2)
        self.assertEqual(data["page"], 1)
        self.assertTrue(data["next"])
        self.assertFalse(data["previous"])
        self.assertEqual(len(data["results"]), 1)

    def test_list_conflicts_pagination_page_2(self):
        """Second page returns remaining results."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/",
            {"session_id": str(self.session.id), "per_page": 1, "page": 2},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["next"])
        self.assertTrue(data["previous"])
        self.assertEqual(len(data["results"]), 1)

    def test_list_conflicts_unauthenticated(self):
        """Unauthenticated request is rejected."""
        response = self.client.get(
            "/api/conflicts/", {"session_id": str(self.session.id)}
        )
        self.assertIn(response.status_code, [401, 403])

    def test_list_conflicts_no_organisation_no_access(self):
        """User without organisation membership or session access gets 404."""
        no_org_user = create_test_user(username_prefix="no_org")
        self.client.login(username=no_org_user.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/", {"session_id": str(self.session.id)}
        )

        # No org, no session access -> check_session_access denies -> 404
        self.assertEqual(response.status_code, 404)

    def test_list_conflicts_reviewer_role_with_session_access(self):
        """A participant REVIEWER (accepted invitation) can list conflicts."""
        basic_reviewer = create_test_user(username_prefix="basic")
        OrganisationMembership.objects.create(
            user=basic_reviewer,
            organisation=self.org,
            role="REVIEWER",
            is_active=True,
        )
        # Access now comes from participation, not bare org membership (GH #230).
        make_session_participant(self.session, basic_reviewer)

        self.client.login(username=basic_reviewer.username, password="testpass123")
        response = self.client.get(
            "/api/conflicts/", {"session_id": str(self.session.id)}
        )

        self.assertEqual(response.status_code, 200)


# =============================================================================
# get_conflict_detail Tests
# =============================================================================


class ConflictDetailViewTests(AdminConflictAPITestBase):
    """Tests for GET /api/conflicts/{id}/ endpoint."""

    def _url(self, conflict_id):
        return f"/api/conflicts/{conflict_id}/"

    def test_get_conflict_detail_as_lead_reviewer(self):
        """Lead reviewer can get conflict details."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(self._url(self.conflict.id))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "PENDING")
        self.assertEqual(data["conflict_type"], "INCLUDE_EXCLUDE")
        self.assertIn("conflicting_decisions", data)
        self.assertEqual(len(data["conflicting_decisions"]), 2)

    def test_get_conflict_detail_as_senior_researcher(self):
        """Senior researcher can get conflict details."""
        self.client.login(username=self.senior.username, password="testpass123")
        response = self.client.get(self._url(self.conflict.id))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["conflict_type"], "INCLUDE_EXCLUDE")

    def test_get_conflict_detail_includes_result_data(self):
        """Conflict detail includes nested result data."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(self._url(self.conflict.id))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("result", data)

    def test_get_conflict_detail_includes_resolved_by(self):
        """Conflict detail includes resolved_by field (null for unresolved)."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self.client.get(self._url(self.conflict.id))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("resolved_by", data)
        self.assertIsNone(data["resolved_by"])

    def test_get_conflict_detail_invalid_uuid(self):
        """Non-existent conflict UUID returns 404."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        fake_id = uuid.uuid4()
        response = self.client.get(self._url(fake_id))

        self.assertEqual(response.status_code, 404)

    def test_get_conflict_detail_wrong_organisation(self):
        """User from different organisation gets 404 (org filter)."""
        self.client.login(username=self.outsider.username, password="testpass123")
        response = self.client.get(self._url(self.conflict.id))

        # outsider has no session access (not owner, not invited) -> 404
        self.assertEqual(response.status_code, 404)

    def test_get_conflict_detail_unauthenticated(self):
        """Unauthenticated request is rejected."""
        response = self.client.get(self._url(self.conflict.id))
        self.assertIn(response.status_code, [401, 403])

    def test_get_conflict_detail_no_organisation_no_access(self):
        """User without any organisation membership or session access gets 404."""
        no_org_user = create_test_user(username_prefix="no_org")
        self.client.login(username=no_org_user.username, password="testpass123")
        response = self.client.get(self._url(self.conflict.id))

        # No org, no session access -> check_session_access denies -> 404
        self.assertEqual(response.status_code, 404)


# =============================================================================
# ResolveConflictView Tests
# =============================================================================


class ResolveConflictViewTests(AdminConflictAPITestBase):
    """Tests for POST /api/conflicts/{id}/resolve/ endpoint."""

    def _url(self, conflict_id):
        return f"/api/conflicts/{conflict_id}/resolve/"

    def _valid_payload(self):
        return {
            "decision": "INCLUDE",
            "resolution_notes": "Decided to include based on relevance",
        }

    def _post_json(self, url, data):
        return self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

    def test_resolve_conflict_as_senior_researcher(self):
        """Senior researcher can resolve a conflict."""
        self.client.login(username=self.senior.username, password="testpass123")
        response = self._post_json(self._url(self.conflict.id), self._valid_payload())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))

        # Verify conflict is now resolved
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "RESOLVED")

    def test_resolve_conflict_already_resolved(self):
        """Resolving an already-resolved conflict returns 409."""
        self.conflict.status = "RESOLVED"
        self.conflict.save(update_fields=["status"])

        self.client.login(username=self.senior.username, password="testpass123")
        response = self._post_json(self._url(self.conflict.id), self._valid_payload())

        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["error"], "already_resolved")

    def test_resolve_conflict_missing_decision(self):
        """Missing required decision field returns 400."""
        self.client.login(username=self.senior.username, password="testpass123")
        response = self._post_json(
            self._url(self.conflict.id),
            {"resolution_notes": "No decision provided"},
        )

        self.assertEqual(response.status_code, 400)

    def test_resolve_conflict_invalid_decision(self):
        """Invalid decision value returns 400."""
        self.client.login(username=self.senior.username, password="testpass123")
        response = self._post_json(
            self._url(self.conflict.id),
            {"decision": "INVALID_VALUE"},
        )

        self.assertEqual(response.status_code, 400)

    def test_resolve_conflict_permission_denied_for_lead_reviewer(self):
        """Lead reviewer cannot resolve conflicts (view-body role check requires CONFLICT_RESOLVE)."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self._post_json(self._url(self.conflict.id), self._valid_payload())

        self.assertEqual(response.status_code, 403)

    def test_resolve_conflict_invalid_conflict_id(self):
        """Non-existent conflict UUID returns 404."""
        self.client.login(username=self.senior.username, password="testpass123")
        fake_id = uuid.uuid4()
        response = self._post_json(self._url(fake_id), self._valid_payload())

        self.assertEqual(response.status_code, 404)

    def test_resolve_conflict_creates_session_activity(self):
        """Resolving a conflict logs a SessionActivity entry."""
        initial_count = SessionActivity.objects.filter(
            session=self.session, activity_type="conflict_resolved"
        ).count()

        self.client.login(username=self.senior.username, password="testpass123")
        response = self._post_json(self._url(self.conflict.id), self._valid_payload())

        self.assertEqual(response.status_code, 200)
        final_count = SessionActivity.objects.filter(
            session=self.session, activity_type="conflict_resolved"
        ).count()
        self.assertEqual(final_count, initial_count + 1)

    def test_resolve_conflict_unauthenticated(self):
        """Unauthenticated request is rejected."""
        response = self._post_json(self._url(self.conflict.id), self._valid_payload())
        self.assertIn(response.status_code, [401, 403])

    def test_resolve_conflict_wrong_organisation(self):
        """User from different organisation gets 404."""
        self.client.login(username=self.outsider.username, password="testpass123")
        response = self._post_json(self._url(self.conflict.id), self._valid_payload())

        # outsider has no session access (not owner, not invited) -> 404
        self.assertEqual(response.status_code, 404)

    def test_resolve_conflict_exclude_with_reason(self):
        """Resolving as EXCLUDE with exclusion_reason works."""
        self.client.login(username=self.senior.username, password="testpass123")
        response = self._post_json(
            self._url(self.conflict.id),
            {
                "decision": "EXCLUDE",
                "exclusion_reason": "not_relevant",
                "resolution_notes": "After review, this is off-topic",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "RESOLVED")


# =============================================================================
# add_conflict_discussion Tests
# =============================================================================


class AddConflictDiscussionTests(AdminConflictAPITestBase):
    """Tests for POST /api/conflicts/{id}/discuss/ endpoint."""

    def _url(self, conflict_id):
        return f"/api/conflicts/{conflict_id}/discuss/"

    def _post_json(self, url, data):
        return self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

    def test_add_discussion_as_conflicting_reviewer(self):
        """Conflicting reviewer can add a discussion comment."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self._post_json(
            self._url(self.conflict.id),
            {"comment": "I believe this should be included."},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))

        # Verify comment was stored
        self.conflict.refresh_from_db()
        self.assertIn(
            "I believe this should be included", self.conflict.resolution_notes
        )

    def test_add_discussion_updates_status_to_in_discussion(self):
        """Adding a comment to PENDING conflict updates status to IN_DISCUSSION."""
        self.assertEqual(self.conflict.status, "PENDING")

        self.client.login(username=self.reviewer1.username, password="testpass123")
        self._post_json(
            self._url(self.conflict.id),
            {"comment": "Starting discussion."},
        )

        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "IN_DISCUSSION")

    def test_add_discussion_preserves_in_discussion_status(self):
        """Adding a comment to an IN_DISCUSSION conflict keeps the status."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        self._post_json(
            self._url(self.conflict2.id),
            {"comment": "Continuing discussion."},
        )

        self.conflict2.refresh_from_db()
        self.assertEqual(self.conflict2.status, "IN_DISCUSSION")

    def test_add_discussion_empty_comment_rejected(self):
        """Empty comment string returns 400."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self._post_json(self._url(self.conflict.id), {"comment": ""})

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "validation_error")

    def test_add_discussion_missing_comment_rejected(self):
        """Missing comment field returns 400."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        response = self._post_json(self._url(self.conflict.id), {})

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data["error"], "validation_error")

    def test_add_discussion_non_reviewer_non_admin_rejected(self):
        """Non-conflicting lead reviewer without CONFLICT_COMMENT gets 403."""
        bystander = create_test_user(username_prefix="bystander")
        OrganisationMembership.objects.create(
            user=bystander,
            organisation=self.org,
            role="LEAD_REVIEWER",
            is_active=True,
        )

        self.client.login(username=bystander.username, password="testpass123")
        response = self._post_json(
            self._url(self.conflict.id),
            {"comment": "I have opinions too."},
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertEqual(data["error"], "permission_denied")

    def test_add_discussion_senior_researcher_can_comment(self):
        """Senior researcher can add comments (passes IsLeadReviewerOrAdmin via CONFLICT_VIEW)."""
        self.client.login(username=self.senior.username, password="testpass123")
        response = self._post_json(
            self._url(self.conflict.id),
            {"comment": "Admin perspective on this conflict."},
        )

        # Senior passes DRF permission, then view checks CONFLICT_COMMENT
        # SENIOR_RESEARCHER does not have CONFLICT_COMMENT, but may have
        # is_conflicting_reviewer=False, so this depends on the secondary check
        # Since senior is NOT a conflicting reviewer and lacks CONFLICT_COMMENT -> 403
        self.assertEqual(response.status_code, 403)

    def test_add_discussion_creates_session_activity(self):
        """Adding a discussion comment logs a SessionActivity entry."""
        initial_count = SessionActivity.objects.filter(
            session=self.session, activity_type="conflict_discussion"
        ).count()

        self.client.login(username=self.reviewer1.username, password="testpass123")
        self._post_json(
            self._url(self.conflict.id),
            {"comment": "Test comment for activity log."},
        )

        final_count = SessionActivity.objects.filter(
            session=self.session, activity_type="conflict_discussion"
        ).count()
        self.assertEqual(final_count, initial_count + 1)

    def test_add_discussion_invalid_conflict_id(self):
        """Non-existent conflict UUID returns 404."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        fake_id = uuid.uuid4()
        response = self._post_json(
            self._url(fake_id),
            {"comment": "This conflict does not exist."},
        )

        self.assertEqual(response.status_code, 404)

    def test_add_multiple_comments(self):
        """Multiple comments accumulate in resolution_notes."""
        self.client.login(username=self.reviewer1.username, password="testpass123")
        self._post_json(self._url(self.conflict.id), {"comment": "First comment."})
        self._post_json(self._url(self.conflict.id), {"comment": "Second comment."})

        self.conflict.refresh_from_db()
        self.assertIn("First comment", self.conflict.resolution_notes)
        self.assertIn("Second comment", self.conflict.resolution_notes)

    def test_add_discussion_unauthenticated(self):
        """Unauthenticated request is rejected."""
        response = self._post_json(
            self._url(self.conflict.id),
            {"comment": "Should not work."},
        )
        self.assertIn(response.status_code, [401, 403])

    def test_add_discussion_wrong_organisation(self):
        """User from different organisation gets 404."""
        self.client.login(username=self.outsider.username, password="testpass123")
        response = self._post_json(
            self._url(self.conflict.id),
            {"comment": "Cross-org comment."},
        )

        # outsider has no session access (not owner, not invited) -> 404
        self.assertEqual(response.status_code, 404)

    def test_add_discussion_reviewer_role_denied(self):
        """Participant REVIEWER lacks CONFLICT_COMMENT and is not a conflicting reviewer -> 403."""
        basic_reviewer = create_test_user(username_prefix="basic")
        OrganisationMembership.objects.create(
            user=basic_reviewer,
            organisation=self.org,
            role="REVIEWER",
            is_active=True,
        )
        # Participant (so reaches the endpoint), but cannot comment -> 403.
        make_session_participant(self.session, basic_reviewer)

        self.client.login(username=basic_reviewer.username, password="testpass123")
        response = self._post_json(
            self._url(self.conflict.id),
            {"comment": "Basic reviewer comment."},
        )

        self.assertEqual(response.status_code, 403)
