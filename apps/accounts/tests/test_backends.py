"""
Tests for RoleBasedPermissionBackend caching optimisation.

Tests the three-level caching strategy used by the authentication backend
to minimize database queries when checking permissions.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.backends import RoleBasedPermissionBackend
from apps.accounts.permissions import Permissions
from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestBackendCaching(TestCase):
    """Test RoleBasedPermissionBackend caching optimisation."""

    def setUp(self):
        """Set up test data."""
        self.backend = RoleBasedPermissionBackend()

        # Create test user
        self.user = create_test_user()

        # Create test organisation with unique slug
        # Use get_or_create to avoid duplicate key errors in test database
        self.org, _ = Organisation.objects.get_or_create(
            slug="test-org-backend",
            defaults={
                "name": "Test Organisation Backend",
            },
        )

        # Create membership
        self.membership = OrganisationMembership.objects.create(
            user=self.user, organisation=self.org, role="REVIEWER", is_active=True
        )

        # Create test session for permission checks
        self.session = SearchSession.objects.create(
            title="Test Session", organisation=self.org, owner=self.user
        )

    def test_has_perm_uses_cached_membership(self):
        """Backend should use cached membership to avoid database queries."""
        # Pre-cache membership on user object
        self.user._cached_memberships = {
            f"{self.user.id}:{self.org.id}": self.membership
        }

        # Permission check should NOT hit database
        with self.assertNumQueries(0):
            result = self.backend.has_perm(
                self.user, Permissions.RESULT_CLAIM, self.session
            )

        self.assertTrue(result)

    def test_has_perm_caches_on_first_call(self):
        """Backend should cache membership after first database query."""
        # First call: 1 query to fetch membership
        with self.assertNumQueries(1):
            result1 = self.backend.has_perm(
                self.user, Permissions.RESULT_CLAIM, self.session
            )

        self.assertTrue(result1)

        # Verify cache was populated
        self.assertTrue(hasattr(self.user, "_cached_memberships"))
        cache_key = f"{self.user.id}:{self.org.id}"
        self.assertIn(cache_key, self.user._cached_memberships)
        self.assertEqual(self.user._cached_memberships[cache_key], self.membership)

        # Second call: 0 queries (cache hit)
        with self.assertNumQueries(0):
            result2 = self.backend.has_perm(
                self.user, Permissions.RESULT_SUBMIT, self.session
            )

        self.assertTrue(result2)

    def test_reviewer_has_claim_permission(self):
        """REVIEWER role should have claim permission."""
        result = self.backend.has_perm(
            self.user, Permissions.RESULT_CLAIM, self.session
        )
        self.assertTrue(result)

    def test_reviewer_has_submit_permission(self):
        """REVIEWER role should have submit permission."""
        result = self.backend.has_perm(
            self.user, Permissions.RESULT_SUBMIT, self.session
        )
        self.assertTrue(result)

    def test_reviewer_cannot_create_review(self):
        """REVIEWER role should NOT have create review permission."""
        result = self.backend.has_perm(
            self.user, Permissions.REVIEW_CREATE, self.session
        )
        self.assertFalse(result)

    def test_information_specialist_has_all_permissions(self):
        """INFORMATION_SPECIALIST should have all permissions."""
        # Update membership to INFORMATION_SPECIALIST
        self.membership.role = "INFORMATION_SPECIALIST"
        self.membership.save()

        # Test various permissions
        permissions = [
            Permissions.RESULT_CLAIM,
            Permissions.RESULT_SUBMIT,
            Permissions.REVIEW_CREATE,
            Permissions.REVIEW_VIEW,
            Permissions.ORG_VIEW_DASHBOARD,
        ]

        for perm in permissions:
            with self.subTest(perm=perm):
                result = self.backend.has_perm(self.user, perm, self.session)
                self.assertTrue(result, f"INFORMATION_SPECIALIST should have {perm}")

    def test_lead_reviewer_can_edit_own_review(self):
        """LEAD_REVIEWER should be able to edit own review."""
        # Update membership to LEAD_REVIEWER
        self.membership.role = "LEAD_REVIEWER"
        self.membership.save()

        result = self.backend.has_perm(
            self.user, Permissions.REVIEW_EDIT_OWN, self.session
        )
        self.assertTrue(result)

    def test_lead_reviewer_cannot_edit_others_review(self):
        """LEAD_REVIEWER should NOT be able to edit others' review."""
        # Create another user
        other_user = create_test_user(username_prefix="otheruser")

        # Create membership for other user
        OrganisationMembership.objects.create(
            user=other_user, organisation=self.org, role="LEAD_REVIEWER", is_active=True
        )

        # Test that other_user cannot edit self.user's session
        result = self.backend.has_perm(
            other_user, Permissions.REVIEW_EDIT_OWN, self.session
        )
        self.assertFalse(result)

    def test_no_permission_without_organisation(self):
        """Should deny permission when no organisation context."""
        result = self.backend.has_perm(self.user, Permissions.RESULT_CLAIM, obj=None)
        self.assertFalse(result)

    def test_no_permission_for_unauthenticated_user(self):
        """Should deny permission for unauthenticated user."""
        unauthenticated_user = User()
        result = self.backend.has_perm(
            unauthenticated_user, Permissions.RESULT_CLAIM, self.session
        )
        self.assertFalse(result)

    def test_no_permission_without_membership(self):
        """Should deny permission when user has no membership."""
        # Create user without membership
        user_no_membership = create_test_user(username_prefix="nomembership")

        result = self.backend.has_perm(
            user_no_membership, Permissions.RESULT_CLAIM, self.session
        )
        self.assertFalse(result)

    def test_cache_key_format(self):
        """
        Cache key MUST use 'user_id:org_id' format (not hyphen, not pk).

        CRITICAL: This format is documented in progress document line 684
        and must be enforced to ensure caching consistency across the codebase.
        """
        # Ensure cache is empty before test
        self.user._cached_memberships = {}

        # Trigger caching
        self.backend.has_perm(self.user, Permissions.RESULT_CLAIM, self.session)

        # Verify correct format exists (colon separator, .id not .pk)
        expected_key = f"{self.user.id}:{self.org.id}"
        self.assertIn(expected_key, self.user._cached_memberships)

        # Ensure wrong formats don't exist (common mistakes)
        wrong_key_hyphen = f"{self.user.id}-{self.org.id}"
        self.assertNotIn(
            wrong_key_hyphen,
            self.user._cached_memberships,
            "Cache key should use colon separator, not hyphen",
        )

        # Verify exactly one cache entry was created
        self.assertEqual(
            len(self.user._cached_memberships), 1, "Should only create one cache entry"
        )


class TestMultiOrgPermissionIsolation(TestCase):
    """Test that permissions are correctly scoped to the current organisation.

    Regression test for the multi-org permission escalation bug where
    has_perm() without obj iterates ALL cached memberships, granting
    permissions from any org rather than the current one.
    """

    def setUp(self):
        """Create a user with different roles in two organisations."""
        self.backend = RoleBasedPermissionBackend()

        self.user = create_test_user(username_prefix="multiorguser")

        # Org A: user is REVIEWER (can claim results)
        self.org_a, _ = Organisation.objects.get_or_create(
            slug="test-org-a-perms",
            defaults={"name": "Organisation A"},
        )
        self.membership_a = OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org_a,
            role="REVIEWER",
            is_active=True,
        )

        # Org B: user is OBSERVER (can only view final decisions)
        self.org_b, _ = Organisation.objects.get_or_create(
            slug="test-org-b-perms",
            defaults={"name": "Organisation B"},
        )
        self.membership_b = OrganisationMembership.objects.create(
            user=self.user,
            organisation=self.org_b,
            role="OBSERVER",
            is_active=True,
        )

    def test_no_cross_org_permission_escalation_with_obj(self):
        """User should NOT get Org A's REVIEWER perms when checking against Org B object."""
        session_b = SearchSession.objects.create(
            title="Org B Session",
            organisation=self.org_b,
            owner=self.user,
        )

        # With obj, backend correctly scopes to Org B -- OBSERVER cannot claim
        result = self.backend.has_perm(self.user, Permissions.RESULT_CLAIM, session_b)
        self.assertFalse(
            result,
            "OBSERVER in Org B should NOT have RESULT_CLAIM, "
            "even though user is REVIEWER in Org A",
        )

    def test_no_cross_org_escalation_without_obj_using_contextvar(self):
        """Without obj, backend should use contextvar to scope to current org."""
        from apps.organisation.context import set_current_org

        # Cache BOTH memberships (as middleware would for multi-org user)
        self.user._cached_memberships = {
            f"{self.user.id}:{self.org_a.id}": self.membership_a,
            f"{self.user.id}:{self.org_b.id}": self.membership_b,
        }

        # Set current org context to Org B (OBSERVER role)
        set_current_org(self.org_b)

        # Without obj, backend should use contextvar to find Org B membership
        result = self.backend.has_perm(self.user, Permissions.RESULT_CLAIM)
        self.assertFalse(
            result,
            "With Org B as current context, OBSERVER should NOT have RESULT_CLAIM",
        )

    def test_contextvar_grants_correct_org_permissions(self):
        """Contextvar should grant permissions from the correct org."""
        from apps.organisation.context import set_current_org

        self.user._cached_memberships = {
            f"{self.user.id}:{self.org_a.id}": self.membership_a,
            f"{self.user.id}:{self.org_b.id}": self.membership_b,
        }

        # Set current org context to Org A (REVIEWER role)
        set_current_org(self.org_a)

        # REVIEWER in Org A should have RESULT_CLAIM
        result = self.backend.has_perm(self.user, Permissions.RESULT_CLAIM)
        self.assertTrue(
            result,
            "With Org A as current context, REVIEWER should have RESULT_CLAIM",
        )

        # REVIEWER in Org A should NOT have REVIEW_CREATE
        result = self.backend.has_perm(self.user, Permissions.REVIEW_CREATE)
        self.assertFalse(
            result,
            "REVIEWER should NOT have REVIEW_CREATE even in correct org context",
        )
