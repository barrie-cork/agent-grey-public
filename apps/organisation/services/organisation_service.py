"""
Organisation service for business logic and org-wide operations.

Provides:
- Organisation creation and management
- Quota checking and validation
- Organisation-wide metrics and statistics
- Default organisation management
"""

from typing import Dict, Optional

from django.db.models import Count
from django.utils import timezone

from apps.core.services.base import BaseService
from apps.organisation.models import Organisation


class OrganisationService(BaseService):
    """
    Service for organisation management and metrics.

    Following the BaseService pattern from apps/core/services/base.py.
    """

    SERVICE_NAME = "OrganisationService"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialize organisation service resources."""
        # No special initialization needed
        pass

    def health_check(self) -> bool:
        """
        Check if organisation service is healthy.

        Returns:
            bool: True if service is operational
        """
        try:
            # Simple database connectivity check
            Organisation.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def get_default_config(self) -> Dict:
        """Get default configuration for organisation service."""
        return {
            "cache_timeout": 300,  # 5 minutes
            "enable_quota_enforcement": True,
        }

    def get_or_create_default_org(self) -> Organisation:
        """
        Get or create the default organisation.

        This is used during migration and for initial setup.

        Returns:
            Organisation: Default organisation instance
        """
        with self._measure_performance("get_or_create_default_org"):
            try:
                org, created = Organisation.objects.get_or_create(
                    slug="default",
                    defaults={
                        "name": "Default Organisation",
                        "default_min_reviewers": 1,
                        "require_dual_review": False,
                    },
                )

                if created:
                    self.logger.info(f"Created default organisation: {org.name}")

                return org

            except Exception as e:
                self._handle_error(e, operation="get_or_create_default_org")
                raise

    def get_org_metrics(self, org: Organisation) -> Dict:
        """
        Calculate comprehensive organisation metrics.

        Args:
            org: Organisation instance

        Returns:
            Dict with org-wide metrics including:
            - Total reviews (by status)
            - Total members (by role)
            - Active review count
            - Quota status
            - Average completion time
        """
        with self._measure_performance("get_org_metrics"):
            try:
                # Check cache first
                cache_key = f"org_metrics_{org.id}"
                cached = self.get_cached_value(cache_key)
                if cached:
                    return cached

                # Calculate metrics
                reviews = org.reviews.all()

                # Review counts by status
                status_counts = reviews.values("status").annotate(count=Count("id"))
                status_dict = {item["status"]: item["count"] for item in status_counts}

                # Member counts by role
                members = org.memberships.filter(is_active=True)
                role_counts = members.values("role").annotate(count=Count("id"))
                role_dict = {item["role"]: item["count"] for item in role_counts}

                # Active reviews
                active_reviews = org.get_active_reviews_count()

                # Quota status
                at_review_quota = org.is_at_review_quota()
                at_user_quota = org.is_at_user_quota()

                # Average completion time
                completed = reviews.filter(
                    status="completed",
                    started_at__isnull=False,
                    completed_at__isnull=False,
                )
                avg_completion_hours = None
                if completed.exists():
                    total_seconds = sum(
                        [
                            (r.completed_at - r.started_at).total_seconds()
                            for r in completed
                        ]
                    )
                    avg_completion_hours = round(
                        total_seconds / completed.count() / 3600, 2
                    )

                metrics = {
                    "organisation_id": str(org.id),
                    "organisation_name": org.name,
                    "total_reviews": reviews.count(),
                    "active_reviews": active_reviews,
                    "status_breakdown": status_dict,
                    "total_members": members.count(),
                    "role_breakdown": role_dict,
                    "quota_status": {
                        "at_review_quota": at_review_quota,
                        "at_user_quota": at_user_quota,
                        "max_active_reviews": org.max_active_reviews,
                        "max_users": org.max_users,
                    },
                    "average_completion_hours": avg_completion_hours,
                    "calculated_at": timezone.now().isoformat(),
                }

                # Cache for 5 minutes
                self.set_cached_value(cache_key, metrics)

                return metrics

            except Exception as e:
                self._handle_error(
                    e, operation="get_org_metrics", context={"org_id": str(org.id)}
                )
                raise

    def check_review_quota(self, org: Organisation) -> tuple[bool, Optional[str]]:
        """
        Check if organisation can create new reviews.

        Args:
            org: Organisation instance

        Returns:
            Tuple of (can_create: bool, error_message: Optional[str])
        """
        if not self.config.get("enable_quota_enforcement", True):
            return True, None

        if org.is_at_review_quota():
            return (
                False,
                f"Review quota reached ({org.max_active_reviews} active reviews)",
            )

        return True, None

    def check_user_quota(self, org: Organisation) -> tuple[bool, Optional[str]]:
        """
        Check if organisation can add new users.

        Args:
            org: Organisation instance

        Returns:
            Tuple of (can_add: bool, error_message: Optional[str])
        """
        if not self.config.get("enable_quota_enforcement", True):
            return True, None

        if org.is_at_user_quota():
            return False, f"User quota reached ({org.max_users} members)"

        return True, None

    def get_quality_metrics(self, org: Organisation) -> Dict:
        """
        Calculate quality metrics for organisation reviews.

        Includes:
        - Average Inter-Rater Reliability (IRR)
        - Reviews below IRR threshold
        - Pending conflicts
        - Total results reviewed

        Args:
            org: Organisation instance

        Returns:
            Dict with quality metrics
        """
        with self._measure_performance("get_quality_metrics"):
            try:
                # This will be implemented when dual screening models are added in Phase 2
                # For now, return placeholder structure
                return {
                    "organisation_id": str(org.id),
                    "average_irr": None,
                    "reviews_below_threshold": 0,
                    "pending_conflicts": 0,
                    "total_results_reviewed": 0,
                    "note": "Quality metrics will be populated in Phase 2 (Dual Screening)",
                }

            except Exception as e:
                self._handle_error(
                    e, operation="get_quality_metrics", context={"org_id": str(org.id)}
                )
                raise
