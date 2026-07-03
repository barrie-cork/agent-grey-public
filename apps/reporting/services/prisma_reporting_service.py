"""
PRISMA reporting service for reporting slice.
Business capability: PRISMA-compliant report generation and flow diagram data.
"""

from datetime import datetime

from django.db.models import QuerySet
from django.utils import timezone

from apps.core.logging import ServiceLoggerMixin
from apps.reporting.constants import PRISMAConstants
from apps.results_manager.api import get_deduplication_stats
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_manager.signals import get_session_data
from apps.review_results.api import get_review_progress_stats
from apps.review_results.models import SimpleReviewDecision, URLAccessLog
from apps.search_strategy.signals import get_session_queries_data
from apps.serp_execution.api import get_raw_results_count, get_session_executions_data

# Use dependency injection instead of direct imports


class PrismaReportingService(ServiceLoggerMixin):
    """Service for generating PRISMA-compliant reports and flow diagrams."""

    def generate_prisma_flow_data(self, session_id: str):
        """
        Generate data for PRISMA flow diagram.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with PRISMA flow data
        """
        # Import here to get actual data
        from apps.review_manager.models import SearchSession

        # Get session directly to ensure we have the latest data
        try:
            session = SearchSession.objects.get(id=session_id)
            session_data = {
                "id": str(session.id),
                "title": session.title,
                "created_at": session.created_at.isoformat(),
            }
        except SearchSession.DoesNotExist:
            return {}

        # Gather data from different stages
        identification_data = self._gather_identification_data(session_id)
        screening_data = self._gather_screening_data(session_id)
        retrieval_data = self._gather_retrieval_data(session_id)
        eligibility_data = self._gather_eligibility_data(session_id)
        included_data = self._gather_included_data(session_id)
        iteration_data = self._gather_iteration_breakdown(session_id)

        # Calculate summary statistics
        summary_data = self._calculate_summary_statistics(
            identification_data,
            screening_data,
            retrieval_data,
            eligibility_data,
            included_data,
        )

        # Build and return flow data
        return self._build_flow_data_structure(
            session_data,
            identification_data,
            screening_data,
            retrieval_data,
            eligibility_data,
            included_data,
            summary_data,
            iteration_data,
        )

    def _get_session_data(self, session_id: str):
        """Get session data using internal API."""
        return get_session_data(session_id)

    def _gather_identification_data(self, session_id: str):
        """Gather identification stage data with detailed source breakdown."""
        queries_data = get_session_queries_data(session_id)
        executions_data = get_session_executions_data(session_id)
        raw_results_response = get_raw_results_count(session_id)

        # Extract count from response - handle both dict and integer responses
        if isinstance(raw_results_response, dict):
            raw_results_count = raw_results_response.get("count", 0)
        elif isinstance(raw_results_response, int):
            raw_results_count = raw_results_response
        else:
            raw_results_count = 0

        # Query-based breakdown using SearchExecution + SearchQuery
        from apps.serp_execution.models import SearchExecution

        completed_executions = SearchExecution.objects.filter(
            query__session_id=session_id,
            status="completed",
        ).select_related("query")

        websites = 0
        organizations = 0
        for execution in completed_executions:
            count = execution.results_count or 0
            if execution.query.target_domain:
                organizations += count
            else:
                websites += count

        # Get per-provider source breakdown for audit trail
        from apps.reporting.services.search_source_service import (
            get_search_source_breakdown,
        )

        search_source_breakdown = get_search_source_breakdown(session_id)

        # Count manually added results (identified during screening)
        from apps.results_manager.models import ProcessedResult

        other_sources_count = ProcessedResult.objects.filter(
            session_id=session_id,
            is_manually_added=True,
            processing_status="success",
        ).count()

        return {
            "database": raw_results_count,
            "other_sources": other_sources_count,
            "total": raw_results_count + other_sources_count,
            "websites": websites,
            "organizations": organizations,
            "citation_searching": 0,
            "queries_data": queries_data,
            "executions_data": executions_data,
            "search_source_breakdown": search_source_breakdown,
        }

    def _gather_screening_data(self, session_id: str):
        """Gather screening stage data."""
        # Get actual deduplication stats from the results manager
        dedup_stats = get_deduplication_stats(session_id)

        # Get actual processed results count (excluding hidden)
        from apps.results_manager.models import ProcessedResult  # noqa: F811

        actual_processed_count = ProcessedResult.objects.filter(
            session__id=session_id
        ).count()

        # Count hidden results for reporting
        hidden_count = ProcessedResult.objects.filter(
            session__id=session_id, is_hidden=True
        ).count()

        # Get hidden iterations for the note
        hidden_iterations = []
        if hidden_count > 0:
            hidden_iterations = list(
                ProcessedResult.objects.filter(session__id=session_id, is_hidden=True)
                .values_list("execution_round", flat=True)
                .distinct()
            )

        duplicates_removed = dedup_stats.get("duplicates_removed", 0)
        unique_results = dedup_stats.get("unique_results", 0)
        if (
            "duplicates_removed" not in dedup_stats
            or "unique_results" not in dedup_stats
        ):
            self.logger.warning(
                "Dedup stats missing expected keys for session %s: %s",
                session_id,
                list(dedup_stats.keys()),
            )

        return {
            "records_screened": actual_processed_count,
            "duplicates_removed": duplicates_removed,
            "excluded": 0,  # Initial screening exclusions
            "unique_results": unique_results,
            "processed_results": actual_processed_count,
            "hidden_count": hidden_count,
            "hidden_iterations": sorted(hidden_iterations),
        }

    def _gather_retrieval_data(self, session_id: str):
        """
        Gather PRISMA-compliant retrieval stage data.

        Uses only actual user interaction data from URL access logs.
        Does not use theoretical PDF availability as fallback.
        """
        retrieval_stats = self.get_retrieval_statistics(session_id)

        # Return actual statistics based on user interactions only
        return {
            "reports_sought": retrieval_stats["reports_sought_for_retrieval"],
            "reports_not_retrieved": retrieval_stats["reports_not_retrieved"],
            "reports_retrieved": retrieval_stats["reports_retrieved"],
            "failure_reasons": retrieval_stats["failure_reasons"],
            "retrieval_rate": retrieval_stats["retrieval_rate"],
            "reports_assessed_for_eligibility": retrieval_stats[
                "reports_assessed_for_eligibility"
            ],
        }

    def _gather_eligibility_data(self, session_id: str):
        """Gather eligibility stage data."""
        # Get actual review stats - this already queries the database directly
        review_stats = get_review_progress_stats(session_id)
        exclusion_reasons = self.get_exclusion_reasons(session_id)

        return {
            "reports_assessed": 0,  # Will be filled from retrieval data
            "full_text_assessed": 0,  # Will be filled from screening data
            "excluded": review_stats["excluded_results"],
            "exclusion_reasons": exclusion_reasons,
            "review_stats": review_stats,
        }

    def _gather_included_data(self, session_id: str):
        """Gather included stage data."""
        # Get actual review stats - this already queries the database directly
        review_stats = get_review_progress_stats(session_id)

        return {
            "studies_included": review_stats["included_results"],
            "qualitative": review_stats["included_results"],
            "quantitative": review_stats["included_results"],
            "total": review_stats["included_results"],
            "maybe_results": review_stats.get("maybe_results", 0),
            "pending_results": review_stats["pending_results"],
            "reports_included": review_stats["included_results"],  # For the new box
        }

    def _calculate_summary_statistics(
        self,
        identification_data: dict,
        screening_data: dict,
        retrieval_data: dict,
        eligibility_data: dict,
        included_data: dict,
    ):
        """Calculate summary statistics from stage data."""
        review_stats = eligibility_data["review_stats"]
        total_reviewed = (
            review_stats["included_results"]
            + review_stats["excluded_results"]
            + review_stats.get("maybe_results", 0)
        )
        inclusion_rate = (
            (review_stats["included_results"] / total_reviewed * 100)
            if total_reviewed > 0
            else 0
        )

        # Extract search engines from queries
        search_engines = set()
        for query in identification_data.get("queries_data", []):
            if query.get("search_engines"):
                search_engines.update(query["search_engines"])

        return {
            "inclusion_rate": round(inclusion_rate, 1),
            "retrieval_rate": retrieval_data["retrieval_rate"],
            "total_reviewed": total_reviewed,
            "search_engines": list(search_engines),
        }

    def _build_flow_data_structure(
        self,
        session_data: dict,
        identification_data: dict,
        screening_data: dict,
        retrieval_data: dict,
        eligibility_data: dict,
        included_data: dict,
        summary_data: dict,
        iteration_data: list | None = None,
    ):
        """Build the final PRISMA flow data structure."""
        # Update eligibility data with values from other stages
        eligibility_data["reports_assessed"] = retrieval_data[
            "reports_assessed_for_eligibility"
        ]
        eligibility_data["full_text_assessed"] = screening_data["unique_results"]

        return {
            # Legacy flat structure for backward compatibility
            "raw_search_results": identification_data["total"],
            "duplicates_removed": screening_data["duplicates_removed"],
            "processed_results": screening_data.get(
                "processed_results", screening_data["unique_results"]
            ),
            "results_included": included_data["studies_included"],
            "results_excluded": eligibility_data["excluded"],
            "results_maybe": included_data["maybe_results"],
            "results_pending": included_data["pending_results"],
            "session_metadata": {
                "session_id": session_data["id"],
                "title": session_data["title"],
                "created_date": session_data["created_at"][:10],
            },
            # PRISMA 2020 nested structure
            "identification": {
                "database": identification_data["database"],
                "other_sources": identification_data["other_sources"],
                "total": identification_data["total"],
                "websites": identification_data["websites"],
                "organizations": identification_data["organizations"],
                "citation_searching": identification_data["citation_searching"],
            },
            "screening": {
                "records_screened": screening_data["records_screened"],
                "duplicates_removed": screening_data["duplicates_removed"],
                "excluded": screening_data["excluded"],
            },
            "retrieval": {
                "reports_sought": retrieval_data["reports_sought"],
                "reports_not_retrieved": retrieval_data["reports_not_retrieved"],
                "reports_retrieved": retrieval_data["reports_retrieved"],
                "failure_reasons": retrieval_data["failure_reasons"],
            },
            "eligibility": {
                "reports_assessed": eligibility_data["reports_assessed"],
                "full_text_assessed": eligibility_data["full_text_assessed"],
                "excluded": eligibility_data["excluded"],
                "exclusion_reasons": eligibility_data["exclusion_reasons"],
            },
            "included": {
                "studies_included": included_data["studies_included"],
                "qualitative": included_data["qualitative"],
                "quantitative": included_data["quantitative"],
                "total": included_data["total"],
            },
            "summary": summary_data,
            "iterations": iteration_data or [],
            "hidden_results": {
                "count": screening_data.get("hidden_count", 0),
                "iterations": screening_data.get("hidden_iterations", []),
            },
            "search_sources": identification_data.get("search_source_breakdown", []),
        }

    def _gather_iteration_breakdown(self, session_id: str) -> list[dict]:
        """Gather per-iteration breakdown for PRISMA reporting.

        Returns per-iteration stats including query-level detail.

        Args:
            session_id: UUID of the SearchSession.

        Returns:
            List of dicts, one per iteration, each containing:
                - round: iteration number
                - raw_results: total raw results in this iteration
                - unique_results: non-duplicate results
                - duplicates_found: duplicates within this iteration
                - hidden_count: results hidden by user
                - strategy_snapshot: PIC terms + search config at time of execution
                - queries: per-query breakdown (text, domain, results_count)
        """
        from apps.results_manager.models import ProcessedResult
        from apps.serp_execution.models import SearchExecution

        # Get all execution rounds for this session
        executions = SearchExecution.objects.filter(
            query__session_id=session_id
        ).order_by("execution_round", "created_at")

        # Group by execution_round
        rounds: dict[int, dict] = {}
        for execution in executions:
            round_num = execution.execution_round
            if round_num not in rounds:
                rounds[round_num] = {
                    "round": round_num,
                    "strategy_snapshot": execution.strategy_snapshot,
                    "queries": [],
                    "raw_results": 0,
                }
            rounds[round_num]["queries"].append(
                {
                    "query_text": execution.query.query_text if execution.query else "",
                    "domain": (
                        execution.query.target_domain
                        if execution.query and execution.query.target_domain
                        else "General Search"
                    ),
                    "results_count": execution.results_count or 0,
                }
            )
            rounds[round_num]["raw_results"] += execution.results_count or 0

        # Enrich with ProcessedResult stats per round
        for round_num, data in rounds.items():
            round_results = ProcessedResult.objects.filter(
                session_id=session_id, execution_round=round_num
            )
            data["unique_results"] = round_results.filter(
                processing_status="success"
            ).count()
            data["duplicates_found"] = round_results.filter(
                processing_status="filtered"
            ).count()
            data["hidden_count"] = round_results.filter(is_hidden=True).count()

        return sorted(rounds.values(), key=lambda x: x["round"])

    def get_retrieval_statistics(self, session_id: str):
        """
        Get PRISMA-compliant URL retrieval statistics based on actual user interactions.

        PRISMA Compliance:
        - Reports sought for retrieval: Only URLs actually clicked by users
        - Reports not retrieved: Only URLs clicked but failed to access
        - Reports retrieved: Only URLs clicked and successfully accessed

        Returns:
            Dictionary with retrieval metrics
        """
        # Get all URL access logs for the session
        access_logs = URLAccessLog.objects.filter(session__id=session_id)

        # Count unique results that were sought for retrieval (actually clicked by users)
        sought_results = access_logs.values("result_id").distinct().count()

        # PRISMA Compliance: If no URLs have been clicked, report 0 for all retrieval metrics
        # Do NOT use theoretical PDF availability as a fallback
        if sought_results == 0:
            self.logger.info(
                f"No URL clicks recorded for session {session_id}. "
                "Reporting 0 for all retrieval statistics (PRISMA-compliant)."
            )
            return {
                "reports_sought_for_retrieval": 0,
                "reports_not_retrieved": 0,
                "reports_retrieved": 0,
                "reports_assessed_for_eligibility": 0,
                "failure_reasons": {},
                "retrieval_rate": 0.0,
            }

        # Count results not retrieved (clicked but marked as failed)
        not_retrieved = (
            access_logs.filter(access_successful=False)
            .values("result_id")
            .distinct()
            .count()
        )

        # Calculate retrieved (clicked and successful access)
        retrieved = sought_results - not_retrieved

        # Get breakdown of failure reasons from actual failed attempts
        failure_reasons = {}
        failed_logs = access_logs.filter(access_successful=False)
        for log in failed_logs:
            reason = (
                log.get_failure_reason_display() if log.failure_reason else "Unknown"
            )
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

        return {
            "reports_sought_for_retrieval": sought_results,
            "reports_not_retrieved": not_retrieved,
            "reports_retrieved": retrieved,
            "reports_assessed_for_eligibility": retrieved,  # All retrieved reports are assessed
            "failure_reasons": failure_reasons,
            "retrieval_rate": round(
                (retrieved / sought_results * 100) if sought_results > 0 else 0, 1
            ),
        }

    def calculate_review_period_from_data(self, session_data: dict):
        """
        Calculate review period from session data.

        Args:
            session_data: Session data dictionary

        Returns:
            Dictionary with start_date, end_date, and duration_days
        """
        created_date = datetime.fromisoformat(
            session_data["created_at"].replace("Z", "+00:00")
        )

        return {
            "start_date": created_date.date().isoformat(),
            "end_date": created_date.date().isoformat(),  # Use same for now
            "duration_days": 1,
        }

    def get_exclusion_reasons(self, session_id: str):
        """
        Get exclusion reasons and their counts.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary mapping exclusion reasons to counts
        """
        from apps.review_manager.models import SearchSession

        session = SearchSession.objects.select_related("current_configuration").get(
            id=session_id
        )
        cfg = session.current_configuration
        if cfg and cfg.is_workflow_2:
            return self._wf2_exclusion_reasons(session)

        excluded_decisions = SimpleReviewDecision.objects.filter(
            session_id=session_id, decision="exclude"
        )

        reasons = {}
        for decision in excluded_decisions:
            standardized_reason = self._get_standardized_reason(decision)
            if standardized_reason:
                reasons[standardized_reason] = reasons.get(standardized_reason, 0) + 1

        return reasons

    def _standardize_wf2_reason(self, raw_reason: str) -> str | None:
        """
        Standardize a free-text/coded WF2 ReviewerDecision.exclusion_reason.

        WF2 reasons are usually the choice CODE (e.g. "not_grey_lit") submitted
        from the screening UI, not prose. Resolve known codes to the same
        canonical label WF1 produces via get_exclusion_reason_display(), then
        fall back to the prose mapper for genuine free text.
        """
        if not raw_reason:
            return None
        code = raw_reason.strip().lower()
        label = PRISMAConstants.STANDARD_EXCLUSION_REASONS.get(code)
        if label:
            return label
        return self._map_text_to_standard_reason(code)

    def _wf2_exclusion_reasons(self, session) -> dict[str, int]:
        """
        Build exclusion-reason breakdown for a WF2 session.

        # mirrors internal_api._wf2_progress_counts
        Counts per-result (not per-decision): a result excluded by 3 reviewers
        contributes its reason exactly once.
        """
        from apps.review_results.models import ConflictResolution, ReviewerDecision

        conflicted_result_ids = set(
            ConflictResolution.objects.filter(result__session=session).values_list(
                "result_id", flat=True
            )
        )

        # Non-conflicted results that are unanimous EXCLUDE
        all_non_conflicted_reviewed = set(
            ReviewerDecision.objects.filter(result__session=session, is_revote=False)
            .exclude(decision="ABSTAIN")
            .exclude(result_id__in=conflicted_result_ids)
            .values_list("result_id", flat=True)
            .distinct()
        )
        results_with_non_exclude = set(
            ReviewerDecision.objects.filter(result__session=session, is_revote=False)
            .exclude(decision="ABSTAIN")
            .exclude(decision="EXCLUDE")
            .values_list("result_id", flat=True)
        )
        unanimous_exclude_ids = all_non_conflicted_reviewed - results_with_non_exclude

        reasons: dict[str, int] = {}

        # Unanimous-EXCLUDE results: take the exclusion_reason from any EXCLUDE decision
        for result_id in unanimous_exclude_ids:
            rd = (
                ReviewerDecision.objects.filter(
                    result_id=result_id, decision="EXCLUDE", is_revote=False
                )
                .exclude(exclusion_reason="")
                .first()
            )
            if rd is None:
                continue
            standardized = self._standardize_wf2_reason(rd.exclusion_reason)
            if standardized:
                reasons[standardized] = reasons.get(standardized, 0) + 1

        # Resolved-conflict EXCLUDE results: use final_decision.exclusion_reason
        resolved_exclude_conflicts = ConflictResolution.objects.filter(
            result__session=session,
            status=ConflictResolution.STATUS_RESOLVED,
            final_decision__decision="EXCLUDE",
        ).select_related("final_decision")
        for conflict in resolved_exclude_conflicts:
            fd = conflict.final_decision
            if not fd or not fd.exclusion_reason:
                continue
            standardized = self._standardize_wf2_reason(fd.exclusion_reason)
            if standardized:
                reasons[standardized] = reasons.get(standardized, 0) + 1

        return reasons

    def _get_standardized_reason(self, decision):
        """
        Get standardized exclusion reason from decision.

        Args:
            decision: SimpleReviewDecision instance

        Returns:
            Standardized reason string or None
        """
        reason = decision.exclusion_reason or decision.notes.strip()
        if not reason:
            return None

        # Use choice field display name if available
        if decision.exclusion_reason:
            return decision.get_exclusion_reason_display()

        # Map notes text to standardized reasons
        return self._map_text_to_standard_reason(reason.lower())

    def _map_text_to_standard_reason(self, reason_text):
        """
        Map freeform text to standardized exclusion reason.

        Args:
            reason_text: Lowercase reason text

        Returns:
            Standardized reason string
        """
        reason_mapping = {
            ("not relevant", "irrelevant"): "not_relevant",
            ("not grey", "not gray"): "not_grey_lit",
            ("no full text", "full text unavailable", "no access"): "no_access",
            ("duplicate",): "duplicate",
            ("wrong document type", "document type"): "wrong_document_type",
            ("language",): "language",
            ("population",): "wrong_population",
            ("intervention", "interest"): "wrong_intervention",
            ("quality", "methodology"): "other",
        }

        for keywords, reason_key in reason_mapping.items():
            if any(keyword in reason_text for keyword in keywords):
                return PRISMAConstants.STANDARD_EXCLUSION_REASONS[reason_key]

        return reason_text.title()

    def calculate_review_period(self, session):
        """
        Calculate the time period of the systematic review.

        Args:
            session: SearchSession instance

        Returns:
            Dictionary with review period information
        """
        period_info = {
            "start_date": session.created_at.date(),
            "end_date": (
                session.completed_at.date()
                if session.completed_at
                else timezone.now().date()
            ),
            "duration_days": 0,
            "phases": [],
        }

        if session.completed_at:
            duration = session.completed_at.date() - session.created_at.date()
            period_info["duration_days"] = duration.days

        # Calculate phase durations based on status changes
        activities = SessionActivity.objects.filter(
            session=session, activity_type="status_changed"
        ).order_by("created_at")

        phase_start = session.created_at
        for activity in activities:
            if activity.metadata and "new_status" in activity.metadata:
                phase_duration = (activity.created_at - phase_start).days
                period_info["phases"].append(
                    {
                        "status": activity.metadata.get("old_status", "draft"),
                        "duration_days": phase_duration,
                        "end_date": activity.created_at.date(),
                    }
                )
                phase_start = activity.created_at

        return period_info

    def generate_checklist_data(self, session_id: str):
        """
        Generate PRISMA checklist data for reporting.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with checklist items and completion status
        """
        # For now, return the same as export_prisma_checklist
        return self.export_prisma_checklist(session_id)

    def analyze_exclusion_reasons(self, session_id: str):
        """
        Analyze exclusion reasons for the systematic review.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with exclusion analysis
        """
        exclusion_reasons = self.get_exclusion_reasons(session_id)

        # Calculate totals and percentages
        total_exclusions = sum(exclusion_reasons.values())

        analysis = {
            "total_exclusions": total_exclusions,
            "reasons": [],
            "top_reasons": [],
        }

        # Format reasons with percentages
        for reason, count in exclusion_reasons.items():
            percentage = (count / total_exclusions * 100) if total_exclusions > 0 else 0
            analysis["reasons"].append(
                {"reason": reason, "count": count, "percentage": round(percentage, 1)}
            )

        # Sort by count to get top reasons
        analysis["reasons"].sort(key=lambda x: x["count"], reverse=True)
        analysis["top_reasons"] = analysis["reasons"][:3]

        # Add most common reason for backward compatibility
        if analysis["reasons"]:
            analysis["most_common_reason"] = analysis["reasons"][0]["reason"]
        else:
            analysis["most_common_reason"] = None

        return analysis

    def export_prisma_checklist(self, session_id: str):
        """
        Generate PRISMA checklist with completion status.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with PRISMA checklist data
        """
        try:
            session = SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            return {}

        # PRISMA 2020 checklist items
        checklist_items = [
            {
                "section": "Title",
                "item": 1,
                "description": "Identify the report as a systematic review.",
                "completed": bool(
                    session.title and "systematic" in session.title.lower()
                ),
                "evidence": session.title if session.title else None,
            },
            {
                "section": "Abstract",
                "item": 2,
                "description": "See the PRISMA 2020 for Abstracts checklist.",
                "completed": bool(session.description),
                "evidence": session.description if session.description else None,
            },
            {
                "section": "Rationale",
                "item": 3,
                "description": (
                    "Describe the rationale for the review in the context "
                    "of existing knowledge."
                ),
                "completed": bool(
                    session.description
                    and len(session.description)
                    > PRISMAConstants.MIN_DESCRIPTION_LENGTH
                ),
                "evidence": "Description provided" if session.description else None,
            },
            {
                "section": "Objectives",
                "item": 4,
                "description": (
                    "Provide an explicit statement of the objective(s) "
                    "or question(s) the review addresses."
                ),
                "completed": bool(session.description),
                "evidence": (
                    "Objectives in description" if session.description else None
                ),
            },
            # Note: This is a simplified version. A full implementation would
            # include all PRISMA items
        ]

        # Calculate completion statistics
        completed_items = sum(1 for item in checklist_items if item["completed"])
        total_items = len(checklist_items)
        completion_percentage = round(
            completed_items / total_items * PRISMAConstants.PERCENTAGE_MULTIPLIER, 1
        )

        return {
            "session_id": session_id,
            "checklist_items": checklist_items,
            "completion_summary": {
                "completed_items": completed_items,
                "total_items": total_items,
                "completion_percentage": completion_percentage,
            },
            "generated_at": timezone.now().isoformat(),
        }

    def get_irr_metrics(self, session_id: str) -> QuerySet:
        """
        Get inter-rater reliability metrics for dual-screening PRISMA report.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            QuerySet of InterRaterReliability objects with reviewer details
        """
        from apps.review_results.models import InterRaterReliability

        return (
            InterRaterReliability.objects.filter(search_session_id=session_id)
            .select_related("reviewer_a", "reviewer_b")
            .order_by("-calculated_at")
        )

    def get_conflict_summary(self, session_id: str) -> dict[str, int]:
        """
        Calculate conflict resolution summary for dual-screening PRISMA report.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with conflict counts by resolution method
        """
        from django.db.models import Count, Q

        from apps.review_results.models import ConflictResolution

        conflicts = ConflictResolution.objects.filter(result__session_id=session_id)

        # Use aggregation to avoid N+1 queries
        aggregate_result = conflicts.aggregate(
            total_conflicts=Count("id"),
            resolved_by_discussion=Count(
                "id", filter=Q(status="RESOLVED", resolution_method="CONSENSUS")
            ),
            resolved_by_revote=Count(
                "id", filter=Q(status="RESOLVED", resolution_method="REVOTE")
            ),
            resolved_by_arbitration=Count(
                "id", filter=Q(status="RESOLVED", resolution_method="ARBITRATION")
            ),
            pending_conflicts=Count(
                "id", filter=Q(status__in=["PENDING", "IN_DISCUSSION", "ESCALATED"])
            ),
        )

        return {
            "total_conflicts": aggregate_result["total_conflicts"],
            "resolved_by_discussion": aggregate_result["resolved_by_discussion"],
            "resolved_by_revote": aggregate_result["resolved_by_revote"],
            "resolved_by_arbitration": aggregate_result["resolved_by_arbitration"],
            "pending_conflicts": aggregate_result["pending_conflicts"],
        }

    def get_configuration_changes(self, session_id: str) -> QuerySet:
        """
        Get configuration changes for protocol deviation log in PRISMA report.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            QuerySet of ConfigurationChange objects ordered by date
        """
        from apps.review_manager.models import ConfigurationChange

        return (
            ConfigurationChange.objects.filter(session_id=session_id)
            .select_related("changed_by", "from_configuration", "to_configuration")
            .order_by("changed_at")
        )

    def get_report_data(self, session_id: str, report_type: str):
        """
        Get report data based on report type.

        Args:
            session_id: UUID of the SearchSession
            report_type: Type of report (full_report, prisma_flow, etc.)

        Returns:
            Dictionary with report data
        """
        # Import here to avoid circular imports
        from apps.reporting.tasks import generate_comprehensive_report_data

        if report_type == "full_report":
            # Use the same comprehensive data generation as tasks
            return generate_comprehensive_report_data(session_id)
        elif report_type == "prisma_flow":
            return self.generate_prisma_flow_data(session_id)
        elif report_type == "prisma_checklist":
            return self.export_prisma_checklist(session_id)
        else:
            # For other report types, return basic data
            session = SearchSession.objects.get(id=session_id)
            return {"session": session, "generated_at": timezone.now()}

    def auto_populate_other_methods(self, session_id: str) -> dict:
        """Auto-populate 'other methods' data from real session data."""
        from apps.results_manager.models import ProcessedResult
        from apps.review_results.models import BrowsingVisit
        from apps.serp_execution.models import SearchExecution

        # Identification: split search executions by query type
        executions = SearchExecution.objects.filter(
            query__session_id=session_id,
            status="completed",
        ).select_related("query")

        organisations = 0
        websites = 0
        for execution in executions:
            count = execution.results_count or 0
            if execution.query.target_domain:
                organisations += count
            else:
                websites += count

        # Manually added results (Stream-2 promotions from browsing)
        other_sources = ProcessedResult.objects.filter(
            session_id=session_id,
            is_manually_added=True,
            processing_status="success",
        ).count()

        # Retrieval stats from BrowsingVisit (other-methods arm only)
        # ponytail: exclude promoted visits to avoid double-counting with other_sources
        visits_qs = BrowsingVisit.objects.filter(
            session_id=session_id, promoted_result__isnull=True
        )
        reports_sought = visits_qs.count()
        reports_not_retrieved = visits_qs.filter(access_successful=False).count()
        reports_assessed = reports_sought - reports_not_retrieved

        # Capture provenance: how many visits used a de-personalised (incognito)
        # session. Methodological note, not a PRISMA flow count.
        de_personalised_visits = visits_qs.filter(captured_incognito=True).count()

        exclusion_reasons = self.get_exclusion_reasons(session_id)
        reports_excluded = sum(exclusion_reasons.values())

        return {
            "websites": websites,
            "organisations": organisations,
            "other_sources": other_sources,
            "citation_searching": 0,
            "reports_sought": reports_sought,
            "reports_not_retrieved": reports_not_retrieved,
            "reports_assessed": reports_assessed,
            "reports_excluded": reports_excluded,
            "exclusion_reasons": exclusion_reasons,
            "de_personalised_visits": de_personalised_visits,
            "personalised_visits": reports_sought - de_personalised_visits,
        }

    def generate_full_prisma_flow_data(self, session_id: str) -> dict:
        """Generate two-column PRISMA 2020 flow diagram data."""
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            return {}

        # Gather existing stage data
        identification = self._gather_identification_data(session_id)
        screening = self._gather_screening_data(session_id)
        retrieval_stats = self.get_retrieval_statistics(session_id)
        eligibility = self._gather_eligibility_data(session_id)
        included = self._gather_included_data(session_id)
        exclusion_reasons = self.get_exclusion_reasons(session_id)

        # Database flow (left column) -- traditional search results
        database_flow = {
            "identification": {
                "databases_registers": identification["database"],
                "duplicates_removed": screening["duplicates_removed"],
            },
            "screening": {
                "records_screened": screening["records_screened"],
                "records_excluded": screening["excluded"],
            },
            "retrieval": {
                "reports_sought": retrieval_stats["reports_sought_for_retrieval"],
                "reports_not_retrieved": retrieval_stats["reports_not_retrieved"],
            },
            "eligibility": {
                "reports_assessed": retrieval_stats["reports_assessed_for_eligibility"],
                "excluded": eligibility["excluded"],
                "exclusion_reasons": exclusion_reasons,
            },
        }

        # Other methods flow (right column) -- user override or auto-populated
        if session.prisma_other_methods:
            om = session.prisma_other_methods
        else:
            om = self.auto_populate_other_methods(session_id)

        other_methods_flow = {
            "identification": {
                "websites": om.get("websites", 0),
                "organisations": om.get("organisations", 0),
                "citation_searching": om.get("citation_searching", 0),
            },
            "retrieval": {
                "reports_sought": om.get("reports_sought", 0),
                "reports_not_retrieved": om.get("reports_not_retrieved", 0),
            },
            "eligibility": {
                "reports_assessed": om.get("reports_assessed", 0),
                "excluded": om.get("reports_excluded", 0),
                "exclusion_reasons": om.get("exclusion_reasons", {}),
            },
        }

        # Capture provenance (raw fact about how pages were captured; not subject
        # to PRISMA user overrides).
        from apps.review_results.models import BrowsingVisit

        captured = BrowsingVisit.objects.filter(
            session_id=session_id, promoted_result__isnull=True
        )
        captured_total = captured.count()
        de_personalised = captured.filter(captured_incognito=True).count()

        return {
            "database_flow": database_flow,
            "other_methods_flow": other_methods_flow,
            "included": {
                "new_studies": included["studies_included"],
                "total": included["total"],
            },
            "capture_provenance": {
                "total": captured_total,
                "de_personalised": de_personalised,
                "personalised": captured_total - de_personalised,
            },
            "session_metadata": {
                "session_id": str(session.id),
                "title": session.title,
                "created_date": session.created_at.isoformat()[:10],
                "has_user_overrides": bool(session.prisma_other_methods),
            },
        }
