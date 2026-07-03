"""
Views for the SERP execution module.
Handles search execution, monitoring, and error recovery via Serper API.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, FormView, View

from .dependencies import get_session_provider
from .forms import ErrorRecoveryForm
from .models import SearchExecution
from .services.view_services import RecoveryViewService, StatusViewService

logger = logging.getLogger(__name__)


class SessionOwnershipMixin:
    """
    Mixin to ensure user owns the search session.

    Provides session retrieval with ownership validation through
    the session provider service for secure access control.
    """

    def get_session(self):
        """
        Get and validate session ownership through provider.

        Returns:
            SearchSession: The validated session object

        Raises:
            PermissionDenied: If user doesn't own the session
        """
        session_id = self.kwargs.get("session_id")  # type: ignore[attr-defined]
        session_provider = get_session_provider()

        # Get session through provider
        session = session_provider.get_session(session_id)

        # Verify ownership through provider
        if not session_provider.verify_session_ownership(session_id, self.request.user):  # type: ignore[attr-defined]
            raise PermissionDenied("You don't have permission to access this session.")

        return session


class SearchExecutionStatusView(LoginRequiredMixin, SessionOwnershipMixin, DetailView):
    """
    Real-time monitoring of search execution progress via Serper API.

    Provides comprehensive execution status including individual query
    progress, result counts, error handling, and performance metrics.
    Supports auto-refresh functionality for active executions and
    detailed statistics for completed runs.

    Integrates with recovery system for failed executions and provides
    actionable feedback on rate limiting and API quota management.
    """

    # Default template - will be overridden by get_template_names()
    template_name = "serp_execution/execution_status.html"
    context_object_name = "session"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = StatusViewService()

    def get_object(self):
        """
        Get the search session for status monitoring.

        Returns:
            SearchSession: The session object for execution monitoring
        """
        return self.get_session()

    def get_template_names(self):
        """Choose template based on JavaScript availability."""
        if self.request.GET.get("nojs") or "text/html" not in self.request.META.get(
            "HTTP_ACCEPT", ""
        ):
            return ["serp_execution/execution_status_nojs.html"]
        return ["serp_execution/execution_status.html"]

    def get_context_data(self, **kwargs):
        """
        Add execution details and enhanced statistics to context.

        Provides comprehensive execution monitoring data including:
        - Individual execution status and progress
        - Aggregated statistics for dashboard cards
        - Real-time refresh intervals for active executions
        - Error details and recovery options

        Args:
            **kwargs: Additional keyword arguments

        Returns:
            dict: Context with execution data and statistics
        """
        context = super().get_context_data(**kwargs)

        # Use service to get all execution data
        execution_data = self.service.get_execution_data(self.object)
        context.update(execution_data)

        # Add feature flag - check Constance first, then settings
        from constance import config
        from django.conf import settings

        # Check Constance config first, fall back to settings
        try:
            context["use_new_monitor"] = config.USE_NEW_SESSION_MONITOR
        except AttributeError:
            context["use_new_monitor"] = getattr(
                settings, "USE_NEW_SESSION_MONITOR", False
            )

        # Add version for cache busting
        context["VERSION"] = getattr(settings, "STATIC_VERSION", "1.0.0")

        # For no-JS version, add simple progress data
        if "nojs" in self.request.GET:
            context["progress"] = {
                "status": self.object.status,
                "status_detail": self.object.status_detail,
                "percentage": 50 if self.object.status == "executing" else 100,
                "message": self.object.status_detail
                or self.object.STATUS_MESSAGES.get(self.object.status, ""),
            }

        # Add any failed executions for retry functionality
        # Fixed: Use correct relationship path after refactoring
        from apps.serp_execution.models import SearchExecution

        context["failed_executions"] = SearchExecution.objects.filter(
            query__session=self.object, status="failed"
        ).exists()

        return context


class ErrorRecoveryView(LoginRequiredMixin, SessionOwnershipMixin, FormView):
    """
    Handle execution errors with intelligent recovery options.

    Provides error analysis and recovery strategies for failed Serper API
    executions including automatic retry scheduling, manual intervention
    options, and error categorization. Integrates with the recovery manager
    for intelligent delay calculations and retry strategies.

    Supports rate limiting recovery, API quota management, and network
    error handling with exponential backoff strategies.
    """

    template_name = "serp_execution/error_recovery.html"
    form_class = ErrorRecoveryForm

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.service = RecoveryViewService()

    def dispatch(self, request, *args, **kwargs):
        """
        Get execution and validate ownership before processing.

        Validates user ownership of the execution and ensures it's
        eligible for retry operations before allowing access to
        recovery interface.

        Args:
            request: The HTTP request object
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments

        Returns:
            HttpResponse: Either the view response or redirect to status page
        """
        execution_id = kwargs.get("execution_id")
        self.execution = get_object_or_404(SearchExecution, id=execution_id)
        self.session = self.execution.query.strategy.session

        # Validate ownership
        if self.session.owner != request.user:
            raise PermissionDenied(
                "You don't have permission to access this execution."
            )

        # Check if execution can be retried
        if not self.execution.can_retry():
            messages.error(request, "This execution cannot be retried.")
            return redirect(
                "serp_execution:execution_status", session_id=self.session.id
            )

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """
        Add execution details and recovery options to context.

        Provides error analysis, retry eligibility assessment, and
        recovery recommendations based on error categorization.

        Args:
            **kwargs: Additional keyword arguments

        Returns:
            dict: Context with execution and recovery data
        """
        context = super().get_context_data(**kwargs)

        # Use service to analyze error and get recovery options
        recovery_data = self.service.analyze_execution_error(self.execution)

        context.update(
            {"execution": self.execution, "session": self.session, **recovery_data}
        )

        return context

    def form_valid(self, form):
        """
        Process the selected recovery action.

        Handles retry scheduling, execution skipping, or manual
        intervention based on user selection and error category.
        Integrates with Celery for async retry execution.

        Args:
            form: The validated recovery form

        Returns:
            HttpResponse: Redirect to execution status page
        """
        try:
            # Use service to process recovery action
            result = self.service.process_recovery_action(
                self.execution, form.cleaned_data
            )

            # Show appropriate message based on action
            if result["success"]:
                if result["action"] == "retry":
                    messages.success(
                        self.request,
                        f"Retry scheduled for execution. Task ID: {result.get('task_id', 'N/A')}",
                    )
                else:
                    messages.info(self.request, result["message"])
            else:
                messages.error(self.request, "Recovery action failed.")

            return redirect(
                "serp_execution:execution_status", session_id=self.session.id
            )

        except Exception as e:
            logger.error(f"Recovery action failed: {str(e)}")
            messages.error(self.request, "Recovery action failed. Please try again.")
            return self.form_invalid(form)

    def get_initial(self):
        """
        Set initial form data based on error analysis.

        Returns:
            dict: Initial form data
        """
        initial = super().get_initial()
        # Use service to prepare initial form data
        form_data = self.service.prepare_recovery_form_data(self.execution)
        initial.update(form_data)
        return initial

    def get_form_kwargs(self):
        """
        Pass execution to form for validation and customization.

        Returns: dict: Form kwargs including execution object
        """
        kwargs = super().get_form_kwargs()
        kwargs["execution"] = self.execution
        return kwargs


class TestSessionMonitorView(LoginRequiredMixin, DetailView):
    """
    Test view for Session Monitor development and debugging.

    Provides a test interface for the new SSE-based SessionMonitor
    JavaScript implementation with manual testing controls.
    """

    template_name = "serp_execution/test_session_monitor.html"

    def get(self, request, *args, **kwargs):
        """
        Render test page with optional session context.

        Args:
            request: The HTTP request object
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments

        Returns:
            HttpResponse: Rendered test page
        """
        from django.shortcuts import render

        # Get session_id from URL if provided
        session_id = kwargs.get("session_id")

        context = {"session_id": session_id or f"test-session-{request.user.id}"}

        return render(request, self.template_name, context)

    def get_object(self):
        """Not needed for test view."""
        return None


class ReconcileStateView(LoginRequiredMixin, SessionOwnershipMixin, View):
    """
    Manually trigger state reconciliation for stuck sessions.

    When a session gets stuck in 'executing' state even though all executions
    are complete, this view provides a manual way to force state reconciliation
    and transition the session to the appropriate next state.
    """

    def post(self, request, session_id):
        """
        Trigger state reconciliation for the specified session.

        Args:
            request: The HTTP request object
            session_id: UUID of the session to reconcile

        Returns:
            HttpResponse: Redirect to execution status page with message
        """
        from apps.serp_execution.tasks.monitoring_helpers import (
            reconcile_session_states,
        )

        try:
            # Get the session (ownership validated by mixin)
            session = self.get_session()
            if session is None:
                raise Http404("Session not found")

            # Trigger reconciliation
            result = reconcile_session_states(str(session.id))

            # Provide feedback based on results
            if result.get("reconciled"):
                changes = result.get("changes", [])
                messages.success(
                    request, f"State reconciled successfully: {', '.join(changes)}"
                )
            elif result.get("errors"):
                errors = result.get("errors", [])
                messages.error(
                    request, f"Reconciliation encountered errors: {', '.join(errors)}"
                )
            else:
                messages.info(
                    request, "No reconciliation needed - session state is correct"
                )

        except Exception as e:
            logger.error(f"Manual reconciliation failed for session {session_id}: {e}")
            messages.error(
                request, f"Reconciliation failed: {str(e)}. Please try again."
            )

        return redirect("serp_execution:execution_status", session_id=session_id)
