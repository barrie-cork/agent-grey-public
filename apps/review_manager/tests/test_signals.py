"""
Unit tests for review_manager signal handlers.

Tests send_invitations_when_ready, handle_status_change_request,
and cache invalidation signals directly.
"""

import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession
from apps.review_manager.signals import (
    handle_status_change_request,
    invalidate_session_cache_on_save,
    send_invitations_when_ready,
)


class SendInvitationsWhenReadyTest(DisablePersonalOrgSignalMixin, TestCase):
    """Tests for the send_invitations_when_ready signal handler."""

    def setUp(self):
        self.user = create_test_user(username_prefix="signal_inv")
        self.org = Organisation.objects.create(
            name="Signal Test Org", slug="signal-test-org"
        )
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )
        self.session = SearchSession.objects.create(
            title="Signal Test Session",
            owner=self.user,
            organisation=self.org,
            status="draft",
        )

    def test_skips_on_created(self):
        """No invitation logic triggered for new records."""
        send_invitations_when_ready(
            sender=SearchSession,
            instance=self.session,
            created=True,
            update_fields=None,
        )

    def test_skips_when_status_not_ready_for_review(self):
        """No invitations sent when session status is not ready_for_review."""
        self.session.status = "draft"
        send_invitations_when_ready(
            sender=SearchSession,
            instance=self.session,
            created=False,
            update_fields=None,
        )

    def test_skips_when_no_invited_reviewers(self):
        """No invitations sent when configuration has no invited reviewers."""
        from apps.review_manager.models import ReviewConfiguration

        config = ReviewConfiguration.objects.create(
            session=self.session,
            organisation=self.org,
            created_by=self.user,
            invited_reviewers=[],
        )
        self.session.current_configuration = config
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["current_configuration", "status"])

        send_invitations_when_ready(
            sender=SearchSession,
            instance=self.session,
            created=False,
            update_fields=None,
        )

    @patch(
        "apps.review_manager.utils.requires_is_approval_for_external",
        return_value=False,
    )
    @patch("apps.review_manager.utils.classify_invited_reviewers")
    @patch("apps.review_manager.services.invitation_service.ReviewInvitationService")
    def test_sends_invitations_for_internal_reviewers(
        self, mock_service_cls, mock_classify, mock_approval
    ):
        """Invitations are created for internal reviewers."""
        from apps.review_manager.models import ReviewConfiguration

        reviewer_data = [
            {"email": "rev@example.com", "first_name": "Rev", "last_name": "User"}
        ]
        config = ReviewConfiguration.objects.create(
            session=self.session,
            organisation=self.org,
            created_by=self.user,
            invited_reviewers=reviewer_data,
        )
        self.session.current_configuration = config
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["current_configuration", "status"])

        mock_classify.return_value = {
            "internal": reviewer_data,
            "external": [],
            "counts": {"internal": 1, "external": 0},
        }

        mock_service_instance = MagicMock()
        mock_service_instance.create_invitations.return_value = (["inv1"], [])
        mock_service_cls.return_value = mock_service_instance

        send_invitations_when_ready(
            sender=SearchSession,
            instance=self.session,
            created=False,
            update_fields=None,
        )

        mock_service_instance.create_invitations.assert_called_once()
        call_kwargs = mock_service_instance.create_invitations.call_args
        self.assertEqual(call_kwargs.kwargs["session"], self.session)

    @patch(
        "apps.review_manager.utils.requires_is_approval_for_external",
        return_value=False,
    )
    @patch("apps.review_manager.utils.classify_invited_reviewers")
    @patch("apps.review_manager.services.invitation_service.ReviewInvitationService")
    def test_handles_invitation_service_error_gracefully(
        self, mock_service_cls, mock_classify, mock_approval
    ):
        """Exception in invitation service is caught and logged, not raised."""
        from apps.review_manager.models import ReviewConfiguration

        reviewer_data = [
            {"email": "rev@example.com", "first_name": "Rev", "last_name": "User"}
        ]
        config = ReviewConfiguration.objects.create(
            session=self.session,
            organisation=self.org,
            created_by=self.user,
            invited_reviewers=reviewer_data,
        )
        self.session.current_configuration = config
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["current_configuration", "status"])

        mock_classify.return_value = {
            "internal": reviewer_data,
            "external": [],
            "counts": {"internal": 1, "external": 0},
        }

        mock_service_instance = MagicMock()
        mock_service_instance.create_invitations.side_effect = RuntimeError("SMTP fail")
        mock_service_cls.return_value = mock_service_instance

        # Should not raise
        send_invitations_when_ready(
            sender=SearchSession,
            instance=self.session,
            created=False,
            update_fields=None,
        )


class HandleStatusChangeRequestTest(DisablePersonalOrgSignalMixin, TestCase):
    """Tests for handle_status_change_request signal handler."""

    def setUp(self):
        self.user = create_test_user(username_prefix="signal_status")
        self.org = Organisation.objects.create(
            name="Status Test Org", slug="status-test-org"
        )
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )

    @patch("apps.review_manager.utils.transition_session_status")
    def test_transitions_session_status(self, mock_transition):
        """Calls transition_session_status for valid session."""
        session = SearchSession.objects.create(
            title="Transition Test",
            owner=self.user,
            organisation=self.org,
            status="defining_search",
        )
        mock_transition.return_value = (True, None)

        handle_status_change_request(
            sender=None,
            session_id=str(session.id),
            requested_status="ready_to_execute",
            reason="Strategy complete",
        )

        mock_transition.assert_called_once_with(
            session, "ready_to_execute", description="Strategy complete"
        )

    @patch("apps.review_manager.utils.transition_session_status")
    def test_handles_nonexistent_session(self, mock_transition):
        """DoesNotExist is silently caught for nonexistent session."""
        handle_status_change_request(
            sender=None,
            session_id=str(uuid.uuid4()),
            requested_status="ready_to_execute",
            reason="Test",
        )
        mock_transition.assert_not_called()


class CacheInvalidationSignalTest(DisablePersonalOrgSignalMixin, TestCase):
    """Tests for cache invalidation signal handlers."""

    def setUp(self):
        self.user = create_test_user(username_prefix="signal_cache")
        self.org = Organisation.objects.create(
            name="Cache Test Org", slug="cache-test-org"
        )
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )
        self.session = SearchSession.objects.create(
            title="Cache Test Session",
            owner=self.user,
            organisation=self.org,
            status="draft",
        )

    @patch("apps.core.services.cache_service.WorkflowCacheService")
    def test_invalidates_session_cache_on_save(self, mock_cache_svc):
        """Session cache is invalidated on save."""
        invalidate_session_cache_on_save(
            sender=SearchSession,
            instance=self.session,
            created=False,
        )

        mock_cache_svc.invalidate_session.assert_called_once_with(str(self.session.id))
        mock_cache_svc.invalidate_user_dashboard.assert_called_once_with(
            str(self.user.id)
        )

    @patch("apps.review_manager.tasks.cache.warm_session_cache")
    @patch("apps.core.services.cache_service.WorkflowCacheService")
    def test_warms_cache_for_active_status(self, mock_cache_svc, mock_warm):
        """Cache warm is triggered for active session statuses."""
        self.session.status = "under_review"
        self.session._status_changed = True

        invalidate_session_cache_on_save(
            sender=SearchSession,
            instance=self.session,
            created=False,
        )

        mock_warm.delay.assert_called_once_with(str(self.session.id))
