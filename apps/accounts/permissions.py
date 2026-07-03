"""
Centralised permission string registry for Agent Grey.

Single source of truth for all permission definitions used across
RoleBasedPermissionBackend and DRF permission classes.

This module prevents hardcoded permission strings throughout the codebase,
provides type safety through constants, and makes refactoring easier.
"""


class Permissions:
    """Permission string constants for type safety and refactoring support."""

    # Review Manager Permissions
    REVIEW_CREATE = "review_manager.create_review"
    REVIEW_EDIT_OWN = "review_manager.edit_own_review"
    REVIEW_VIEW = "review_manager.view_review"
    REVIEW_INVITE_REVIEWERS = "review_manager.invite_reviewers"
    REVIEW_VIEW_METRICS = "review_manager.view_metrics"

    # Review Results Permissions
    RESULT_CLAIM = "review_results.claim_result"
    RESULT_SUBMIT = "review_results.submit_decision"
    RESULT_VIEW_FINAL = "review_results.view_final_decisions"
    CONFLICT_RESOLVE = "review_results.resolve_conflict"
    CONFLICT_VIEW = "review_results.view_conflict"
    CONFLICT_COMMENT = "review_results.comment_conflict"

    # Organisation Permissions
    ORG_VIEW_DASHBOARD = "organisation.view_dashboard"
    ORG_EXPORT_REPORTS = "organisation.export_reports"
    MANAGE_ORGANISATION = "organisation.manage_organisation"

    # Meta permissions
    ALL_PERMISSIONS = "*"  # Information Specialist wildcard

    @classmethod
    def get_role_permissions(cls, role: str) -> list[str]:
        """
        Get all permissions for a given organisation role.

        Args:
            role: OrganisationMembership.ROLE_CHOICES value
                (INFORMATION_SPECIALIST, SENIOR_RESEARCHER, LEAD_REVIEWER,
                 REVIEWER, or OBSERVER)

        Returns:
            List of permission strings (from constants above)

        Raises:
            ValueError: If role is not recognised

        Examples:
            >>> Permissions.get_role_permissions('REVIEWER')
            ['review_results.claim_result', 'review_results.submit_decision']

            >>> Permissions.get_role_permissions('INFORMATION_SPECIALIST')
            ['*']
        """
        role_map = {
            "INFORMATION_SPECIALIST": [
                cls.ALL_PERMISSIONS,
                cls.MANAGE_ORGANISATION,
            ],
            "SENIOR_RESEARCHER": [
                cls.REVIEW_VIEW,
                cls.REVIEW_VIEW_METRICS,
                cls.ORG_VIEW_DASHBOARD,
                cls.ORG_EXPORT_REPORTS,
                cls.CONFLICT_RESOLVE,
                cls.CONFLICT_VIEW,
            ],
            "LEAD_REVIEWER": [
                cls.REVIEW_CREATE,
                cls.REVIEW_EDIT_OWN,
                cls.REVIEW_INVITE_REVIEWERS,
                cls.RESULT_CLAIM,
                cls.RESULT_SUBMIT,
                cls.CONFLICT_VIEW,
            ],
            "REVIEWER": [
                cls.RESULT_CLAIM,
                cls.RESULT_SUBMIT,
            ],
            "OBSERVER": [
                cls.RESULT_VIEW_FINAL,
            ],
        }

        if role not in role_map:
            raise ValueError(f"Unknown role: {role}")

        return role_map[role]
