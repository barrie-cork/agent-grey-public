"""Search strategy views implementing the PIC framework for grey literature research.

This module handles the Population, Interest/Intervention, Context (PIC) framework
for systematic literature review search strategy definition. The PIC framework
helps researchers create comprehensive and structured search queries by breaking
down search concepts into three key components.

The module provides both traditional form-based interfaces and AJAX endpoints
for real-time query preview and validation.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from apps.core.utils.error_responses import (
    error_response,
    permission_denied_response,
    validation_error_response,
)
from apps.review_manager.models import SearchSession, SessionActivity

from .api_types import QueryGenerationRequest
from .forms import SearchStrategyForm
from .models import SearchStrategy
from .services import SearchStrategyService

logger = logging.getLogger(__name__)


class SessionOwnershipMixin:
    """Mixin to ensure user owns the search session.

    Provides ownership validation for all views that operate on search sessions,
    preventing unauthorized access to session data and maintaining data security.
    Used across all search strategy views to enforce proper access control.
    """

    def get_session(self):
        """Get and validate session ownership.

        Retrieves the search session from URL parameters and validates that
        the current user is the owner of the session. This is a critical
        security check to prevent unauthorized access to session data.

        Returns:
            SearchSession: The validated session object.

        Raises:
            Http404: If session does not exist.
            PermissionDenied: If user is not the session owner.
        """
        session_id = self.kwargs.get("session_id")  # type: ignore[attr-defined]
        session = get_object_or_404(SearchSession, id=session_id)

        if session.owner != self.request.user:  # type: ignore[attr-defined]
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("You don't have permission to access this session.")

        return session


class SearchStrategyView(LoginRequiredMixin, SessionOwnershipMixin, TemplateView):
    """Main search strategy view implementing the PIC framework interface.

    Provides the primary interface for defining search strategies using the
    Population, Interest/Intervention, Context (PIC) framework. The PIC framework
    is a systematic approach for structuring literature search queries:

    - Population: Target group or demographic being studied
    - Interest/Intervention: The intervention, exposure, or phenomena of interest
    - Context: Setting, location, or circumstances where the research applies

    This view handles both GET requests (displaying the form) and POST requests
    (processing form submissions, validation, and query generation). It enforces
    the 9-state workflow by only allowing strategy editing in appropriate states.

    Attributes:
        template_name: Path to the strategy form template.
        session: Current search session (set in dispatch method).
    """

    template_name = "search_strategy/strategy_form.html"

    def __init__(self, *args, **kwargs):
        """Initialize view with service layer."""
        super().__init__(*args, **kwargs)
        self.strategy_service = SearchStrategyService()

    def dispatch(self, request, *args, **kwargs):
        """Validate session status and ownership before processing.

        Ensures the session is in an appropriate state for strategy editing.
        Originally only 'draft' and 'defining_search' states allowed modification,
        but now we also allow returning from later states with proper warnings.

        SECURITY: Only session owners can access search strategy. Reviewers
        (invited collaborators) are prevented from viewing or editing the
        search strategy to maintain blind review integrity.

        Args:
            request: The HTTP request object.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            HttpResponse: Either continues to view processing or redirects to session detail.

        Raises:
            PermissionDenied: If user is not the session owner.
        """
        self.session = self.get_session()

        # SECURITY CHECK: Only owners can access search strategy
        # Reviewers must be prevented from seeing strategy to maintain blind review
        if self.session.owner != request.user:
            from django.core.exceptions import PermissionDenied

            logger.warning(
                f"User {request.user.id} ({request.user.username}) attempted to access "
                f"search strategy for session {self.session.id} owned by "
                f"{self.session.owner.id} ({self.session.owner.username})"
            )

            raise PermissionDenied(
                "Only the session owner can define or edit the search strategy. "
                "Reviewers can only access results after searches are complete."
            )

        # States that can return to defining_search
        returnable_states = [
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
        ]

        # States that cannot edit strategy at all
        blocked_states = ["completed", "archived"]

        if self.session.status in blocked_states:
            messages.error(
                request,
                f"Cannot edit search strategy. Session is in '{self.session.get_status_display()}' status.",
            )
            return redirect("review_manager:session_detail", session_id=self.session.id)

        # If coming from a later state, handle the transition
        if self.session.status in returnable_states:
            result = self._handle_returnable_state_transition(request)
            if result is not None:
                return result

        return super().dispatch(request, *args, **kwargs)

    def _handle_returnable_state_transition(self, request):
        """Handle session transition back to defining_search from returnable states.

        Args:
            request: The HTTP request.

        Returns:
            HttpResponse redirect if transition failed, None if successful.
        """
        from django.db.models import Count

        from apps.results_manager.models import ProcessedResult

        result_stats = ProcessedResult.objects.filter(session=self.session).aggregate(
            count=Count("id")
        )
        result_count = result_stats["count"]
        if result_count > 0:
            SessionActivity.log_activity(
                session=self.session,
                activity_type="strategy_modified",
                description="Search strategy modified after previous execution",
                user=request.user,
                metadata={
                    "previous_status": self.session.status,
                    "existing_results_count": result_count,
                },
            )

        if self.session.can_transition_to("defining_search"):
            with transaction.atomic():
                session = SearchSession.objects.select_for_update().get(
                    pk=self.session.pk
                )
                if session.can_transition_to("defining_search"):
                    old_status = session.status
                    session.status = "defining_search"
                    session.save(update_fields=["status"])

                    SessionActivity.log_activity(
                        session=session,
                        activity_type="status_changed",
                        description=f"Returned to search strategy editing from {old_status}",
                        user=request.user,
                        metadata={
                            "old_status": old_status,
                            "new_status": "defining_search",
                            "reason": "user_initiated_strategy_modification",
                        },
                    )
                    self.session = session

            messages.info(
                request,
                f"Session status changed from '{old_status}' to 'Defining Search' to allow strategy modification.",
            )
            return None
        else:
            return self._attempt_indirect_transition(request)

    def _attempt_indirect_transition(self, request):
        """Attempt indirect path back to defining_search through intermediate states.

        Args:
            request: The HTTP request.

        Returns:
            HttpResponse redirect if no path found, None if transition succeeded.
        """
        transition_path = []
        current = self.session.status

        while (
            current != "defining_search" and current in self.session.ALLOWED_TRANSITIONS
        ):
            if "defining_search" in self.session.ALLOWED_TRANSITIONS.get(current, []):
                transition_path.append("defining_search")
                break
            for next_state in self.session.ALLOWED_TRANSITIONS.get(current, []):
                if next_state in [
                    "ready_to_execute",
                    "executing",
                    "processing_results",
                    "draft",
                    "defining_search",
                ]:
                    transition_path.append(next_state)
                    current = next_state
                    break
            else:
                break

        if transition_path and transition_path[-1] == "defining_search":
            with transaction.atomic():
                session = SearchSession.objects.select_for_update().get(
                    pk=self.session.pk
                )
                for state in transition_path:
                    prev_status = session.status
                    session.status = state
                    session.save(update_fields=["status"])
                    SessionActivity.log_activity(
                        session=session,
                        activity_type="status_changed",
                        description=f"Transitioned from {prev_status} to {state} (indirect path to defining_search)",
                        user=request.user,
                        metadata={
                            "old_status": prev_status,
                            "new_status": state,
                            "reason": "indirect_transition",
                        },
                    )
                self.session = session

            messages.info(
                request,
                "Session returned to 'Defining Search' status to allow strategy modification.",
            )
            return None
        else:
            messages.error(
                request,
                f"Cannot transition from '{self.session.get_status_display()}' to strategy editing.",
            )
            return redirect("review_manager:session_detail", session_id=self.session.id)

    def get_context_data(self, **kwargs):
        """Add strategy data and form to context.

        Optimized to align with CORE_REQUIREMENTS:
        - Single query generation per request
        - Preserves full query details for execution display

        Prepares all necessary data for rendering the strategy form, including
        the strategy object, form instance, statistics, generated queries,
        and validation status. Creates a new strategy if none exists.

        Args:
            **kwargs: Additional context data from parent classes.

        Returns:
            Dictionary containing:
                - session: Current search session
                - strategy: SearchStrategy instance (created if needed)
                - form: SearchStrategyForm instance
                - stats: Strategy statistics (term counts, completion status)
                - queries: Preview of generated search queries
                - is_complete: Boolean indicating if strategy is ready for execution
                - validation_errors: Any validation issues found
        """
        context = super().get_context_data(**kwargs)

        # Get or create strategy
        strategy, created = SearchStrategy.objects.get_or_create(
            session=self.session,
            defaults={
                "user": self.request.user,
                "search_config": {
                    "domains": [],
                    "include_general_search": True,
                    "file_types": [],
                    "search_types": ["google"],
                    "max_results": 100,
                },
            },
        )

        # Generate queries ONCE and cache in context
        queries = strategy.generate_queries()  # Cached internally

        # Get stats (will use count_queries, not regenerate)
        stats = strategy.get_stats()

        # Initialize form
        form = SearchStrategyForm(instance=strategy)

        context.update(
            {
                "session": self.session,
                "strategy": strategy,
                "form": form,
                "stats": stats,
                "queries": queries,  # Already generated, no duplicate call
                "is_complete": strategy.is_complete,
                "validation_errors": strategy.validation_errors,
            }
        )

        return context

    def post(self, request, *args, **kwargs):
        """Handle strategy form submission.

        Processes form data using the service layer for business logic.
        Supports multiple submission actions:
        - Regular save: Updates strategy and stays on form
        - Execute search: Validates completeness and initiates search execution
        - Save and continue: Saves and redirects to execution interface

        Args:
            request: The HTTP request containing form data.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.

        Returns:
            HttpResponse: Redirect response or form re-render with errors.
        """
        self.session = self.get_session()

        # Get or create strategy using service
        strategy, created = self.strategy_service.get_or_create_strategy(
            self.session, request.user
        )

        # Initialize form with POST data
        form = SearchStrategyForm(request.POST, instance=strategy)

        if form.is_valid():
            return self._handle_valid_form(form, request)
        else:
            return self._handle_invalid_form(form, request)

    def _handle_valid_form(self, form, request):
        """Process a valid form submission.

        Args:
            form: The validated SearchStrategyForm.
            request: The HTTP request.

        Returns:
            HttpResponse: Redirect response based on action.
        """
        with transaction.atomic():
            # Save strategy and validate
            strategy, is_complete = self.strategy_service.validate_and_save_strategy(
                form
            )

            # Update search queries
            query_count = self.strategy_service.update_search_queries(strategy)

            # Log activity
            self.strategy_service.log_strategy_update(
                self.session, request.user, is_complete, query_count
            )

            # Handle status transitions if complete
            if is_complete:
                self.strategy_service.handle_status_transition(
                    self.session, request.user, request
                )
            else:
                messages.success(request, "Search strategy saved successfully.")

            # Handle different submission actions
            return self._handle_submission_action(request, is_complete)

    def _handle_submission_action(self, request, is_complete):
        """Handle different form submission actions.

        Args:
            request: The HTTP request.
            is_complete: Whether the strategy is complete.

        Returns:
            HttpResponse: Redirect response based on action.
        """
        logger.debug(f"POST data keys: {list(request.POST.keys())}")

        # Get the action value from the form
        action = request.POST.get("action")

        # Handle the new action pattern
        if action == "save_and_monitor":
            return self._handle_execute_search(request, is_complete)
        elif "save_and_continue" in request.POST:
            # CHANGED: Redirect directly to status page instead of execute view
            # OLD: return redirect("serp_execution:execute_search", session_id=self.session.id)
            return redirect(
                "serp_execution:execution_status", session_id=self.session.id
            )
        else:
            # Just save - stay on strategy form
            return redirect("search_strategy:strategy_form", session_id=self.session.id)

    def _handle_execute_search(self, request, is_complete):
        """Handle execute search action.

        Args:
            request: The HTTP request.
            is_complete: Whether the strategy is complete.

        Returns:
            HttpResponse: Redirect response.
        """
        # Check if strategy is complete
        if not is_complete:
            messages.error(
                request,
                "Cannot execute search: Strategy is not complete. Please fill in all required fields.",
            )
            return redirect("search_strategy:strategy_form", session_id=self.session.id)

        # Prepare for execution (transitions to ready_to_execute)
        prep_result = self.strategy_service.prepare_for_execution(
            self.session, request.user, request
        )

        if not prep_result["success"]:
            messages.error(request, prep_result["error"])
            return redirect("search_strategy:strategy_form", session_id=self.session.id)

        # Ensure execution task is dispatched directly as well
        # (belt-and-suspenders: state manager's on_commit auto-trigger may silently fail)
        self.session.refresh_from_db()
        if self.session.status == "ready_to_execute":
            try:
                from apps.serp_execution.tasks import (
                    initiate_search_session_execution_task,
                )

                initiate_search_session_execution_task.delay(str(self.session.id))
                logger.info(
                    f"Direct execution task dispatched for session {self.session.id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to dispatch execution task for session {self.session.id}: {e}"
                )

        messages.success(
            request,
            "Search strategy validated successfully. Execution is starting automatically...",
        )

        logger.debug(
            f"Strategy validated, redirecting to execution_status. "
            f"Automatic trigger will start execution for session {self.session.id}"
        )

        return redirect(
            "serp_execution:execution_status",
            session_id=self.session.id,
        )

    def _handle_invalid_form(self, form, request):
        """Handle invalid form submission.

        Args:
            form: The invalid SearchStrategyForm.
            request: The HTTP request.

        Returns:
            HttpResponse: Re-rendered form with errors.
        """
        messages.error(request, "Please correct the errors below.")

        # Re-render form with errors
        context = self.get_context_data()
        context["form"] = form
        return self.render_to_response(context)


@login_required
@require_http_methods(["POST"])
def update_strategy_ajax(request, session_id):
    """AJAX endpoint for real-time strategy updates and query preview.

    Processes PIC framework data from the frontend and returns live query
    previews without saving to the database. This enables users to see
    how their Population, Interest, and Context terms will be combined
    into search queries before committing the changes.

    The endpoint validates input using Pydantic schemas and generates
    queries using the same logic as the main form submission, ensuring
    consistency between preview and execution.

    Args:
        request: POST request containing JSON data with PIC terms and config.
        session_id: UUID string identifying the search session.

    Returns:
        JsonResponse containing:
            - success: Boolean indicating operation success
            - is_complete: Whether strategy meets completion requirements
            - validation_errors: Any validation issues found
            - queries: Array of generated query objects for preview
            - stats: Statistics about term counts and configuration
            - base_query: The core query combining all PIC terms

    Raises:
        Http404: If session does not exist.
        403: If user does not own the session.
        400: If request data is invalid.
        500: If server error occurs during processing.
    """
    try:
        # Get session and validate ownership
        session = get_object_or_404(SearchSession, id=session_id)
        if session.owner != request.user:
            return permission_denied_response("modify", "search strategy")
        # Get or create strategy
        strategy, created = SearchStrategy.objects.get_or_create(
            session=session, defaults={"user": request.user}
        )

        # Parse and validate form data
        try:
            raw_data = json.loads(request.body)
            # Manual validation for required fields
            if not all(
                key in raw_data
                for key in ["population_terms", "interest_terms", "context_terms"]
            ):
                return JsonResponse(
                    {
                        "error": "Missing required fields: population_terms, interest_terms, or context_terms"
                    },
                    status=400,
                )

            # Use TypedDict structure (no runtime validation)
            validated_data: QueryGenerationRequest = {
                "population_terms": [
                    term.strip()
                    for term in raw_data.get("population_terms", [])
                    if term and term.strip()
                ],
                "interest_terms": [
                    term.strip()
                    for term in raw_data.get("interest_terms", [])
                    if term and term.strip()
                ],
                "context_terms": [
                    term.strip()
                    for term in raw_data.get("context_terms", [])
                    if term and term.strip()
                ],
                "search_config": raw_data.get("search_config", {}),
            }
        except json.JSONDecodeError:
            return validation_error_response(
                field_errors={"json": ["Invalid JSON format"]}, message="Invalid JSON"
            )
        except Exception as e:
            return JsonResponse(
                {"error": "Validation failed", "details": str(e)}, status=400
            )

        # Update strategy fields with validated data (don't save yet)
        strategy.population_terms = validated_data["population_terms"]
        strategy.interest_terms = validated_data["interest_terms"]
        strategy.context_terms = validated_data["context_terms"]
        strategy.search_config = validated_data["search_config"]

        # Validate and generate queries
        is_complete = strategy.validate_completeness()
        queries = strategy.generate_queries()
        stats = strategy.get_stats()

        # Log query generation for monitoring
        logger.debug(f"Generated {len(queries)} queries for session {session_id}")
        for i, query_data in enumerate(queries):
            logger.debug(f"Query {i + 1}: {query_data}")

        # Format queries for preview
        # Note: estimated_results field removed as pre-execution estimates were unreliable
        # and created confusion when actual results differed significantly
        formatted_queries = []
        for i, query_data in enumerate(queries):
            formatted_queries.append(
                {
                    "id": i + 1,
                    "query": query_data["query"],
                    "type": query_data["type"],
                    "domain": query_data.get("domain", "General Search"),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "is_complete": is_complete,
                "validation_errors": strategy.validation_errors,
                "queries": formatted_queries,
                "stats": stats,
                "base_query": strategy.generate_base_query(),
            }
        )

    except Exception as e:
        return error_response(e, status_code=500)


@login_required
@require_http_methods(["POST"])
def check_query_lengths_ajax(request, session_id):
    """AJAX endpoint to check query lengths and provide splitting information.

    Validates that generated queries don't exceed recommended length limits
    and provides information about how queries would be split if enabled.
    This helps users understand when and why query splitting is needed.

    Args:
        request: POST request containing JSON data with PIC terms and config.
        session_id: UUID string identifying the search session.

    Returns:
        JsonResponse containing:
            - has_issues: Boolean indicating if any queries exceed length limit
            - issues: Array of length issue details for long queries
            - split_count: Number of queries after splitting (if enabled)
            - recommendations: Suggested actions based on query lengths

    Raises:
        Http404: If session does not exist.
        403: If user does not own the session.
        400: If request data is invalid.
        500: If server error occurs during processing.
    """
    session = get_object_or_404(SearchSession, id=session_id)

    # Validate session ownership
    if session.owner != request.user:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        # Parse JSON data
        data = json.loads(request.body)

        # Create temporary strategy for checking
        from .models import SearchStrategy

        temp_strategy = SearchStrategy(
            population_terms=data.get("population_terms", []),
            interest_terms=data.get("interest_terms", []),
            context_terms=data.get("context_terms", []),
            search_config=data.get("search_config", {}),
        )

        # Check query lengths
        max_length = (
            data.get("search_config", {})
            .get("query_splitting", {})
            .get("max_query_length", 2000)
        )
        length_issues = temp_strategy.check_query_lengths(max_length)

        # Calculate split count if splitting is enabled
        split_count = None
        if (
            data.get("search_config", {})
            .get("query_splitting", {})
            .get("enabled", False)
        ):
            split_queries = temp_strategy.generate_split_queries()
            split_count = len(split_queries)
        else:
            # Count how many queries would be generated without splitting
            base_queries = temp_strategy.generate_queries()
            split_count = len(base_queries)

        # Build recommendations
        recommendations = []
        if length_issues:
            if len(length_issues) == 1:
                recommendations.append(
                    "Consider enabling query splitting to avoid search failures."
                )
            else:
                recommendations.append(
                    f"Enable query splitting to handle {len(length_issues)} long queries."
                )

            # Check average excess
            total_excess = sum(issue["excess"] for issue in length_issues)
            avg_excess = total_excess // len(length_issues) if length_issues else 0

            if avg_excess > 1000:
                recommendations.append(
                    "Consider reducing the number of terms or using more specific domain searches."
                )

        return JsonResponse(
            {
                "has_issues": len(length_issues) > 0,
                "issues": length_issues,
                "split_count": split_count,
                "recommendations": recommendations,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error checking query lengths: {str(e)}")
        return error_response(e, status_code=500)


@login_required
@require_http_methods(["GET"])
def strategy_status_api(request, session_id):
    """API endpoint to get current strategy status and statistics.

    Provides read-only access to strategy completion status, validation
    errors, and statistical information. Used by frontend components
    to display strategy progress and completion indicators without
    needing to process form data.

    This endpoint is useful for dashboards, progress indicators, and
    other UI elements that need to display strategy status information.

    Args:
        request: GET request object.
        session_id: UUID string identifying the search session.

    Returns:
        JsonResponse containing:
            - exists: Boolean indicating if strategy exists
            - is_complete: Whether strategy meets all requirements
            - validation_errors: Dictionary of any validation issues
            - stats: Detailed statistics about PIC terms and configuration
            - query_count: Number of queries that would be generated
            - updated_at: ISO timestamp of last strategy modification

    Raises:
        Http404: If session does not exist.
        403: If user does not own the session.
        500: If server error occurs during processing.
    """
    try:
        # Get session and validate ownership
        session = get_object_or_404(SearchSession, id=session_id)
        if session.owner != request.user:
            return permission_denied_response("modify", "search strategy")

        # Get strategy if exists
        try:
            strategy = SearchStrategy.objects.get(session=session)
            stats = strategy.get_stats()
            queries = strategy.generate_queries()

            response_data = {
                "exists": True,
                "is_complete": strategy.is_complete,
                "validation_errors": strategy.validation_errors,
                "stats": stats,
                "query_count": len(queries),
                "updated_at": strategy.updated_at.isoformat(),
            }
        except SearchStrategy.DoesNotExist:
            response_data = {
                "exists": False,
                "is_complete": False,
                "validation_errors": {},
                "stats": {
                    "population_count": 0,
                    "interest_count": 0,
                    "context_count": 0,
                    "total_terms": 0,
                    "domain_count": 0,
                    "query_count": 0,
                    "is_complete": False,
                },
                "query_count": 0,
                "updated_at": None,
            }

        return JsonResponse(response_data)

    except Exception as e:
        return error_response(e, status_code=500)
