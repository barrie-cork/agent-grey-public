"""Regression tests for atomic state transitions in SearchStrategyView (issue #154).

These tests cover the return-to-defining_search transition paths in
``apps.search_strategy.views.SearchStrategyView``:

- The direct path (``_handle_returnable_state_transition``) wraps the status
  save and the audit-log write in ``transaction.atomic()`` with
  ``select_for_update()`` and re-checks ``can_transition_to`` inside the lock.
- The indirect path (``_attempt_indirect_transition``) walks intermediate
  states, persisting and logging each hop inside a single atomic block.

The key guarantee is atomicity: if the audit-log write fails, the status
change must roll back so the session is never left in an inconsistent state
with a missing audit trail.
"""

from unittest.mock import patch

from django.contrib.messages.storage.session import SessionStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.tests.utils import create_test_user
from apps.review_manager.models import (
    ReviewConfiguration,
    SearchSession,
    SessionActivity,
)
from apps.search_strategy.views import SearchStrategyView


class AtomicReturnTransitionTest(TestCase):
    """Test the direct return-to-defining_search path is atomic and logs once."""

    def setUp(self):
        """Set up an owned session and log the owner in."""
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        self.session = SearchSession.objects.create(
            title="Atomic Transition Session",
            description="Issue 154 regression",
            owner=self.user,
            status="draft",
        )
        config = ReviewConfiguration.objects.create(
            session=self.session, created_by=self.user
        )
        self.session.current_configuration = config
        self.session.save()

    def _strategy_url(self):
        return reverse(
            "search_strategy:strategy_form", kwargs={"session_id": self.session.id}
        )

    def test_direct_return_transitions_and_logs_once(self):
        """A returnable state transitions back to defining_search with one log entry.

        ``under_review`` allows a direct transition to ``defining_search`` (it is
        in ALLOWED_TRANSITIONS), so the direct path is taken and exactly one
        ``status_changed`` activity is recorded.
        """
        self.session.status = "under_review"
        self.session.save()

        response = self.client.get(self._strategy_url())

        self.assertEqual(response.status_code, 200)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")

        status_changes = SessionActivity.objects.filter(
            session=self.session, activity_type="status_changed"
        )
        self.assertEqual(status_changes.count(), 1)

        activity = status_changes.first()
        self.assertEqual(activity.metadata.get("old_status"), "under_review")
        self.assertEqual(activity.metadata.get("new_status"), "defining_search")
        self.assertEqual(
            activity.metadata.get("reason"), "user_initiated_strategy_modification"
        )

    def test_audit_log_failure_rolls_back_status_change(self):
        """If the audit-log write fails, the status change must roll back.

        With no processed results, the only ``log_activity`` call reached is the
        ``status_changed`` write *inside* the atomic block, immediately after the
        status save. Forcing it to raise must roll back the status save, leaving
        the session at its original state with no orphan activity row.
        """
        self.session.status = "under_review"
        self.session.save()

        with patch.object(
            SessionActivity,
            "log_activity",
            side_effect=RuntimeError("audit log write failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.get(self._strategy_url())

        # Status must be unchanged: the atomic block rolled back the save.
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "under_review")

        # No status_changed activity should have been persisted.
        self.assertFalse(
            SessionActivity.objects.filter(
                session=self.session, activity_type="status_changed"
            ).exists()
        )


class IndirectReturnTransitionTest(TestCase):
    """Test the indirect path logs every intermediate state inside one atomic block.

    The indirect path is reached only when a direct transition to
    ``defining_search`` is not allowed. With the current ALLOWED_TRANSITIONS,
    every state listed in the view's ``returnable_states`` can reach
    ``defining_search`` directly, so the indirect path is exercised here by
    invoking ``_attempt_indirect_transition`` directly with a session whose
    only route to ``defining_search`` is multi-hop (``archived`` ->
    ``draft`` -> ``defining_search``).
    """

    def setUp(self):
        """Set up an owned session and a request carrying the messages framework."""
        self.user = create_test_user()
        self.factory = RequestFactory()

        self.session = SearchSession.objects.create(
            title="Indirect Transition Session",
            description="Issue 154 regression",
            owner=self.user,
            status="draft",
        )

    def _make_request(self):
        """Build a GET request with user and message storage attached."""
        request = self.factory.get("/dummy-url/")
        request.user = self.user
        request.session = {}
        request._messages = SessionStorage(request)
        return request

    def test_indirect_path_logs_each_intermediate_state(self):
        """Each hop on the indirect route is persisted and logged separately."""
        # archived -> draft -> defining_search is the only multi-hop route.
        self.session.status = "archived"
        self.session.save()

        view = SearchStrategyView()
        view.session = self.session
        request = self._make_request()

        result = view._attempt_indirect_transition(request)

        # None signals a successful transition (no error redirect).
        self.assertIsNone(result)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")

        # One status_changed log per intermediate hop: draft, then defining_search.
        status_changes = SessionActivity.objects.filter(
            session=self.session, activity_type="status_changed"
        ).order_by("created_at")
        self.assertEqual(status_changes.count(), 2)

        logged_new_states = [
            activity.metadata.get("new_status") for activity in status_changes
        ]
        self.assertEqual(logged_new_states, ["draft", "defining_search"])

        # Each entry records its own from->to hop with the indirect reason.
        first, second = status_changes[0], status_changes[1]
        self.assertEqual(first.metadata.get("old_status"), "archived")
        self.assertEqual(first.metadata.get("new_status"), "draft")
        self.assertEqual(first.metadata.get("reason"), "indirect_transition")
        self.assertEqual(second.metadata.get("old_status"), "draft")
        self.assertEqual(second.metadata.get("new_status"), "defining_search")
        self.assertEqual(second.metadata.get("reason"), "indirect_transition")

    def test_indirect_path_audit_failure_rolls_back_all_hops(self):
        """If logging fails mid-walk, every hop rolls back atomically.

        The whole indirect walk runs in a single ``transaction.atomic()`` block,
        so a failure on the first audit-log write must leave the session at its
        original state with no partial status change and no orphan activity.
        """
        self.session.status = "archived"
        self.session.save()

        view = SearchStrategyView()
        view.session = self.session
        request = self._make_request()

        with patch.object(
            SessionActivity,
            "log_activity",
            side_effect=RuntimeError("audit log write failed"),
        ):
            with self.assertRaises(RuntimeError):
                view._attempt_indirect_transition(request)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "archived")
        self.assertFalse(
            SessionActivity.objects.filter(
                session=self.session, activity_type="status_changed"
            ).exists()
        )
