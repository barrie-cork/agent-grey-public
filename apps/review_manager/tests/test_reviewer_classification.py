"""
Tests for reviewer classification functionality.

Tests Phase B implementation:
- Classification of internal vs external reviewers
- Utility functions for approval workflow
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.utils import (
    is_user_in_organisation,
    classify_invited_reviewers,
    requires_is_approval_for_external,
    get_invitation_rate_limit,
    get_invitation_expiry_days,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ReviewerClassificationTests(TestCase):
    """Test reviewer classification into internal and external categories."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create internal users (members of organisation)
        # Email must match what tests pass to is_user_in_organisation
        self.internal_user1 = create_test_user(
            username_prefix="alice",
            email="alice@ourorg.com",
            first_name="Alice",
            last_name="Smith",
        )
        OrganisationMembership.objects.create(
            user=self.internal_user1,
            organisation=self.org,
            role="REVIEWER",
            is_active=True,
        )

        self.internal_user2 = create_test_user(
            username_prefix="charlie",
            email="charlie@ourorg.com",
            first_name="Charlie",
            last_name="Brown",
        )
        OrganisationMembership.objects.create(
            user=self.internal_user2,
            organisation=self.org,
            role="REVIEWER",
            is_active=True,
        )

        # Create inactive member (should be treated as external)
        self.inactive_user = create_test_user(
            username_prefix="dave",
            email="dave@ourorg.com",
            first_name="Dave",
            last_name="Wilson",
        )
        OrganisationMembership.objects.create(
            user=self.inactive_user,
            organisation=self.org,
            role="REVIEWER",
            is_active=False,  # Inactive
        )

        # External users (not members) don't need to be created

    def test_is_user_in_organisation_active_member(self):
        """Active member is recognised as being in organisation."""
        self.assertTrue(is_user_in_organisation("alice@ourorg.com", self.org))
        self.assertTrue(is_user_in_organisation("charlie@ourorg.com", self.org))

    def test_is_user_in_organisation_inactive_member(self):
        """Inactive member is NOT considered in organisation."""
        self.assertFalse(is_user_in_organisation("dave@ourorg.com", self.org))

    def test_is_user_in_organisation_non_member(self):
        """Non-member is not in organisation."""
        self.assertFalse(is_user_in_organisation("bob@external.com", self.org))
        self.assertFalse(is_user_in_organisation("stranger@unknown.com", self.org))

    def test_classify_all_internal(self):
        """All reviewers are organisation members."""
        invited_reviewers = [
            {"email": "alice@ourorg.com", "first_name": "Alice", "last_name": "Smith"},
            {
                "email": "charlie@ourorg.com",
                "first_name": "Charlie",
                "last_name": "Brown",
            },
        ]

        classification = classify_invited_reviewers(invited_reviewers, self.org)

        self.assertEqual(len(classification["internal"]), 2)
        self.assertEqual(len(classification["external"]), 0)
        self.assertEqual(classification["counts"]["total"], 2)
        self.assertEqual(classification["counts"]["internal"], 2)
        self.assertEqual(classification["counts"]["external"], 0)

        # Verify correct emails in internal
        internal_emails = [r["email"] for r in classification["internal"]]
        self.assertIn("alice@ourorg.com", internal_emails)
        self.assertIn("charlie@ourorg.com", internal_emails)

    def test_classify_all_external(self):
        """All reviewers are outside organisation."""
        invited_reviewers = [
            {"email": "bob@external.com", "first_name": "Bob", "last_name": "Jones"},
            {"email": "eve@another.com", "first_name": "Eve", "last_name": "Taylor"},
            {"email": "frank@third.com", "first_name": "Frank", "last_name": "Miller"},
        ]

        classification = classify_invited_reviewers(invited_reviewers, self.org)

        self.assertEqual(len(classification["internal"]), 0)
        self.assertEqual(len(classification["external"]), 3)
        self.assertEqual(classification["counts"]["total"], 3)
        self.assertEqual(classification["counts"]["internal"], 0)
        self.assertEqual(classification["counts"]["external"], 3)

        # Verify correct emails in external
        external_emails = [r["email"] for r in classification["external"]]
        self.assertIn("bob@external.com", external_emails)
        self.assertIn("eve@another.com", external_emails)
        self.assertIn("frank@third.com", external_emails)

    def test_classify_mixed(self):
        """Mix of internal and external reviewers."""
        invited_reviewers = [
            {"email": "alice@ourorg.com", "first_name": "Alice", "last_name": "Smith"},
            {"email": "bob@external.com", "first_name": "Bob", "last_name": "Jones"},
            {
                "email": "charlie@ourorg.com",
                "first_name": "Charlie",
                "last_name": "Brown",
            },
            {"email": "eve@another.com", "first_name": "Eve", "last_name": "Taylor"},
        ]

        classification = classify_invited_reviewers(invited_reviewers, self.org)

        self.assertEqual(len(classification["internal"]), 2)
        self.assertEqual(len(classification["external"]), 2)
        self.assertEqual(classification["counts"]["total"], 4)
        self.assertEqual(classification["counts"]["internal"], 2)
        self.assertEqual(classification["counts"]["external"], 2)

        # Verify correct classification
        internal_emails = [r["email"] for r in classification["internal"]]
        external_emails = [r["email"] for r in classification["external"]]

        self.assertIn("alice@ourorg.com", internal_emails)
        self.assertIn("charlie@ourorg.com", internal_emails)
        self.assertIn("bob@external.com", external_emails)
        self.assertIn("eve@another.com", external_emails)

    def test_classify_inactive_member_as_external(self):
        """Inactive member should be classified as external."""
        invited_reviewers = [
            {"email": "dave@ourorg.com", "first_name": "Dave", "last_name": "Wilson"},
        ]

        classification = classify_invited_reviewers(invited_reviewers, self.org)

        # Dave is inactive, so should be external
        self.assertEqual(len(classification["internal"]), 0)
        self.assertEqual(len(classification["external"]), 1)
        self.assertEqual(classification["external"][0]["email"], "dave@ourorg.com")

    def test_classify_empty_list(self):
        """Empty reviewer list returns empty classification."""
        invited_reviewers = []

        classification = classify_invited_reviewers(invited_reviewers, self.org)

        self.assertEqual(len(classification["internal"]), 0)
        self.assertEqual(len(classification["external"]), 0)
        self.assertEqual(classification["counts"]["total"], 0)

    def test_classify_skips_empty_emails(self):
        """Empty emails are skipped in classification."""
        invited_reviewers = [
            {"email": "", "first_name": "No", "last_name": "Email"},
            {"email": "alice@ourorg.com", "first_name": "Alice", "last_name": "Smith"},
            {"email": "   ", "first_name": "Whitespace", "last_name": "Only"},
        ]

        classification = classify_invited_reviewers(invited_reviewers, self.org)

        # Only alice should be processed
        self.assertEqual(classification["counts"]["total"], 3)  # Total includes empties
        self.assertEqual(len(classification["internal"]), 1)
        self.assertEqual(classification["internal"][0]["email"], "alice@ourorg.com")

    def test_classify_preserves_reviewer_data(self):
        """Classification preserves all reviewer dictionary data."""
        invited_reviewers = [
            {
                "email": "alice@ourorg.com",
                "first_name": "Alice",
                "last_name": "Smith",
                "custom_field": "custom_value",
            },
        ]

        classification = classify_invited_reviewers(invited_reviewers, self.org)

        # Verify all fields preserved
        internal_reviewer = classification["internal"][0]
        self.assertEqual(internal_reviewer["email"], "alice@ourorg.com")
        self.assertEqual(internal_reviewer["first_name"], "Alice")
        self.assertEqual(internal_reviewer["last_name"], "Smith")
        self.assertEqual(internal_reviewer["custom_field"], "custom_value")

    def test_requires_is_approval_for_external_default(self):
        """Default should be False (approval not required) for Phase B."""
        self.assertFalse(requires_is_approval_for_external())

    def test_get_invitation_rate_limit_default(self):
        """Default rate limit should be 10."""
        self.assertEqual(get_invitation_rate_limit(), 10)

    def test_get_invitation_expiry_days_default(self):
        """Default expiry should be 7 days."""
        self.assertEqual(get_invitation_expiry_days(), 7)
