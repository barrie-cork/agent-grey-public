"""
Core workflow management views for systematic literature review sessions.

This module implements the primary interface for managing systematic literature
review sessions through a 9-state workflow: draft → defining_search →
ready_to_execute → executing → processing_results → ready_for_review →
under_review → completed → archived.

Provides comprehensive session management including creation, editing, deletion,
duplication, archival, and intelligent workflow navigation. All views enforce
user ownership and appropriate status transitions to maintain data integrity
throughout the research process.

The views support PRISMA-compliant systematic reviews with audit trails,
progress tracking, and contextual navigation to guide researchers through
the grey literature review methodology.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import BooleanField, Case, Q, Value, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from apps.core.services.cache_service import WorkflowCacheService

from .forms import SessionCreateAndConfigForm, SessionEditForm
from .mixins import SessionNavigationMixin, UserOwnerMixin
from .models import (
    ReviewConfiguration,
    ReviewInvitation,
    SearchSession,
    SessionActivity,
)

logger = logging.getLogger(__name__)


class DashboardView(LoginRequiredMixin, SessionNavigationMixin, ListView):
    """Primary dashboard displaying user's systematic literature review sessions.

    Provides an overview of all search sessions with filtering, pagination,
    and cached statistics. Supports the 9-state workflow by showing session
    progress and enabling navigation to appropriate next steps.

    Implements the main entry point for grey literature review management,
    allowing researchers to monitor active reviews, access completed work,
    and create new systematic literature searches following PRISMA guidelines.

    Performance optimized with:
    - Custom model manager for single-query data loading
    - Pagination increased to 20 items for better UX
    - Aggregate queries for statistics
    - Smart caching for status distribution
    """

    model = SearchSession
    template_name = "review_manager/dashboard.html"
    context_object_name = "sessions"
    paginate_by = 20  # Increased from 12 for better performance

    def get_queryset(self):
        """Retrieve filtered and optimized queryset of user's search sessions.

        Includes both owned sessions and sessions where user has accepted invitation.
        Uses Q() queries to combine:
        - Sessions owned by current user
        - Sessions where user is invitee with ACCEPTED status

        Adds is_owner annotation to distinguish owned vs shared sessions.

        Uses the optimized for_dashboard() manager method which includes:
        - select_related for owner and strategy
        - prefetch_related for recent activities (limited to 5)
        - Annotations for statistics (query_count, execution_count, etc.)

        Returns:
            QuerySet: Highly optimized QuerySet with all needed data in a single query.
        """
        # Get sessions owned by user OR where user has accepted invitation
        queryset = (
            SearchSession.objects.filter(
                Q(owner=self.request.user)
                | Q(
                    reviewer_invitations__invitee=self.request.user,
                    reviewer_invitations__status=ReviewInvitation.STATUS_ACCEPTED,
                )
            )
            .for_dashboard()
            .annotate(
                is_owner=Case(
                    When(owner=self.request.user, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField(),
                )
            )
            .distinct()
        )  # Prevent duplicates from JOIN

        # Apply filters
        status_filter = self.request.GET.get("status")
        search_query = self.request.GET.get("q")

        if status_filter and status_filter != "all":
            if status_filter == "active":
                queryset = queryset.active_only()
            else:
                queryset = queryset.filter(status=status_filter)

        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(description__icontains=search_query)
            )

        # Already optimally ordered by the manager
        return queryset

    def get_context_data(self, **kwargs):
        """Add dashboard statistics and filtering context to template.

        Separates sessions into owned_sessions and shared_sessions based on
        is_owner annotation. Includes pending invitations preview (limited to 5).

        Uses optimized aggregate queries to fetch all statistics in a single
        database hit. Implements smart caching with graceful fallback.

        Returns:
            dict: Template context with sessions, statistics, and filter state
        """
        context = super().get_context_data(**kwargs)

        # Separate owned vs shared sessions
        all_sessions = context["sessions"]
        owned_sessions = [s for s in all_sessions if s.is_owner]
        shared_sessions = [s for s in all_sessions if not s.is_owner]

        # Get pending invitations (limited to 5 for preview)
        from apps.review_manager.services.invitation_service import (
            ReviewInvitationService,
        )

        invitation_service = ReviewInvitationService()
        pending_invitations = invitation_service.get_pending_invitations(
            self.request.user
        )[:5]

        # Use optimized cache service for statistics
        stats = WorkflowCacheService.get_dashboard_stats(str(self.request.user.id))

        # Get status distribution with caching
        status_distribution = self._get_status_distribution()

        context.update(stats)
        context.update(
            {
                "owned_sessions": owned_sessions,
                "shared_sessions": shared_sessions,
                "pending_invitations": pending_invitations,
                "current_filter": self.request.GET.get("status", "all"),
                "search_query": self.request.GET.get("q", ""),
                "status_distribution": status_distribution,
            }
        )

        return context

    def _get_status_distribution(self):
        """Get status distribution with caching.

        Returns a dictionary of status counts for chart display.
        Cached separately as it changes less frequently than other stats.
        """
        cache_key = f"status_dist:user:{self.request.user.id}"

        try:
            distribution = cache.get(cache_key)
            if distribution is None:
                distribution = dict(
                    SearchSession.objects.filter(owner=self.request.user)
                    .by_status_distribution()
                    .values_list("status", "count")
                )
                # Cache for 5 minutes
                cache.set(cache_key, distribution, 300)
            return distribution
        except (ConnectionError, TimeoutError, OSError):
            # Cache unavailability fallback -- query DB directly
            return dict(
                SearchSession.objects.filter(owner=self.request.user)
                .by_status_distribution()
                .values_list("status", "count")
            )


class SessionCreateView(LoginRequiredMixin, CreateView):
    """Create new systematic literature review session with inline configuration.

    Initializes a new search session in the 9-state workflow at 'draft' status.
    Combines session creation (title, description) with review configuration
    (reviewer invitations, screening methodology) in a single step.

    The created session starts in 'draft' status and can proceed through:
    draft → defining_search → ready_to_execute → executing → processing_results
    → ready_for_review → under_review → completed → archived
    """

    model = SearchSession
    form_class = SessionCreateAndConfigForm
    template_name = "review_manager/session_create.html"

    def get_form_kwargs(self):
        """Pass the requesting user so the form can scope the org selector."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        """Expose whether the organisation selector should be rendered.

        The selector is only present on the form (and shown) when the user has
        more than one active membership; single-org users are auto-assigned.
        """
        context = super().get_context_data(**kwargs)
        context["show_organisation_selector"] = "organisation" in context["form"].fields
        return context

    @transaction.atomic
    def form_valid(self, form):
        """Process valid combined form for session and configuration.

        Creates session with title/description, then creates ReviewConfiguration
        with reviewer settings, invalidates dashboard cache, logs activity.

        Organisation assignment (Issue #171): deterministic. Multi-org users
        pick an organisation via the form selector; single-org users are
        auto-assigned silently. The form validates the chosen organisation is
        one the user is an active member of, so no ``.first()`` guesswork.

        Args:
            form: Validated SessionCreateAndConfigForm with title, description,
                  and review configuration fields.

        Returns:
            HttpResponse: Redirect to session detail view after creating both
                         session and configuration.
        """
        form.instance.owner = self.request.user

        # Deterministic organisation assignment. The selector is only present
        # for multi-org users; single-org users fall back to single_organisation.
        organisation = form.cleaned_data.get("organisation") or form.single_organisation

        if organisation:
            form.instance.organisation = organisation
            logger.info(f"Assigned session to organisation: {organisation.name}")
        else:
            logger.warning(
                f"User {self.request.user.username} has no organisation membership"
            )

        # Save session first
        response = super().form_valid(form)
        session = self.object

        # Create ReviewConfiguration from form data
        invited_reviewers = form.cleaned_data.get("invited_reviewers_data", [])
        min_reviewers = form.cleaned_data.get("min_reviewers_per_result", 1)
        conflict_method = form.cleaned_data.get(
            "conflict_resolution_method", "CONSENSUS"
        )
        consensus_criteria = form.cleaned_data.get("consensus_criteria", "MAJORITY")
        arbitrator_email = form.cleaned_data.get("designated_arbitrator_email", "")
        arbitrator_name = form.cleaned_data.get("designated_arbitrator_name", "")

        # Only create configuration if at least one configuration field is set
        config_fields = [min_reviewers, conflict_method, consensus_criteria]
        has_config = any(
            f for f in config_fields if f and f != "CONSENSUS" and f != "MAJORITY"
        )

        if has_config or invited_reviewers:
            # Create ReviewConfiguration v1
            config = ReviewConfiguration(
                session=session,
                version=1,
                created_by=self.request.user,
                organisation=session.organisation,
                effective_from=timezone.now(),
                blind_screening_enforced=True,
                min_reviewers_per_result=min_reviewers or 1,
                conflict_resolution_method=conflict_method or "CONSENSUS",
                consensus_criteria=consensus_criteria or "MAJORITY",
                designated_arbitrator_email=arbitrator_email,
                designated_arbitrator_name=arbitrator_name,
                invited_reviewers=invited_reviewers
                if isinstance(invited_reviewers, list)
                else [],
            )
            config.save()

            # Update session's current_configuration
            session.current_configuration = config
            session.save(update_fields=["current_configuration"])

            total_reviewers = 1 + len(invited_reviewers)

            # Log configuration creation
            logger.info(
                f"Configuration v{config.version} created for session {session.id} "
                f"by user {self.request.user.id}: "
                f"min_reviewers={config.min_reviewers_per_result}, "
                f"total_reviewers={total_reviewers}, "
                f"invited_count={len(invited_reviewers)}, "
                f"consensus_criteria={config.consensus_criteria}, "
                f"conflict_resolution={config.conflict_resolution_method}"
            )

            # Log activity for audit trail
            SessionActivity.objects.create(
                session=session,
                activity_type="configuration_saved",
                user=self.request.user,
                metadata={
                    "min_reviewers": config.min_reviewers_per_result,
                    "total_reviewers": total_reviewers,
                    "invited_reviewers_count": len(invited_reviewers),
                    "consensus_criteria": config.consensus_criteria,
                    "conflict_resolution_method": config.conflict_resolution_method,
                    "configuration_version": config.version,
                },
            )

        # Invalidate dashboard cache for this user
        WorkflowCacheService.invalidate_user_dashboard(str(self.request.user.id))

        # Log activity
        SessionActivity.log_activity(
            session=session,
            activity_type="created",
            description=f'Session "{session.title}" created',
            user=self.request.user,
        )

        # Build success message
        if has_config or invited_reviewers:
            reviewer_summary = (
                f"{config.min_reviewers_per_result} reviewer(s) per result"
            )
            invitation_note = ""
            if len(invited_reviewers) > 0:
                reviewer_summary += (
                    f" ({len(invited_reviewers)} reviewer(s) will be invited)"
                )
                invitation_note = " Reviewer invitations will be sent automatically when search results are available."
            messages.success(
                self.request,
                f'Review session "{session.title}" created successfully. '
                f"Your review requires {reviewer_summary} with "
                f"{config.get_consensus_criteria_display()} consensus.{invitation_note}",
            )
        else:
            messages.success(
                self.request,
                f'Review session "{session.title}" created successfully!',
            )

        return response

    def get_success_url(self):
        """Determine redirect URL after successful session creation.

        Returns:
            str: URL to session detail view for next workflow step.
        """
        return reverse(
            "review_manager:session_detail", kwargs={"session_id": self.object.id}
        )


class SessionDetailView(LoginRequiredMixin, SessionNavigationMixin, DetailView):
    """Central hub for managing systematic literature review session.

    Provides comprehensive session information including current status in the
    9-state workflow, progress metrics, recent activities, and contextual
    navigation options. Serves as the primary coordination point for researchers
    managing their grey literature review process.

    Displays status-specific information and available actions based on current
    workflow position, guiding users through the systematic review process
    from initial search strategy to final report generation.

    Access Control:
    - Owners have full access with editing capabilities
    - Invited reviewers (with accepted invitations) have read-only access
    - Other users are denied access with PermissionDenied
    """

    model = SearchSession
    template_name = "review_manager/session_detail.html"
    context_object_name = "session"
    pk_url_kwarg = "session_id"

    def dispatch(self, request, *args, **kwargs):
        """Check access permissions before processing request.

        Implements role-based access control for session detail view:
        1. Session owners get full access (can_edit=True)
        2. Users with accepted invitations get read-only access (can_edit=False)
        3. All other users are denied access

        Sets instance variables:
        - self.user_role: 'owner' or 'reviewer'
        - self.can_edit: Boolean indicating edit permissions

        Raises:
            PermissionDenied: If user has no access to this session

        Returns:
            HttpResponse: Result from parent dispatch method
        """
        # LoginRequiredMixin check: redirect unauthenticated users before
        # accessing user attributes (AnonymousUser lacks .email)
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        session = self.get_object()
        user = request.user

        # Check 1: Is user the session owner?
        if session.owner == user:
            self.user_role = "owner"
            self.can_edit = True
            return super().dispatch(request, *args, **kwargs)

        # Check 2: Has user accepted an invitation to this session?
        has_accepted_invitation = ReviewInvitation.objects.filter(
            session=session,
            invitee_email=user.email,
            status=ReviewInvitation.STATUS_ACCEPTED,
        ).exists()

        if has_accepted_invitation:
            self.user_role = "reviewer"
            self.can_edit = False
            return super().dispatch(request, *args, **kwargs)

        # Check 3: No access - deny with helpful message
        raise PermissionDenied(
            "You do not have access to this session. "
            "If you were invited, please accept the invitation first."
        )

    def get_context_data(self, **kwargs):
        """Add session-specific context for detailed view.

        Provides comprehensive context including workflow navigation,
        recent activities, permission flags, and progress metrics.
        Supports intelligent navigation based on current workflow state.

        Args:
            **kwargs: Additional context variables from parent class.

        Returns:
            dict:
            Template context dictionary containing:
                - session: The SearchSession object
                - user_role: 'owner' or 'reviewer'
                - can_edit: Boolean indicating if user can edit session
                - nav_info: Next workflow step information
                - recent_activities: Latest session activities
                - status_explanation: Human-readable status description
                - progress_percentage: Workflow completion percentage
                - inclusion_rate: Review inclusion rate (if applicable)
                - reviewer_completions: QuerySet of ReviewerCompletion for invited reviewers
                - my_completion: Current user's ReviewerCompletion (if they are invited reviewer)
        """
        context = super().get_context_data(**kwargs)
        session = self.object

        # Get navigation info
        nav_info = self.get_session_next_url(session)

        # Get recent activities
        recent_activities = session.activities.select_related("user").order_by(
            "-created_at"
        )[:10]

        # Get reviewer completion tracking (Phase 2: Completion Tracking Integration)
        from apps.review_results.models import ReviewerCompletion

        reviewer_completions = ReviewerCompletion.objects.filter(
            session=session
        ).select_related("reviewer", "invitation")

        # Check if current user has a completion record (invited reviewer)
        my_completion = None
        try:
            my_completion = ReviewerCompletion.objects.get(
                session=session, reviewer=self.request.user
            )
        except ReviewerCompletion.DoesNotExist:
            pass

        # Status-specific context
        context.update(
            {
                "user_role": self.user_role,
                "can_edit": self.can_edit,
                "nav_info": nav_info,
                "recent_activities": recent_activities,
                "status_explanation": self.get_status_explanation(session.status),
                "progress_percentage": session.progress_percentage,
                "inclusion_rate": session.inclusion_rate,
                "reviewer_completions": reviewer_completions,
                "my_completion": my_completion,
            }
        )

        return context

    def get_status_explanation(self, status):
        """Get human-readable explanation for 9-state workflow status.

        Args:
            status: Current session status from the workflow state machine.

        Returns:
            str: User-friendly explanation of current status and expected next actions.
        """
        explanations = {
            "draft": "Session is in draft mode. You can edit all details and define your search strategy.",
            "defining_search": "Define your search queries and parameters using the PIC framework.",
            "ready_to_execute": "Validation complete. System is preparing to execute search automatically.",
            "executing": "Search queries are currently being executed.",
            "processing_results": "Search results are being processed and normalized.",
            "ready_for_review": "Results are ready for manual review and inclusion/exclusion decisions.",
            "under_review": "Manual review is in progress.",
            "completed": "Review is complete. Generate reports and export data.",
            "archived": "Session has been archived and is read-only.",
        }
        return explanations.get(status, "Unknown status")


class SessionUpdateView(LoginRequiredMixin, UserOwnerMixin, UpdateView):
    """Edit basic session metadata for systematic literature review.

    Allows modification of session title and description while preserving
    workflow state and associated data. Only available for sessions in
    'draft' or 'defining_search' status to prevent disruption of active reviews.

    Changes are logged to maintain audit trail of session modifications
    throughout the research process.
    """

    model = SearchSession
    form_class = SessionEditForm
    template_name = "review_manager/session_edit.html"
    pk_url_kwarg = "session_id"

    def form_valid(self, form):
        """Process valid session update form.

        Saves changes to session metadata, logs the modification activity,
        and provides user feedback about successful update.

        Args:
            form: Validated SessionEditForm with updated title and description.

        Returns:
            HttpResponse: HTTP response redirecting to session detail view.
        """
        response = super().form_valid(form)

        SessionActivity.log_activity(
            session=self.object,
            activity_type="settings_changed",
            description="Session details updated",
            user=self.request.user,
        )

        messages.success(
            self.request,
            f'Session "{self.object.title}" has been updated successfully.',
        )
        return response

    def get_success_url(self):
        """Determine redirect URL after successful session update.

        Returns:
            str: URL to session detail view to show updated information.
        """
        return reverse(
            "review_manager:session_detail", kwargs={"session_id": self.object.id}
        )


class SessionNavigateView(LoginRequiredMixin, SessionNavigationMixin, View):
    """Intelligent workflow navigation for systematic literature review.

    Provides context-aware navigation based on session status in the 9-state
    workflow. Redirects users to the most appropriate next step based on
    current session state, supporting guided progression through the
    systematic review process.

    Eliminates user confusion about next steps by automatically determining
    the correct workflow destination for each session state.

    Access Control:
    - Session owners have full access
    - Invited reviewers with ACCEPTED invitations have access
    - Users without access are redirected to dashboard with error message
    """

    def get_object(self):
        """Retrieve the session object for permission checking.

        Returns:
            SearchSession: SearchSession object identified by session_id URL parameter.
        """
        session_id = self.kwargs.get("session_id")
        return get_object_or_404(SearchSession, pk=session_id)

    def dispatch(self, request, *args, **kwargs):
        """Check if user has access to this session (owner or invited reviewer).

        Implements the same access control as SessionDetailView to ensure
        invited reviewers can navigate to their assigned sessions.

        Args:
            request: HTTP request object
            *args: Positional arguments
            **kwargs: Keyword arguments including session_id

        Returns:
            HttpResponse: Super dispatch if authorized, redirect to dashboard if not
        """
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        session = self.get_object()
        user = request.user

        # Check 1: Is user the session owner?
        if session.owner == user:
            return super().dispatch(request, *args, **kwargs)

        # Check 2: Has user accepted an invitation to this session?
        has_accepted_invitation = ReviewInvitation.objects.filter(
            session=session,
            invitee_email=user.email,
            status=ReviewInvitation.STATUS_ACCEPTED,
        ).exists()

        if has_accepted_invitation:
            return super().dispatch(request, *args, **kwargs)

        # No access - show error and redirect to dashboard
        messages.error(
            request,
            "You do not have access to this session. "
            "If you were invited, please accept the invitation first.",
        )
        return redirect("review_manager:dashboard")

    def get(self, request, session_id):
        """Navigate to contextually appropriate workflow step.

        Determines the next logical step in the systematic review workflow
        based on current session status and redirects accordingly.

        Args:
            request: HTTP request object.
            session_id: UUID of the session for navigation.

        Returns:
            HttpResponse: HTTP redirect response to the appropriate workflow step.
        """
        session = self.get_object()

        # Get navigation info and redirect
        nav_info = self.get_session_next_url(session)
        return redirect(nav_info["url"])


class SessionDeleteView(LoginRequiredMixin, UserOwnerMixin, View):
    """Delete a search session and all related data.

    Provides secure deletion of systematic literature review sessions with
    CASCADE deletion of all related data including results, decisions, and reports.
    Only the session owner can delete their sessions.

    Supports deletion from any session state to give users full control
    over their data management.
    """

    def get_object(self):
        """Retrieve the session object for permission checking.

        Returns:
            SearchSession: SearchSession object identified by session_id URL parameter.
        """
        session_id = self.kwargs.get("session_id")
        return get_object_or_404(SearchSession, pk=session_id)

    def post(self, request, session_id):
        """Delete the session and all related data.

        Performs CASCADE deletion of the session and all related objects
        including search queries, results, review decisions, and reports.

        Args:
            request: HTTP request object with POST data.
            session_id: UUID of the session to delete.

        Returns:
            HttpResponse: Redirect to dashboard with success message.
        """
        session = self.get_object()
        session_title = session.title
        session_status = session.status

        with transaction.atomic():
            # Log deletion activity BEFORE cascade delete so the audit record
            # persists (SessionActivity has CASCADE FK to SearchSession, so it
            # would be deleted along with the session if logged after deletion).
            SessionActivity.log_activity(
                session=session,
                activity_type="deleted",
                description=f"Session deleted (previous status: {session_status})",
                user=request.user,
            )

            # Clear PROTECT constraints before deletion so Django can cascade.
            # SearchSession.current_configuration and ConfigurationChange FKs to
            # ReviewConfiguration use on_delete=PROTECT, which blocks the cascade
            # delete of ReviewConfiguration (and transitively the session itself).
            from .models import ConfigurationChange

            config_ids = list(session.configurations.values_list("id", flat=True))
            if config_ids:
                ConfigurationChange.objects.filter(
                    from_configuration_id__in=config_ids
                ).delete()
                ConfigurationChange.objects.filter(
                    to_configuration_id__in=config_ids
                ).delete()

            if session.current_configuration_id:
                session.current_configuration = None
                session.save(update_fields=["current_configuration"])

            # Delete the session (CASCADE deletes all related data)
            session.delete()

        messages.success(
            request,
            f"Session '{session_title}' and all related data have been permanently deleted.",
        )
        return redirect("review_manager:dashboard")


class SessionArchiveView(LoginRequiredMixin, UserOwnerMixin, View):
    """Archive a completed systematic literature review session.

    Transitions a session from 'completed' to 'archived' status, marking it
    as read-only and removing it from the active sessions list. Archived
    sessions can be viewed for historical reference or unarchived back to
    'draft' status if needed.

    This is the final step in the 9-state workflow:
    draft → defining_search → ready_to_execute → executing → processing_results
    → ready_for_review → under_review → completed → archived

    Only sessions in 'completed' status can be archived normally, though the
    system allows archiving from any state for administrative purposes.
    """

    def get_object(self):
        """Retrieve the session object for permission checking.

        Returns:
            SearchSession: SearchSession object identified by session_id URL parameter.
        """
        session_id = self.kwargs.get("session_id")
        return get_object_or_404(SearchSession, pk=session_id)

    def post(self, request, session_id):
        """Archive the session and mark as read-only.

        Validates that the session can be archived, updates status to 'archived',
        logs the activity, and provides user feedback. The archived session
        remains accessible but becomes read-only.

        Args:
            request: HTTP request object with POST data.
            session_id: UUID of the session to archive.

        Returns:
            HttpResponse: Redirect to dashboard with success message.
        """
        session = self.get_object()
        old_status = session.status

        # Validate transition to archived
        if not session.can_transition_to("archived"):
            messages.error(
                request,
                f"Cannot archive session from '{session.get_status_display()}' status. "
                f"Expected statuses: completed, or any other status for administrative archival.",
            )
            return redirect("review_manager:session_detail", session_id=session.id)

        # Update status to archived
        session.status = "archived"
        session.save()

        # Invalidate dashboard cache
        WorkflowCacheService.invalidate_user_dashboard(str(request.user.id))

        # Log the archival activity
        SessionActivity.log_activity(
            session=session,
            activity_type="status_changed",
            description=f"Session archived (from {old_status})",
            user=request.user,
            metadata={"old_status": old_status, "new_status": "archived"},
        )

        messages.success(
            request,
            f"Session '{session.title}' has been archived successfully. "
            f"It can be viewed in the archived sessions section.",
        )
        return redirect("review_manager:dashboard")
