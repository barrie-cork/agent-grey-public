"""
Tests for centralised permission registry.

Tests the Permissions class that provides type-safe permission constants
and role-to-permission mappings for Agent Grey's authentication backend.
"""

from django.test import TestCase

from apps.accounts.permissions import Permissions


class TestPermissions(TestCase):
    """Test centralised permission registry."""

    def test_all_roles_have_permissions(self):
        """Every role should return a non-empty permission list."""
        roles = [
            "INFORMATION_SPECIALIST",
            "SENIOR_RESEARCHER",
            "LEAD_REVIEWER",
            "REVIEWER",
            "OBSERVER",
        ]

        for role in roles:
            perms = Permissions.get_role_permissions(role)
            assert len(perms) > 0, f"Role {role} has no permissions"

    def test_information_specialist_has_wildcard(self):
        """Information Specialist should have wildcard permission."""
        perms = Permissions.get_role_permissions("INFORMATION_SPECIALIST")
        assert Permissions.ALL_PERMISSIONS in perms
        assert "*" in perms

    def test_reviewer_can_claim_and_submit(self):
        """Reviewer role should have claim and submit permissions."""
        perms = Permissions.get_role_permissions("REVIEWER")
        assert Permissions.RESULT_CLAIM in perms
        assert Permissions.RESULT_SUBMIT in perms
        assert "review_results.claim_result" in perms
        assert "review_results.submit_decision" in perms

    def test_lead_reviewer_permissions(self):
        """Lead Reviewer should have review creation and management permissions."""
        perms = Permissions.get_role_permissions("LEAD_REVIEWER")
        assert Permissions.REVIEW_CREATE in perms
        assert Permissions.REVIEW_EDIT_OWN in perms
        assert Permissions.REVIEW_INVITE_REVIEWERS in perms

    def test_senior_researcher_permissions(self):
        """Senior Researcher should have view and export permissions."""
        perms = Permissions.get_role_permissions("SENIOR_RESEARCHER")
        assert Permissions.REVIEW_VIEW in perms
        assert Permissions.REVIEW_VIEW_METRICS in perms
        assert Permissions.ORG_VIEW_DASHBOARD in perms
        assert Permissions.ORG_EXPORT_REPORTS in perms

    def test_observer_permissions(self):
        """Observer should only have view final decisions permission."""
        perms = Permissions.get_role_permissions("OBSERVER")
        assert Permissions.RESULT_VIEW_FINAL in perms
        assert len(perms) == 1

    def test_invalid_role_raises_error(self):
        """Invalid role should raise ValueError."""
        with self.assertRaises(ValueError) as context:
            Permissions.get_role_permissions("INVALID_ROLE")
        self.assertIn("Unknown role", str(context.exception))

    def test_permission_constants_are_strings(self):
        """All permission constants should be string values."""
        assert isinstance(Permissions.REVIEW_CREATE, str)
        assert isinstance(Permissions.RESULT_CLAIM, str)
        assert isinstance(Permissions.ORG_VIEW_DASHBOARD, str)
        assert isinstance(Permissions.ALL_PERMISSIONS, str)

    def test_permission_string_format(self):
        """Permission strings should follow app_label.permission_name format."""
        # Review manager permissions
        assert Permissions.REVIEW_CREATE.startswith("review_manager.")
        assert Permissions.REVIEW_VIEW.startswith("review_manager.")

        # Review results permissions
        assert Permissions.RESULT_CLAIM.startswith("review_results.")
        assert Permissions.RESULT_SUBMIT.startswith("review_results.")

        # Organisation permissions
        assert Permissions.ORG_VIEW_DASHBOARD.startswith("organisation.")
        assert Permissions.ORG_EXPORT_REPORTS.startswith("organisation.")

    def test_no_duplicate_permissions_in_roles(self):
        """Each role should not have duplicate permissions."""
        roles = [
            "INFORMATION_SPECIALIST",
            "SENIOR_RESEARCHER",
            "LEAD_REVIEWER",
            "REVIEWER",
            "OBSERVER",
        ]

        for role in roles:
            perms = Permissions.get_role_permissions(role)
            assert len(perms) == len(
                set(perms)
            ), f"Role {role} has duplicate permissions"

    def test_all_roles_have_unique_app_labels(self):
        """Every role's permissions should reference valid app labels."""
        roles = [
            "INFORMATION_SPECIALIST",
            "SENIOR_RESEARCHER",
            "LEAD_REVIEWER",
            "REVIEWER",
            "OBSERVER",
        ]

        valid_prefixes = {"review_manager.", "review_results.", "organisation.", "*"}

        for role in roles:
            perms = Permissions.get_role_permissions(role)
            for perm in perms:
                if perm == "*":
                    continue
                assert any(
                    perm.startswith(p) for p in valid_prefixes if p != "*"
                ), f"Permission '{perm}' for role {role} has unexpected app label"
