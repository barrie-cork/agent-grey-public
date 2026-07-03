"""
Custom model managers for optimized database queries in the review_manager app.
"""

import logging

from django.core.exceptions import FieldError
from django.db import models
from django.db.models import (
    Case,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Prefetch,
    Q,
    When,
)
from django.utils import timezone

logger = logging.getLogger(__name__)


class SearchSessionQuerySet(models.QuerySet):
    """Optimized queryset for SearchSession with performance-focused methods."""

    def with_statistics(self):
        """
        Annotate sessions with computed statistics.
        Reduces multiple queries to a single query with annotations.

        Includes error handling for production database issues with is_active field.
        """
        try:
            # Try the optimized query with is_active filtering
            return self.annotate(
                # Count active queries through the search_strategy relationship
                query_count=Count(
                    "search_strategy__search_queries",
                    filter=Q(search_strategy__search_queries__is_active=True),
                    distinct=True,
                ),
                # Count distinct executions across all queries
                execution_count=Count(
                    "search_strategy__search_queries__executions", distinct=True
                ),
                # Calculate pending reviews
                pending_reviews=F("total_results") - F("reviewed_results"),
                # Calculate completion percentage with safe division
                completion_percentage=Case(
                    When(total_results=0, then=0.0),
                    default=ExpressionWrapper(
                        F("reviewed_results") * 100.0 / F("total_results"),
                        output_field=FloatField(),
                    ),
                    output_field=FloatField(),
                ),
            )
        except FieldError as e:
            # Log the error for debugging
            logger.warning(
                f"FieldError in with_statistics - falling back to simple query: {str(e)}"
            )

            # Fallback query without is_active filtering
            return self.annotate(
                # Count all queries (not just active ones)
                query_count=Count("search_strategy__search_queries", distinct=True),
                # Count distinct executions across all queries
                execution_count=Count(
                    "search_strategy__search_queries__executions", distinct=True
                ),
                # Calculate pending reviews
                pending_reviews=F("total_results") - F("reviewed_results"),
                # Calculate completion percentage with safe division
                completion_percentage=Case(
                    When(total_results=0, then=0.0),
                    default=ExpressionWrapper(
                        F("reviewed_results") * 100.0 / F("total_results"),
                        output_field=FloatField(),
                    ),
                    output_field=FloatField(),
                ),
            )

    def for_dashboard(self):
        """
        Optimized query for dashboard view.
        Includes all necessary related data in a single database hit.
        """
        from apps.review_manager.models import SessionActivity

        return (
            self.select_related("owner", "search_strategy")
            .prefetch_related(
                # Prefetch only the 5 most recent activities
                Prefetch(
                    "activities",
                    queryset=SessionActivity.objects.select_related("user").order_by(
                        "-created_at"
                    )[:5],
                    to_attr="recent_activities",
                ),
                # Prefetch active queries
                "search_strategy__search_queries",
            )
            .with_statistics()
            .order_by("-updated_at")
        )

    def active_only(self):
        """Filter to active sessions (not completed or archived)."""
        return self.exclude(status__in=["completed", "archived"])

    def owned_by(self, user):
        """Filter sessions owned by a specific user."""
        return self.filter(owner=user)

    def stuck_sessions(self, hours=2):
        """
        Find sessions that appear to be stuck.
        Sessions in executing or processing states that haven't updated in X hours.
        """
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours)
        return self.filter(
            status__in=["executing", "processing_results"], updated_at__lt=cutoff_time
        )

    def by_status_distribution(self):
        """Get count of sessions grouped by status."""
        return self.values("status").annotate(count=Count("id")).order_by("status")

    def with_execution_progress(self):
        """
        Annotate sessions with detailed execution progress.
        Useful for monitoring active executions.

        Includes error handling for production database issues with is_active field.
        """
        try:
            # Try the optimized query with is_active filtering
            return self.annotate(
                # Count total queries that should be executed
                total_executable_queries=Count(
                    "search_strategy__search_queries",
                    filter=Q(search_strategy__search_queries__is_active=True),
                    distinct=True,
                ),
                # Count queries with at least one completed execution
                completed_query_executions=Count(
                    "search_strategy__search_queries",
                    filter=Q(
                        search_strategy__search_queries__is_active=True,
                        search_strategy__search_queries__executions__status="completed",
                    ),
                    distinct=True,
                ),
                # Calculate execution progress percentage
                execution_progress=Case(
                    When(total_executable_queries=0, then=0.0),
                    default=ExpressionWrapper(
                        F("completed_query_executions")
                        * 100.0
                        / F("total_executable_queries"),
                        output_field=FloatField(),
                    ),
                    output_field=FloatField(),
                ),
            )
        except FieldError as e:
            # Log the error for debugging
            logger.warning(
                f"FieldError in with_execution_progress - falling back to simple query: {str(e)}"
            )

            # Fallback query without is_active filtering
            return self.annotate(
                # Count all queries (not filtering by is_active)
                total_executable_queries=Count(
                    "search_strategy__search_queries", distinct=True
                ),
                # Count queries with at least one completed execution (without is_active filter)
                completed_query_executions=Count(
                    "search_strategy__search_queries",
                    filter=Q(
                        search_strategy__search_queries__executions__status="completed"
                    ),
                    distinct=True,
                ),
                # Calculate execution progress percentage
                execution_progress=Case(
                    When(total_executable_queries=0, then=0.0),
                    default=ExpressionWrapper(
                        F("completed_query_executions")
                        * 100.0
                        / F("total_executable_queries"),
                        output_field=FloatField(),
                    ),
                    output_field=FloatField(),
                ),
            )


class SearchSessionManager(models.Manager):
    """
    Custom manager with optimized queries for SearchSession model.
    Provides convenient access to optimized querysets.
    """

    def get_queryset(self):
        """Return the custom queryset."""
        return SearchSessionQuerySet(self.model, using=self._db)

    def with_statistics(self):
        """Get sessions with computed statistics."""
        return self.get_queryset().with_statistics()

    def for_dashboard(self):
        """Get optimized queryset for dashboard display."""
        return self.get_queryset().for_dashboard()

    def active_only(self):
        """Get only active sessions."""
        return self.get_queryset().active_only()

    def owned_by(self, user):
        """Get sessions owned by a specific user."""
        return self.get_queryset().owned_by(user)

    def stuck_sessions(self, hours=2):
        """Get potentially stuck sessions."""
        return self.get_queryset().stuck_sessions(hours=hours)

    def get_status_summary(self, user=None):
        """
        Get summary statistics for sessions.
        Optionally filtered by user.
        """
        queryset = self.get_queryset()
        if user:
            queryset = queryset.filter(owner=user)

        return queryset.aggregate(
            total_sessions=Count("id"),
            active_sessions=Count(
                "id", filter=~Q(status__in=["completed", "archived"])
            ),
            draft_sessions=Count("id", filter=Q(status="draft")),
            completed_sessions=Count("id", filter=Q(status="completed")),
            total_results_found=models.Sum("total_results"),
            total_results_reviewed=models.Sum("reviewed_results"),
            total_results_included=models.Sum("included_results"),
        )
