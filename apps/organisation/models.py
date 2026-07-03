"""
Organisation models for multi-tenant systematic review management.

Implements:
- Organisation: Multi-tenant container with quotas and org-wide defaults
- OrganisationMembership: User-to-org mapping with role-based permissions
- OrganisationInvitation: Email invitation system with magic links
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.core.models import AbstractInvitation, TimeStampedModel


class Organisation(TimeStampedModel):
    """
    Multi-tenant organisation for managing multiple reviews.

    Attributes:
        id: UUID primary key
        name: Organisation display name
        slug: URL-safe unique identifier
        default_review_mode: Default review mode for new projects
        default_min_reviewers: Minimum reviewers required per result
        require_dual_review: Enforce dual review for all projects (org policy)
        max_active_reviews: Maximum concurrent active reviews (null = unlimited)
        max_users: Maximum organisation members (null = unlimited)
        created_at: Timestamp when organisation was created
        updated_at: Timestamp when organisation was last modified
    """

    name = models.CharField(max_length=255, help_text="Organisation display name")
    slug = models.SlugField(unique=True, help_text="URL-safe identifier")

    # Organisation-wide defaults
    default_review_mode = models.CharField(
        max_length=20,
        choices=[
            ("SINGLE", "Single Reviewer"),
            ("DUAL", "Dual Independent Reviewers"),
            ("TRIPLE", "Triple Independent Reviewers"),
            ("QUAD", "Quad Independent Reviewers"),
        ],
        default="DUAL",
        help_text="Default review mode for new screening sessions",
        verbose_name="Default Review Mode",
    )
    default_min_reviewers = models.IntegerField(
        default=2,
        choices=[
            (1, "1 Reviewer (Single Screening)"),
            (2, "2 Reviewers (Dual Screening)"),
            (3, "3 Reviewers (Triple Screening)"),
            (4, "4 Reviewers (Multiple Screening)"),
        ],
        help_text="Default number of reviewers required per result",
    )
    require_dual_review = models.BooleanField(
        default=False, help_text="Enforce dual review for all projects (org policy)"
    )
    default_conflict_resolution_method = models.CharField(
        max_length=30,
        choices=[
            ("DESIGNATED_ARBITRATOR", "Designated Arbitrator"),
            ("LEAD_ARBITRATION", "Lead Reviewer Arbitrates"),
            ("CONSENSUS", "Consensus Discussion"),
            ("MAJORITY_VOTE", "Majority Vote"),
        ],
        default="DESIGNATED_ARBITRATOR",
        help_text="Default conflict resolution method for new reviews",
    )

    # Quotas (null = unlimited)
    max_active_reviews = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum concurrent active reviews (null = unlimited)",
    )
    max_users = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum organisation members (null = unlimited)",
    )

    class Meta:
        db_table = "organisations"
        verbose_name = "Organisation"
        verbose_name_plural = "Organisations"
        ordering = ["name"]

    def __str__(self):
        """Return string representation of the organisation."""
        return self.name

    def save(self, *args, **kwargs):
        """Override save to auto-generate slug from name if not provided."""
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_active_reviews_count(self):
        """
        Count active reviews in this organisation.

        Returns:
            int: Number of reviews in active states
        """
        return self.reviews.filter(
            status__in=[
                "executing",
                "processing_results",
                "ready_for_review",
                "under_review",
            ]
        ).count()

    def is_at_review_quota(self):
        """
        Check if organisation has reached review quota.

        Returns:
            bool: True if at or over quota, False if under quota or no quota set
        """
        if self.max_active_reviews is None:
            return False
        return self.get_active_reviews_count() >= self.max_active_reviews

    def get_members_count(self):
        """
        Count active members.

        Returns:
            int: Number of active members
        """
        return self.memberships.filter(is_active=True).count()

    def is_at_user_quota(self):
        """
        Check if organisation has reached user quota.

        Returns:
            bool: True if at or over quota, False if under quota or no quota set
        """
        if self.max_users is None:
            return False
        return self.get_members_count() >= self.max_users

    def get_review_defaults(self):
        """
        Get organisation-level default configuration values for new reviews.

        Returns:
            dict: Default configuration values with keys:
                - min_reviewers_per_result: Default number of reviewers (1-4)
                - conflict_resolution_method: Default conflict resolution method
                - consensus_criteria: Default consensus criteria (MAJORITY/UNANIMOUS)
        """
        return {
            "min_reviewers_per_result": self.default_min_reviewers,
            "conflict_resolution_method": self.default_conflict_resolution_method,
            "consensus_criteria": "MAJORITY",  # Default consensus
        }

    def is_member(self, user):
        """
        Check if user is an active member of this organisation.

        Args:
            user: User instance to check

        Returns:
            bool: True if user has active membership
        """
        return self.memberships.filter(user=user, is_active=True).exists()


class OrganisationMembership(models.Model):
    """
    Links users to organisations with roles and granular permissions.

    Attributes:
        id: UUID primary key
        organisation: FK to Organisation
        user: FK to User
        role: User role within organisation (5 role types)
        can_create_reviews: Permission to create new review projects
        can_manage_users: Permission to invite/remove organisation members
        can_view_all_reviews: Permission to view all reviews in organisation
        can_edit_configurations: Permission to modify organisation settings
        can_export_data: Permission to export organisation-wide reports
        joined_at: Timestamp when user joined organisation
        is_active: Whether membership is active
    """

    ROLE_INFORMATION_SPECIALIST = "INFORMATION_SPECIALIST"
    ROLE_SENIOR_RESEARCHER = "SENIOR_RESEARCHER"
    ROLE_LEAD_REVIEWER = "LEAD_REVIEWER"
    ROLE_REVIEWER = "REVIEWER"
    ROLE_OBSERVER = "OBSERVER"

    ROLE_CHOICES = [
        (ROLE_INFORMATION_SPECIALIST, "Information Specialist"),
        (ROLE_SENIOR_RESEARCHER, "Senior Researcher"),
        (ROLE_LEAD_REVIEWER, "Lead Reviewer"),
        (ROLE_REVIEWER, "Reviewer"),
        (ROLE_OBSERVER, "Observer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        "Organisation", on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organisation_memberships",
    )

    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        help_text="User role within this organisation",
    )

    # Granular permissions (override role defaults)
    can_create_reviews = models.BooleanField(
        default=False, help_text="Can create new review projects"
    )
    can_manage_users = models.BooleanField(
        default=False, help_text="Can invite/remove organisation members"
    )
    can_view_all_reviews = models.BooleanField(
        default=False, help_text="Can view all reviews in organisation"
    )
    can_edit_configurations = models.BooleanField(
        default=False, help_text="Can modify organisation settings"
    )
    can_export_data = models.BooleanField(
        default=False, help_text="Can export organisation-wide reports"
    )

    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive members retain historical data but lose access",
    )

    class Meta:
        db_table = "organisation_memberships"
        verbose_name = "Organisation Membership"
        verbose_name_plural = "Organisation Memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "user"],
                name="unique_organisation_user",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        """Return string representation of the membership."""
        return (
            f"{self.user.email} - {self.organisation.name} ({self.get_role_display()})"
        )

    def save(self, *args, **kwargs):
        """Override save to auto-set granular permissions based on role if creating new."""
        if self._state.adding:
            self._set_role_based_permissions()
        super().save(*args, **kwargs)

    def _set_role_based_permissions(self):
        """
        Set granular permissions based on role (only if not explicitly set).

        Role permission mapping from PRD Section 4.6:
        - Information Specialist: Full access
        - Senior Researcher: View all, export reports
        - Lead Reviewer: Create reviews, manage own projects
        - Reviewer: Review results only
        - Observer: View final decisions only
        """
        role_permissions = {
            self.ROLE_INFORMATION_SPECIALIST: {
                "can_create_reviews": True,
                "can_manage_users": True,
                "can_view_all_reviews": True,
                "can_edit_configurations": True,
                "can_export_data": True,
            },
            self.ROLE_SENIOR_RESEARCHER: {
                "can_create_reviews": False,
                "can_manage_users": False,
                "can_view_all_reviews": True,
                "can_edit_configurations": False,
                "can_export_data": True,
            },
            self.ROLE_LEAD_REVIEWER: {
                "can_create_reviews": True,
                "can_manage_users": False,
                "can_view_all_reviews": False,
                "can_edit_configurations": False,
                "can_export_data": False,
            },
            self.ROLE_REVIEWER: {
                "can_create_reviews": False,
                "can_manage_users": False,
                "can_view_all_reviews": False,
                "can_edit_configurations": False,
                "can_export_data": False,
            },
            self.ROLE_OBSERVER: {
                "can_create_reviews": False,
                "can_manage_users": False,
                "can_view_all_reviews": False,
                "can_edit_configurations": False,
                "can_export_data": False,
            },
        }

        # Apply role-based permissions
        if self.role in role_permissions:
            for perm, value in role_permissions[self.role].items():
                setattr(self, perm, value)


class OrganisationInvitation(AbstractInvitation):
    """
    Track email invitations to join organisation.

    Inherits token generation, expiry, status tracking, and magic link
    generation from AbstractInvitation.

    Attributes:
        organisation: FK to Organisation
        invited_by: FK to User who sent invitation
        email: Email address of invitee
        name: Optional display name of invitee
        role: Role to assign upon acceptance
        accepted_at: Timestamp when invitation was accepted
    """

    organisation = models.ForeignKey(
        "Organisation", on_delete=models.CASCADE, related_name="invitations"
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="invitations_sent",
    )

    # Invitee details
    email = models.EmailField(help_text="Email address of invitee")
    name = models.CharField(
        max_length=255, blank=True, help_text="Optional display name"
    )
    role = models.CharField(
        max_length=30,
        choices=OrganisationMembership.ROLE_CHOICES,
        default=OrganisationMembership.ROLE_REVIEWER,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "organisation_invitations"
        verbose_name = "Organisation Invitation"
        verbose_name_plural = "Organisation Invitations"
        indexes = [
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self):
        """Return string representation of the invitation."""
        return f"Invitation: {self.email} to {self.organisation.name}"

    def get_magic_link_url_name(self) -> str:
        """Return URL pattern name for organisation invitation acceptance."""
        return "organisation:invitation_accept"
