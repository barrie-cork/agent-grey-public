"""
Ultra-Simple Celery Tasks - Direct Database Updates
Replaces complex orchestration with simple direct database status updates.

This module implements the simplified task patterns specified in the PRP:
- Direct session.set_status() calls (no EventBus)
- Simple Celery retry patterns (no complex orchestration)
- Minimal abstraction layers
- Direct service calls from simple_services.py
"""

import logging

from celery import shared_task
from django.db import DatabaseError, transaction
from django.utils import timezone

# Import our simplified services
from apps.core.services.simple_services import (
    SearchResultProcessor,
    SimpleRetryManager,
    URLDeduplicationService,
)

# Import event system for real-time progress updates
from apps.core.state_machine.event_bus import event_bus
from apps.core.state_machine.events import QueryProgressEvent

logger = logging.getLogger(__name__)

# Initialize service instances
retry_manager = SimpleRetryManager()

KNOWN_SEARCH_CONFIG_KEYS = frozenset(
    {
        "domains",
        "file_types",
        "include_general_search",
        "include_guidelines_filter",
        "search_types",
        "search_type",  # legacy single-string back-compat key
        "max_results",
        "pagination",
        "query_splitting",
        "serp_providers",
    }
)


def get_next_execution_round(session) -> int:
    """Get the next execution round number for a session.

    Queries the max execution_round from SearchExecution for this session
    and returns the next value.

    Args:
        session: SearchSession instance.

    Returns:
        Next execution round number (1-based).
    """
    from django.db.models import Max

    from apps.serp_execution.models import SearchExecution

    max_round = SearchExecution.objects.filter(query__session=session).aggregate(
        max_round=Max("execution_round")
    )["max_round"]
    return (max_round or 0) + 1


def build_strategy_snapshot(strategy) -> dict:
    """Build a snapshot of the current search strategy for audit trail.

    Args:
        strategy: SearchStrategy instance.

    Returns:
        Dict containing PIC terms, search config, and timestamp.
    """
    return {
        "population_terms": strategy.population_terms or [],
        "interest_terms": strategy.interest_terms or [],
        "context_terms": strategy.context_terms or [],
        "search_config": strategy.search_config or {},
        "snapshot_at": timezone.now().isoformat(),
    }


@shared_task(bind=True, max_retries=3)
def execute_search_session_simple(self, session_id: str) -> dict:
    """
    Ultra-simple search session execution.

    Replaces complex ExecutionOrchestrator with direct database updates
    and simple service calls as specified in the PRP.

    Args:
        session_id: SearchSession UUID string

    Returns:
        Dict with execution results
    """
    from apps.review_manager.models import SearchSession

    try:
        with transaction.atomic():
            # Use select_for_update to prevent concurrent executions of the same session.
            # Without this lock, two tasks dispatched in quick succession can both pass
            # the status check before either transitions to 'executing'.
            session = SearchSession.objects.select_for_update().get(id=session_id)

            # Check current status and transition appropriately
            if session.status == "ready_to_execute":
                # Normal flow: transition from ready_to_execute to executing
                session.set_status("executing", "Starting search execution...")
            elif session.status == "executing":
                # Already executing — duplicate dispatch, exit cleanly
                logger.info(
                    f"Session {session_id} already executing — skipping duplicate dispatch"
                )
                return {
                    "success": False,
                    "error": "Session is already executing",
                }
            else:
                # Invalid state for execution — likely a duplicate dispatch
                logger.warning(
                    f"Cannot execute session {session_id} from status '{session.status}' "
                    f"— duplicate dispatch or unexpected state"
                )
                return {
                    "success": False,
                    "error": f"Invalid status for execution: {session.status}",
                }

        logger.info(f"Starting simplified execution for session {session_id}")

        # Get session queries through search_strategy
        if not hasattr(session, "search_strategy"):
            session.set_status("processing_results", "No search strategy found")
            return {"success": False, "error": "No search strategy"}

        queries = session.search_strategy.search_queries.filter(
            is_active=True
        ).order_by("execution_order")
        total_queries = queries.count()

        if total_queries == 0:
            session.set_status("processing_results", "No queries to execute")
            return {"success": True, "queries_executed": 0}

        # Determine execution round and build strategy snapshot
        execution_round = get_next_execution_round(session)
        strategy_snapshot = build_strategy_snapshot(session.search_strategy)

        # Count existing results before this iteration
        from apps.results_manager.models import ProcessedResult

        previous_results_count = ProcessedResult.objects.filter(session=session).count()

        # Log iteration start
        from apps.review_manager.models import SessionActivity

        SessionActivity.log_activity(
            session=session,
            activity_type="search_iteration_started",
            description=f"Search iteration {execution_round} started",
            metadata={
                "execution_round": execution_round,
                "strategy_snapshot": strategy_snapshot,
                "previous_results_count": previous_results_count,
            },
        )

        # Initialize services -- use provider abstraction for SERP queries
        from apps.serp_execution.providers import (
            get_default_provider,
            get_provider,
            get_provider_display_name,
        )

        # Resolve providers from strategy config (backward compat: fall back to default)
        serp_provider_keys = session.search_strategy.search_config.get(
            "serp_providers", []
        )
        if serp_provider_keys:
            providers = [
                (get_provider(key), key, get_provider_display_name(key))
                for key in serp_provider_keys
            ]
        else:
            provider = get_default_provider()
            providers = [
                (
                    provider,
                    provider.provider_key,
                    get_provider_display_name(provider.provider_key),
                )
            ]
        logger.info(f"Using SERP providers: {', '.join(d for _, _, d in providers)}")

        # Resolve search types (google, scholar) from config
        # Backward compat: fall back to legacy single search_type string
        search_types = session.search_strategy.search_config.get("search_types", [])
        if not search_types:
            legacy_type = session.search_strategy.search_config.get(
                "search_type", "google"
            )
            search_types = [legacy_type] if legacy_type else ["google"]
        logger.info(f"Using search types: {', '.join(search_types)}")

        # Map search_type values to display names for logging/progress
        search_type_display = {"google": "Google", "scholar": "Google Scholar"}

        result_processor = SearchResultProcessor()
        processed_count = 0
        failed_queries = 0
        last_error_message = ""

        # ponytail: warn-only — honored path already works, this just stops silent no-ops
        unknown = set(session.search_strategy.search_config) - KNOWN_SEARCH_CONFIG_KEYS
        if unknown:
            logger.warning(
                f"Ignored unrecognised search_config keys {sorted(unknown)} for session {session.id} — "
                f"these do NOT cap the search; use 'max_results' (and 'pagination.max_pages')."
            )

        # Get max_results and pagination config from strategy
        # UX Priority: Accuracy & Reliability > Speed
        # Conservative pagination delay prevents premature rate limit stops
        max_results = session.search_strategy.search_config.get("max_results", 100)
        pagination_config = session.search_strategy.search_config.get(
            "pagination",
            {
                "enabled": True,
                "results_per_page": 10,
                "max_pages": 10,
                "delay_between_pages": 2.0,  # Increased from 0.5s to 2.0s for reliability
            },
        )

        # Total execution steps = queries * providers * search_types
        total_steps = total_queries * len(providers) * len(search_types)
        step = 0

        # Execute each query against each selected provider and search type
        from apps.serp_execution.models import SearchExecution

        for search_type in search_types:
            type_display = search_type_display.get(search_type, search_type)
            # Map search_type to Serper API type param ("google" -> "search")
            api_search_type = "scholar" if search_type == "scholar" else "search"

            for provider, provider_key, provider_display in providers:
                step_label = f"{provider_display} ({type_display})"
                logger.info(f"Executing queries with {step_label}")

                for i, query in enumerate(queries, 1):
                    step += 1
                    try:
                        # Update progress
                        session.update_status_detail(
                            f"Executing query {step} of {total_steps} "
                            f"({step_label}): {query.query_text[:50]}..."
                        )

                        # Emit real-time progress event for SSE streaming
                        event_bus.emit(
                            QueryProgressEvent(
                                session_id=str(session.id),
                                query_index=step,
                                total_queries=total_steps,
                                query_text=query.query_text,
                                status="starting",
                                target_domain=(
                                    query.target_domain
                                    if hasattr(query, "target_domain")
                                    else None
                                ),
                            )
                        )

                        # Create SearchExecution record
                        execution = SearchExecution.objects.create(
                            query=query,
                            status="in_progress",
                            search_engine=f"{provider_key}_{search_type}"
                            if search_type != "google"
                            else provider_key,
                            serp_provider=provider_key,
                            serp_provider_display=f"{provider_display} ({type_display})",
                            initiated_by=(
                                session.user if hasattr(session, "user") else None
                            ),
                            started_at=timezone.now(),
                            execution_round=execution_round,
                            strategy_snapshot=strategy_snapshot,
                        )

                        # Execute query using provider abstraction
                        # Pass search_type so the client uses the correct API endpoint
                        results, search_metadata = provider.safe_search(
                            query=query.query_text,
                            num_results=max_results,
                            session=session,
                            search_query=query,
                            pagination_config=pagination_config,
                            search_type=api_search_type,
                            query_index=i,
                            total_queries=total_queries,
                        )

                        # Check for provider-level errors
                        if "error" in results:
                            logger.warning(
                                f"Provider {provider_key} returned error for "
                                f"query {step}: {results['error']}"
                            )

                        # Update execution with API response and pagination metadata
                        execution.api_response = results
                        execution.api_result_count = len(results.get("organic", []))
                        execution.status = "completed"
                        execution.completed_at = timezone.now()

                        # Save pagination metadata for debugging and analytics
                        pagination_info = results.get("pagination", {})
                        if pagination_info:
                            execution.step_metadata = {"pagination": pagination_info}

                        execution.save()

                        # Process results using simple service
                        raw_results = results.get("organic", [])
                        if raw_results:
                            processed, errors = result_processor.process_search_results(
                                raw_results=raw_results,
                                execution=execution,
                                session=session,
                                execution_round=execution_round,
                            )
                            processed_count += processed

                            # Update execution with final counts
                            execution.results_count = processed
                            execution.save()

                            if errors:
                                logger.warning(
                                    f"Processing errors for query {query.id}: "
                                    f"{errors[:3]}"
                                )

                        # Log pagination info if available
                        if pagination_info:
                            logger.info(
                                f"Step {step}/{total_steps} completed: "
                                f"{len(raw_results)} results "
                                f"({pagination_info.get('pages_fetched', 1)} pages, "
                                f"reason: {pagination_info.get('stopped_reason', 'N/A')})"
                            )
                        else:
                            logger.info(
                                f"Step {step}/{total_steps} completed: "
                                f"{len(raw_results)} results"
                            )

                        # Emit completion event for real-time progress tracking
                        event_bus.emit(
                            QueryProgressEvent(
                                session_id=str(session.id),
                                query_index=step,
                                total_queries=total_steps,
                                query_text=query.query_text,
                                status="completed",
                                results_count=(
                                    processed
                                    if "processed" in locals()
                                    else len(raw_results)
                                ),
                                target_domain=(
                                    query.target_domain
                                    if hasattr(query, "target_domain")
                                    else None
                                ),
                                pagination_info=(
                                    {
                                        "pages_fetched": pagination_info.get(
                                            "pages_fetched", 1
                                        ),
                                        "stopped_reason": pagination_info.get(
                                            "stopped_reason", "unknown"
                                        ),
                                        "max_pages": pagination_info.get(
                                            "max_pages", 10
                                        ),
                                        "total_available": pagination_info.get(
                                            "total_available"
                                        ),
                                    }
                                    if pagination_info
                                    else None
                                ),
                            )
                        )

                    except (
                        ConnectionError,
                        TimeoutError,
                        DatabaseError,
                        OSError,
                        ValueError,
                    ) as e:
                        logger.error(
                            f"Error executing query {query.id} with {provider_key}: {e}"
                        )
                        failed_queries += 1
                        last_error_message = str(e)

                        # Update execution if it exists
                        if "execution" in locals():
                            execution.status = "failed"
                            execution.error_message = str(e)
                            execution.completed_at = timezone.now()
                            execution.save()

                        # Emit failure event for real-time tracking
                        event_bus.emit(
                            QueryProgressEvent(
                                session_id=str(session.id),
                                query_index=step,
                                total_queries=total_steps,
                                query_text=query.query_text,
                                status="failed",
                                results_count=0,
                                target_domain=(
                                    query.target_domain
                                    if hasattr(query, "target_domain")
                                    else None
                                ),
                            )
                        )

                        # Simple retry logic (no complex orchestration)
                        error_category = retry_manager.categorize_error(e)
                        if (
                            error_category in ["rate_limit", "network", "timeout"]
                            and self.request.retries < self.max_retries
                        ):
                            delay = retry_manager.get_retry_delay(
                                e, self.request.retries + 1
                            )
                            session.update_status_detail(
                                f"Query failed, retrying in {delay}s..."
                            )
                            raise self.retry(countdown=delay, exc=e)

                        # Non-retryable error or max retries reached
                        session.update_status_detail(f"Query {step} failed: {str(e)}")
                        continue

                    # Inter-query delay to spread API calls and respect rate limits
                    if step < total_steps:
                        inter_query_delay = 5.0  # 5 seconds between queries
                        logger.debug(
                            f"Waiting {inter_query_delay}s before next query "
                            f"(rate limit spacing)"
                        )
                        import time

                        time.sleep(inter_query_delay)

        # Log iteration completed with failure context
        all_failed = failed_queries == total_steps and total_steps > 0
        iteration_metadata = {
            "execution_round": execution_round,
            "new_results_count": processed_count,
            "queries_executed": total_steps,
            "queries_failed": failed_queries,
            "providers_used": [d for _, _, d in providers],
            "search_types": search_types,
        }
        if all_failed:
            iteration_metadata["all_queries_failed"] = True
            iteration_metadata["last_error"] = last_error_message[:500]

        SessionActivity.log_activity(
            session=session,
            activity_type="search_iteration_completed",
            description=(
                f"Search iteration {execution_round} failed: all {total_steps} executions returned errors"
                if all_failed
                else f"Search iteration {execution_round} completed"
            ),
            metadata=iteration_metadata,
        )

        # Update status detail if all queries failed (API error)
        if all_failed:
            session.update_status_detail(
                f"All {total_steps} executions failed: {last_error_message[:200]}"
            )

        # Transition to processing results (replaces EventBus state transition)
        session.set_status(
            "processing_results",
            f"Completed {total_steps} executions, processing results...",
        )

        # Chain to results processing task
        process_session_results_simple.delay(session_id)

        return {
            "success": True,
            "queries_executed": total_steps,
            "results_processed": processed_count,
            "session_id": session_id,
        }

    except SearchSession.DoesNotExist:
        logger.error(f"Session {session_id} not found")
        return {"success": False, "error": "Session not found"}

    except (
        Exception
    ) as e:  # Intentional broad catch: Celery task last-resort error handler
        logger.error(f"Execution failed for session {session_id}: {e}", exc_info=True)

        # Update session to failed state
        try:
            session = SearchSession.objects.get(id=session_id)
            session.set_status("ready_to_execute", f"Execution failed: {str(e)}")
        except Exception:  # Intentional broad catch: last-resort recovery in error path
            pass

        # Simple retry logic
        if self.request.retries < self.max_retries:
            delay = retry_manager.get_retry_delay(e, self.request.retries + 1)
            raise self.retry(countdown=delay, exc=e)

        return {"success": False, "error": str(e)}


@shared_task(bind=True, max_retries=3)
def process_session_results_simple(self, session_id: str) -> dict:
    """
    Ultra-simple results processing with URL-only deduplication.

    Implements exact CORE_REQUIREMENTS.md status messages:
    - "Normalising URLs..."
    - "Conducting cross-query deduplication..."
    - "Finalising results..."

    Args:
        session_id: SearchSession UUID string

    Returns:
        Dict with processing results
    """
    from apps.review_manager.models import SearchSession

    try:
        session = SearchSession.objects.get(id=session_id)

        logger.info(f"Starting simplified results processing for session {session_id}")

        # Step 1: URL Normalisation (exact CORE_REQUIREMENTS message)
        session.update_status_detail("Normalising URLs...")

        # Import here to avoid circular imports
        from apps.results_manager.models import ProcessedResult

        # Count initial results
        initial_count = ProcessedResult.objects.filter(session=session).count()

        # Step 2: Cross-query deduplication (exact CORE_REQUIREMENTS message)
        session.update_status_detail("Conducting cross-query deduplication...")
        deduplication_service = URLDeduplicationService()
        dedup_result = deduplication_service.deduplicate_session_results(session)
        duplicates_removed = dedup_result["total_duplicates"]

        # Step 3: Finalisation (exact CORE_REQUIREMENTS message)
        session.update_status_detail("Finalising results...")

        # Update session statistics
        # Count results with processing_status="success" (aligns with dedup service)
        final_count = ProcessedResult.objects.filter(
            session=session, processing_status="success"
        ).count()

        with transaction.atomic():
            session.total_results = final_count
            session.save(update_fields=["total_results"])

        # Complete processing (automatic transition to ready_for_review)
        session.set_status(
            "ready_for_review",
            f"Processing complete: {final_count} results ready for review",
        )

        logger.info(
            f"Processing complete for session {session_id}: "
            f"{final_count} unique results ({duplicates_removed} duplicates removed)"
        )

        return {
            "success": True,
            "initial_results": initial_count,
            "final_results": final_count,
            "duplicates_removed": duplicates_removed,
            "session_id": session_id,
        }

    except SearchSession.DoesNotExist:
        logger.error(f"Session {session_id} not found for processing")
        return {"success": False, "error": "Session not found"}

    except (
        Exception
    ) as e:  # Intentional broad catch: Celery task last-resort error handler
        logger.error(
            f"Results processing failed for session {session_id}: {e}", exc_info=True
        )

        # Update session status on failure
        try:
            session = SearchSession.objects.get(id=session_id)
            session.set_status("executing", f"Processing failed: {str(e)}")
        except Exception:  # Intentional broad catch: last-resort recovery in error path
            pass

        # Simple retry logic
        if self.request.retries < self.max_retries:
            delay = retry_manager.get_retry_delay(e, self.request.retries + 1)
            raise self.retry(countdown=delay, exc=e)

        return {"success": False, "error": str(e)}


# Backward compatibility alias for existing code
initiate_search_session_execution_task = execute_search_session_simple
