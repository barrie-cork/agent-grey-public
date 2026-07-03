"""
Unit tests for Review Setup Configuration form validation.

Tests ReviewConfigurationForm validation logic including:
- Pre-population of organisation defaults
- Arbitrator field validation for DESIGNATED_ARBITRATOR method
- Min reviewers exceeds available reviewers
- Email format validation
- SessionCreateView invitation integration (Phase 6)
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.forms import ReviewConfigurationForm
from apps.review_manager.models import (
    ReviewConfiguration,
    ReviewInvitation,
    SearchSession,
)
from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user

User = get_user_model()


class ReviewConfigurationFormTest(TestCase):
    """Test suite for ReviewConfigurationForm validation."""

    def setUp(self):
        """Create test user, organisation, and session for form testing."""
        self.user = create_test_user()

        self.organisation = Organisation.objects.create(
            name="Test Organisation",
            slug="test-org",
            default_review_mode="DUAL",
            default_conflict_resolution_method="DESIGNATED_ARBITRATOR",
        )

        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            organisation=self.organisation,
            status="ready_for_review",
        )

    def test_form_pre_populates_organisation_defaults(self):
        """
        Test that form initialises with organisation default values
        for conflict_resolution_method and min_reviewers_per_result
        when no ReviewConfiguration exists yet.
        """
        # Delete auto-created ReviewConfiguration so form enters pre-population branch
        ReviewConfiguration.objects.filter(session=self.session).delete()

        form = ReviewConfigurationForm(session=self.session)

        self.assertEqual(
            form.fields["conflict_resolution_method"].initial, "DESIGNATED_ARBITRATOR"
        )
        self.assertEqual(form.fields["min_reviewers_per_result"].initial, 2)

    def test_form_arbitrator_fields_required_for_designated_arbitrator(self):
        """
        Test that arbitrator email and name are required when using
        DESIGNATED_ARBITRATOR conflict resolution method with multiple reviewers.
        Model clean() raises non-field ValidationError (goes to __all__).
        """
        invited_reviewers = json.dumps(
            [
                {
                    "first_name": "Test",
                    "last_name": "Reviewer",
                    "email": "reviewer@example.com",
                }
            ]
        )

        # Test 1: Empty email with DESIGNATED_ARBITRATOR
        form_data = {
            "min_reviewers_per_result": 2,
            "conflict_resolution_method": "DESIGNATED_ARBITRATOR",
            "consensus_criteria": "MAJORITY",
            "designated_arbitrator_email": "",
            "designated_arbitrator_name": "Dr. Jane Smith",
            "invited_reviewers_data": invited_reviewers,
        }
        form = ReviewConfigurationForm(data=form_data, session=self.session)
        self.assertFalse(form.is_valid())
        self.assertTrue(
            "__all__" in form.errors or "designated_arbitrator_email" in form.errors,
            f"Expected arbitrator email error, got: {form.errors}",
        )

        # Test 2: Empty name with DESIGNATED_ARBITRATOR
        form_data = {
            "min_reviewers_per_result": 2,
            "conflict_resolution_method": "DESIGNATED_ARBITRATOR",
            "consensus_criteria": "MAJORITY",
            "designated_arbitrator_email": "jane.smith@example.com",
            "designated_arbitrator_name": "",
            "invited_reviewers_data": invited_reviewers,
        }
        form = ReviewConfigurationForm(data=form_data, session=self.session)
        self.assertFalse(form.is_valid())
        self.assertTrue(
            "__all__" in form.errors or "designated_arbitrator_name" in form.errors,
            f"Expected arbitrator name error, got: {form.errors}",
        )

    def test_form_arbitrator_fields_not_required_for_other_methods(self):
        """
        Test that arbitrator fields are not required when using conflict
        resolution methods other than DESIGNATED_ARBITRATOR.
        """
        # LEAD_ARBITRATION with empty arbitrator fields
        form_data = {
            "min_reviewers_per_result": 1,
            "conflict_resolution_method": "LEAD_ARBITRATION",
            "consensus_criteria": "MAJORITY",
            "designated_arbitrator_email": "",
            "designated_arbitrator_name": "",
        }
        form = ReviewConfigurationForm(data=form_data, session=self.session)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        # CONSENSUS with empty arbitrator fields
        form_data = {
            "min_reviewers_per_result": 1,
            "conflict_resolution_method": "CONSENSUS",
            "consensus_criteria": "MAJORITY",
            "designated_arbitrator_email": "",
            "designated_arbitrator_name": "",
        }
        form = ReviewConfigurationForm(data=form_data, session=self.session)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_form_min_reviewers_validation(self):
        """
        Test that min_reviewers_per_result cannot exceed total available reviewers.
        """
        # No invited reviewers, so total = 1 (lead only)
        # min_reviewers=2 exceeds available
        form_data = {
            "min_reviewers_per_result": 2,
            "conflict_resolution_method": "CONSENSUS",
            "consensus_criteria": "MAJORITY",
            "designated_arbitrator_email": "",
            "designated_arbitrator_name": "",
        }
        form = ReviewConfigurationForm(data=form_data, session=self.session)
        self.assertFalse(form.is_valid())
        self.assertIn("min_reviewers_per_result", form.errors)

    def test_form_min_reviewers_valid_with_invited_reviewers(self):
        """
        Test that min_reviewers passes when enough invited reviewers provided.
        """
        invited_reviewers = [
            {
                "email": "reviewer1@example.com",
                "first_name": "John",
                "last_name": "Doe",
            },
        ]
        form_data = {
            "min_reviewers_per_result": 2,
            "conflict_resolution_method": "CONSENSUS",
            "consensus_criteria": "MAJORITY",
            "invited_reviewers_data": json.dumps(invited_reviewers),
            "designated_arbitrator_email": "",
            "designated_arbitrator_name": "",
        }
        form = ReviewConfigurationForm(data=form_data, session=self.session)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_form_invalid_email_format(self):
        """
        Test that Django email validation catches invalid email formats.
        """
        # Invalid email
        form_data = {
            "min_reviewers_per_result": 1,
            "conflict_resolution_method": "DESIGNATED_ARBITRATOR",
            "consensus_criteria": "MAJORITY",
            "designated_arbitrator_email": "not-an-email",
            "designated_arbitrator_name": "Dr. John Smith",
        }
        form = ReviewConfigurationForm(data=form_data, session=self.session)
        self.assertFalse(form.is_valid())
        self.assertIn("designated_arbitrator_email", form.errors)

        # Valid email
        form_data = {
            "min_reviewers_per_result": 1,
            "conflict_resolution_method": "DESIGNATED_ARBITRATOR",
            "consensus_criteria": "MAJORITY",
            "designated_arbitrator_email": "test@example.com",
            "designated_arbitrator_name": "Dr. John Smith",
        }
        form = ReviewConfigurationForm(data=form_data, session=self.session)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")


class SessionCreateViewIntegrationTest(TestCase):
    """Test suite for SessionCreateView combined session + config flow."""

    def setUp(self):
        """Create test user, organisation for view testing."""
        self.user = create_test_user()

        self.organisation = Organisation.objects.create(
            name="Test Organisation",
            slug="test-org",
            default_min_reviewers=2,
            default_conflict_resolution_method="CONSENSUS",
        )

        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.user,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

        self.client.login(username=self.user.username, password="testpass123")

    def test_combined_form_creates_session_and_config(self):
        """
        Test that combined form creates both session and ReviewConfiguration.

        Invitations are NOT created during form_valid -- they are deferred
        until the session reaches 'ready_for_review' via signals.
        See apps/review_manager/signals.py:send_invitations_when_ready().
        """
        invited_reviewers = [
            {
                "email": "reviewer1@example.com",
                "first_name": "John",
                "last_name": "Doe",
            },
            {
                "email": "reviewer2@example.com",
                "first_name": "Jane",
                "last_name": "Smith",
            },
        ]

        form_data = {
            "title": "Combined Test Session",
            "description": "Testing combined form",
            # The user has more than one active organisation (personal + team),
            # so the explicit organisation selector is required (Issue #171).
            "organisation": str(self.organisation.id),
            "min_reviewers_per_result": 2,
            "conflict_resolution_method": "CONSENSUS",
            "consensus_criteria": "MAJORITY",
            "invited_reviewers_data": json.dumps(invited_reviewers),
            "designated_arbitrator_email": "",
            "designated_arbitrator_name": "",
        }

        url = reverse("review_manager:create_session")
        response = self.client.post(url, data=form_data)

        # Verify redirect to session detail
        self.assertEqual(response.status_code, 302)

        # Verify session was created
        session = SearchSession.objects.get(title="Combined Test Session")
        self.assertEqual(session.owner, self.user)
        # Assignment is deterministic (Issue #171): the session must be assigned
        # to the SPECIFIC organisation chosen in the form, not an arbitrary
        # .first() membership.
        self.assertEqual(session.organisation, self.organisation)

        # Verify invited reviewers stored in configuration
        config = session.current_configuration
        self.assertIsNotNone(config)
        self.assertEqual(len(config.invited_reviewers), 2)
        self.assertEqual(config.invited_reviewers[0]["email"], "reviewer1@example.com")
        self.assertEqual(config.invited_reviewers[1]["email"], "reviewer2@example.com")

        # Verify NO ReviewInvitation records created at this stage
        invitations = ReviewInvitation.objects.filter(session=session)
        self.assertEqual(invitations.count(), 0)

    def test_combined_form_works_with_minimal_config(self):
        """
        Test that combined form works when only title/description are provided.
        Creates session without ReviewConfiguration when no config fields set.
        """
        form_data = {
            "title": "Minimal Test Session",
            "description": "Testing minimal config",
            # Multi-org user must pick an organisation (Issue #171).
            "organisation": str(self.organisation.id),
        }

        url = reverse("review_manager:create_session")
        response = self.client.post(url, data=form_data)

        # Verify redirect to session detail
        self.assertEqual(response.status_code, 302)

        # Verify session was created
        session = SearchSession.objects.get(title="Minimal Test Session")
        self.assertEqual(session.owner, self.user)

        # No configuration created when only title/description provided
        self.assertIsNone(session.current_configuration)

    def test_multi_org_user_honours_organisation_selection(self):
        """
        Multi-org user: the session is assigned to the organisation explicitly
        selected on the form, not the first membership (Issue #171).
        """
        # The user already has the personal org (from the signal) and the team
        # org from setUp. Add a SECOND team org and select it, proving the
        # chosen organisation is honoured rather than an arbitrary .first().
        second_org = Organisation.objects.create(
            name="Second Organisation",
            slug="second-org",
        )
        OrganisationMembership.objects.create(
            organisation=second_org,
            user=self.user,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

        form_data = {
            "title": "Multi-org Selection Session",
            "description": "Honour the explicit selection",
            "organisation": str(second_org.id),
        }

        url = reverse("review_manager:create_session")
        response = self.client.post(url, data=form_data)

        self.assertEqual(response.status_code, 302)

        session = SearchSession.objects.get(title="Multi-org Selection Session")
        self.assertEqual(session.organisation, second_org)

    def test_multi_org_selector_present_in_form(self):
        """
        Multi-org user: the organisation selector is added to the form and the
        template flag is set (Issue #171).
        """
        url = reverse("review_manager:create_session")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_organisation_selector"])
        self.assertIn("organisation", response.context["form"].fields)

    def test_cross_org_assignment_rejected(self):
        """
        Multi-org user: selecting an organisation the user is NOT an active
        member of is rejected with a validation error and no session is created
        (Issue #171).
        """
        # An organisation the user has no membership in.
        foreign_org = Organisation.objects.create(
            name="Foreign Organisation",
            slug="foreign-org",
        )

        form_data = {
            "title": "Cross-org Attempt Session",
            "description": "Should be rejected",
            "organisation": str(foreign_org.id),
        }

        url = reverse("review_manager:create_session")
        response = self.client.post(url, data=form_data)

        # Form re-renders (no redirect) with an organisation error.
        self.assertEqual(response.status_code, 200)
        self.assertIn("organisation", response.context["form"].errors)

        # No session was created.
        self.assertFalse(
            SearchSession.objects.filter(title="Cross-org Attempt Session").exists()
        )


class SingleOrgSessionCreateViewTest(DisablePersonalOrgSignalMixin, TestCase):
    """SessionCreateView behaviour for users with exactly one active organisation.

    Uses DisablePersonalOrgSignalMixin so no personal organisation is
    auto-created, leaving the user with a single deliberate membership.
    """

    def setUp(self):
        """Create a user with exactly one active organisation membership."""
        self.user = create_test_user()

        self.organisation = Organisation.objects.create(
            name="Solo Organisation",
            slug="solo-org",
        )
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.user,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

        self.client.login(username=self.user.username, password="testpass123")

    def test_single_org_user_auto_assigned_with_no_selector(self):
        """
        Single-org user: no selector is shown and the session is silently
        auto-assigned to the user's only organisation (Issue #171).
        """
        url = reverse("review_manager:create_session")

        # GET: selector absent.
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)
        self.assertFalse(get_response.context["show_organisation_selector"])
        self.assertNotIn("organisation", get_response.context["form"].fields)

        # POST without an organisation field: still auto-assigned.
        form_data = {
            "title": "Solo Session",
            "description": "Auto-assigned to the only org",
        }
        post_response = self.client.post(url, data=form_data)
        self.assertEqual(post_response.status_code, 302)

        session = SearchSession.objects.get(title="Solo Session")
        self.assertEqual(session.organisation, self.organisation)
