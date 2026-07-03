"""
Security tests for reviewer invitation workflow.

Tests ensure that:
1. Invitations are not sent during session setup (Phase 1 fix)
2. Invitations are sent automatically at ready_for_review status (Phase 2 fix)
3. Reviewers cannot access search strategy views (Phase 3 fix)
4. Session owners can still access search strategy views
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import (
    ReviewConfiguration,
    ReviewInvitation,
    SearchSession,
)
from apps.core.tests.utils import create_test_user
from apps.search_strategy.models import SearchStrategy
from apps.search_strategy.views import SearchStrategyView

User = get_user_model()


class InvitationSecurityTestCase(TestCase):
    """Security tests for reviewer invitation workflow."""

    @classmethod
    def setUpTestData(cls):
        """Set up test fixtures once for all tests (class-level)."""
        # Create users
        cls.owner = create_test_user(username_prefix="owner")
        cls.reviewer = create_test_user(username_prefix="reviewer")

        # Create organisation
        cls.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-security"
        )
        OrganisationMembership.objects.create(
            organisation=cls.organisation,
            user=cls.owner,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

    def setUp(self):
        """Set up test fixtures for each test (instance-level)."""
        # Create session
        self.session = SearchSession.objects.create(
            title="Security Test Session",
            description="Test session for security tests",
            owner=self.owner,
            organisation=self.organisation,
            status="draft",
        )

        # Create configuration with invited reviewers
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            created_by=self.owner,
            min_reviewers_per_result=2,
            consensus_criteria="MAJORITY",
            conflict_resolution_method="LEAD_ARBITRATION",
            invited_reviewers=[
                {
                    "email": self.reviewer.email,
                    "first_name": "Test",
                    "last_name": "Reviewer",
                }
            ],
        )
        # Set as current configuration
        self.session.current_configuration = self.config
        self.session.save(update_fields=["current_configuration"])

        # Create search strategy
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.owner,
            population_terms=["elderly", "older adults"],
            interest_terms=["falls prevention", "fall risk"],
            context_terms=["community", "home"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "search_type": "google",
                "max_results": 50,
            },
        )

        # Create request factory
        self.factory = RequestFactory()

    # -------------------------------------------------------------------------
    # Phase 1: Test Invitations Not Sent During Setup
    # -------------------------------------------------------------------------

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_invitations_not_sent_during_setup(self, mock_send_email):
        """
        Test that ReviewInvitation records are NOT created during combined session creation.

        Phase 1 fix removed invitation sending from the combined session creation view.
        Invitations should only be created when session reaches ready_for_review.
        Now tests combined SessionCreateView which includes configuration.
        """
        mock_send_email.return_value = True

        # Log in as owner
        self.client.login(username=self.owner.username, password="testpass123")

        # Create session with combined form (includes reviewer configuration).
        # Use a title distinct from the setUp fixture session (also titled
        # "Security Test Session") so the get() below is unambiguous.
        create_url = reverse("review_manager:create_session")
        _response = self.client.post(
            create_url,
            {
                "title": "Combined Setup Security Session",
                "description": "Testing invitation security",
                # Owner is a member of more than one org (personal + team), so
                # the explicit selector is required (Issue #171).
                "organisation": str(self.organisation.id),
                "invited_reviewers_data": '[{"email": "reviewer@example.com", "first_name": "Test", "last_name": "Reviewer"}]',
                "min_reviewers_per_result": "2",
                "consensus_criteria": "MAJORITY",
                "conflict_resolution_method": "LEAD_ARBITRATION",
            },
            follow=True,
        )

        # Verify no invitations created
        session = SearchSession.objects.get(title="Combined Setup Security Session")
        invitation_count = ReviewInvitation.objects.filter(session=session).count()
        self.assertEqual(
            invitation_count,
            0,
            "Invitations should NOT be created during session creation",
        )

        # Verify email was NOT sent
        mock_send_email.assert_not_called()

    # -------------------------------------------------------------------------
    # Phase 2: Test Invitations Sent at Ready for Review
    # -------------------------------------------------------------------------

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_invitations_sent_at_ready_for_review(self, mock_send_email):
        """
        Test that invitations are sent automatically when session reaches ready_for_review status.

        Phase 2 fix added signal handler in signals.py to send invitations
        when status changes to ready_for_review.
        """
        mock_send_email.return_value = True

        # Verify no invitations exist yet
        self.assertEqual(
            ReviewInvitation.objects.filter(session=self.session).count(), 0
        )

        # Change session status to ready_for_review
        # This should trigger the signal handler
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["status"])

        # Verify invitation was created
        invitation_count = ReviewInvitation.objects.filter(session=self.session).count()
        self.assertEqual(
            invitation_count,
            1,
            "Invitation should be created when status changes to ready_for_review",
        )

        # Verify invitation details
        invitation = ReviewInvitation.objects.get(session=self.session)
        self.assertEqual(invitation.invitee_email, self.reviewer.email)
        self.assertEqual(invitation.inviter, self.owner)
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_PENDING)

        # Verify email was sent
        mock_send_email.assert_called_once()

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_invitations_not_duplicated_on_status_update(self, mock_send_email):
        """
        Test that invitations are not duplicated if status changes again.

        Signal handler should check for existing invitations and skip if already sent.
        """
        mock_send_email.return_value = True

        # First status change to ready_for_review
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["status"])

        # Verify one invitation created
        self.assertEqual(
            ReviewInvitation.objects.filter(session=self.session).count(), 1
        )
        self.assertEqual(mock_send_email.call_count, 1)

        # Second status change (e.g., back to under_review)
        self.session.status = "under_review"
        self.session.save(update_fields=["status"])

        # Third status change back to ready_for_review
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["status"])

        # Verify still only one invitation (no duplicates)
        self.assertEqual(
            ReviewInvitation.objects.filter(session=self.session).count(),
            1,
            "Should not create duplicate invitations",
        )

        # Email should only be sent once (first time)
        self.assertEqual(mock_send_email.call_count, 1)

    # -------------------------------------------------------------------------
    # Phase 3: Test Reviewer Cannot Access Strategy
    # -------------------------------------------------------------------------

    def test_reviewer_cannot_access_strategy_view(self):
        """
        Test that reviewers (non-owners) cannot access search strategy views.

        Phase 3 fix added permission checking to SearchStrategyView.dispatch()
        to raise PermissionDenied for non-owners.
        """
        # Create and accept invitation
        _invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee_email=self.reviewer.email,
            invitee_name="Test Reviewer",
            invitee=self.reviewer,
            status=ReviewInvitation.STATUS_ACCEPTED,
        )

        # Log in as reviewer
        self.client.login(username=self.reviewer.username, password="testpass123")

        # Attempt to access strategy form
        strategy_url = reverse("search_strategy:strategy_form", args=[self.session.id])
        response = self.client.get(strategy_url)

        # Verify PermissionDenied (403 Forbidden)
        self.assertEqual(
            response.status_code,
            403,
            "Reviewers should get 403 Forbidden when accessing strategy",
        )

    def test_reviewer_cannot_access_strategy_via_dispatch(self):
        """
        Test that SearchStrategyView.dispatch() raises PermissionDenied for reviewers.

        This tests the dispatch() method directly to ensure the security check
        is enforced at the view level.
        """
        # Create accepted invitation
        _invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee_email=self.reviewer.email,
            invitee_name="Test Reviewer",
            invitee=self.reviewer,
            status=ReviewInvitation.STATUS_ACCEPTED,
        )

        # Create request as reviewer
        request = self.factory.get(
            reverse("search_strategy:strategy_form", args=[self.session.id])
        )
        request.user = self.reviewer

        # Create view instance
        view = SearchStrategyView()
        view.request = request  # Set request attribute for dispatch
        view.kwargs = {"session_id": str(self.session.id)}

        # Attempt to dispatch - should raise PermissionDenied
        with self.assertRaises(PermissionDenied) as context:
            view.dispatch(request, session_id=str(self.session.id))

        # Verify error message (from SessionOwnershipMixin.get_session())
        self.assertIn(
            "permission to access this session",
            str(context.exception),
        )

    # -------------------------------------------------------------------------
    # Phase 4: Test Owner Can Still Access Strategy
    # -------------------------------------------------------------------------

    def test_owner_can_access_strategy(self):
        """
        Test that session owners can still access search strategy views.

        Security fix should only block reviewers, not owners.
        """
        # Log in as owner
        self.client.login(username=self.owner.username, password="testpass123")

        # Access strategy form
        strategy_url = reverse("search_strategy:strategy_form", args=[self.session.id])
        response = self.client.get(strategy_url)

        # Verify success (200 OK)
        self.assertEqual(
            response.status_code,
            200,
            "Owners should be able to access strategy",
        )

        # Verify correct template used
        self.assertTemplateUsed(response, "search_strategy/strategy_form.html")

    def test_owner_can_access_strategy_via_dispatch(self):
        """
        Test that SearchStrategyView.dispatch() allows owners through.

        This tests the dispatch() method directly to ensure owners are not blocked.
        """
        # Create request as owner
        request = self.factory.get(
            reverse("search_strategy:strategy_form", args=[self.session.id])
        )
        request.user = self.owner

        # Mock messages middleware
        from django.contrib.messages.storage.fallback import FallbackStorage

        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))

        # Create view instance
        view = SearchStrategyView()
        view.request = request
        view.kwargs = {"session_id": str(self.session.id)}

        # Dispatch should succeed without raising PermissionDenied
        try:
            _response = view.dispatch(request, session_id=str(self.session.id))
            # If we get here, dispatch succeeded (no PermissionDenied)
            self.assertTrue(True, "Owner dispatch succeeded")
        except PermissionDenied:
            self.fail("Owner should be able to access strategy via dispatch")

    # -------------------------------------------------------------------------
    # Edge Cases
    # -------------------------------------------------------------------------

    def test_invitations_not_sent_if_no_reviewers_configured(self):
        """
        Test that signal handler handles sessions with no invited reviewers gracefully.
        """
        # Create session without invited reviewers
        session_no_reviewers = SearchSession.objects.create(
            title="No Reviewers Session",
            owner=self.owner,
            organisation=self.organisation,
            status="draft",
        )

        # Create configuration without invited_reviewers
        config = ReviewConfiguration.objects.create(
            session=session_no_reviewers,
            created_by=self.owner,
            min_reviewers_per_result=1,
            consensus_criteria="MAJORITY",
            conflict_resolution_method="LEAD_ARBITRATION",
            invited_reviewers=[],  # Empty list
        )
        session_no_reviewers.current_configuration = config
        session_no_reviewers.save(update_fields=["current_configuration"])

        # Change status to ready_for_review
        session_no_reviewers.status = "ready_for_review"
        session_no_reviewers.save(update_fields=["status"])

        # Verify no invitations created (should handle gracefully)
        invitation_count = ReviewInvitation.objects.filter(
            session=session_no_reviewers
        ).count()
        self.assertEqual(
            invitation_count, 0, "No invitations should be created if none configured"
        )

    def test_invitations_not_sent_if_configuration_missing(self):
        """
        Test that signal handler handles sessions without configuration gracefully.
        """
        # Create session without configuration
        session_no_config = SearchSession.objects.create(
            title="No Config Session",
            owner=self.owner,
            organisation=self.organisation,
            status="draft",
        )

        # Change status to ready_for_review (no configuration set)
        session_no_config.status = "ready_for_review"
        session_no_config.save(update_fields=["status"])

        # Verify no invitations created (should handle gracefully)
        invitation_count = ReviewInvitation.objects.filter(
            session=session_no_config
        ).count()
        self.assertEqual(
            invitation_count, 0, "Should handle missing configuration gracefully"
        )
