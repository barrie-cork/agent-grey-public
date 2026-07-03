"""
Enhanced management command to detect and fix sessions stuck in any state.

This command provides comprehensive recovery for all workflow states with
detailed reporting and configurable timeouts.
"""

import json
import logging
import operator
from datetime import timedelta
from functools import reduce
from typing import Any, Dict, List

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.core.state_machine import state_machine
from apps.core.state_machine.exceptions import InvalidTransition
from apps.results_manager.models import ProcessedResult, ProcessingSession
from apps.review_manager.models import SearchSession
from apps.review_manager.services.recovery_manager import WorkflowRecoveryManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Detect and fix stuck sessions with comprehensive reporting"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fixed without making changes",
        )
        parser.add_argument(
            "--timeout-minutes",
            type=int,
            default=30,
            help="Minutes before considering session stuck (default: 30)",
        )
        parser.add_argument(
            "--json-output", action="store_true", help="Output results in JSON format"
        )
        parser.add_argument(
            "--state",
            type=str,
            help="Only check specific state (e.g., executing, processing_results)",
        )
        parser.add_argument(
            "--auto-recovery",
            action="store_true",
            help="Use WorkflowRecoveryManager for automatic recovery",
        )
        parser.add_argument(
            "--reconcile-states",
            action="store_true",
            help="Perform state reconciliation to fix desynchronization issues",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        dry_run = options["dry_run"]
        timeout_minutes = options["timeout_minutes"]
        json_output = options["json_output"]
        specific_state = options.get("state")
        use_auto_recovery = options.get("auto_recovery")
        reconcile_states = options.get("reconcile_states")

        # Handle state reconciliation if requested
        if reconcile_states:
            return self._handle_state_reconciliation(dry_run, json_output)

        if use_auto_recovery:
            # Use the WorkflowRecoveryManager for automatic recovery
            recovery_manager = WorkflowRecoveryManager()
            if not dry_run:
                stats = recovery_manager.recover_stuck_sessions()
                if json_output:
                    self.stdout.write(json.dumps(stats, indent=2))
                else:
                    self._output_recovery_stats(stats)
            else:
                # Dry run mode - just detect issues
                stats = self._dry_run_auto_recovery(recovery_manager, timeout_minutes)
                if json_output:
                    self.stdout.write(json.dumps(stats, indent=2))
                else:
                    self._output_recovery_stats(stats)
        else:
            # Use enhanced detection logic
            stuck_sessions = self.detect_stuck_sessions(timeout_minutes, specific_state)

            if not stuck_sessions:
                if not json_output:
                    self.stdout.write(self.style.SUCCESS("No stuck sessions found!"))
                else:
                    self.stdout.write(json.dumps({"stuck_sessions": 0}))
                return

            if not json_output:
                self.stdout.write(f"Found {len(stuck_sessions)} stuck sessions")

            recovery_report = self.process_stuck_sessions(stuck_sessions, dry_run)

            # Generate and output report
            if json_output:
                self.stdout.write(json.dumps(recovery_report, indent=2, default=str))
            else:
                self._output_report(recovery_report)

    def detect_stuck_sessions(
        self, timeout_minutes: int, specific_state: str | None = None
    ) -> List[SearchSession]:
        """
        Enhanced detection logic for various stuck states.

        Args:
            timeout_minutes: Base timeout in minutes
            specific_state: Optional specific state to check

        Returns:
            List of stuck SearchSession instances
        """
        threshold = timezone.now() - timedelta(minutes=timeout_minutes)

        # Define stuck conditions for each state
        stuck_conditions = []

        if not specific_state or specific_state == "executing":
            # Executing for too long (use longer timeout)
            exec_threshold = timezone.now() - timedelta(hours=1)
            stuck_conditions.append(
                Q(status="executing", updated_at__lt=exec_threshold)
            )

        if not specific_state or specific_state == "processing_results":
            # Processing without progress
            stuck_conditions.append(
                Q(status="processing_results", updated_at__lt=threshold)
            )

        if not specific_state or specific_state == "ready_to_execute":
            # Ready but never started (use much longer timeout)
            ready_threshold = timezone.now() - timedelta(hours=24)
            stuck_conditions.append(
                Q(status="ready_to_execute", updated_at__lt=ready_threshold)
            )

        if not stuck_conditions:
            return []

        # Find stuck sessions
        stuck_sessions = (
            SearchSession.objects.filter(reduce(operator.or_, stuck_conditions))
            .select_related("owner")
            .order_by("updated_at")
        )

        # Additional checks for specific states
        verified_stuck = []
        for session in stuck_sessions:
            if self._verify_stuck_status(session):
                verified_stuck.append(session)

        return verified_stuck

    def _verify_stuck_status(self, session: SearchSession) -> bool:
        """
        Verify if a session is truly stuck.

        Args:
            session: Session to verify

        Returns:
            True if session is stuck, False otherwise
        """
        if session.status == "executing":
            return self._verify_executing_stuck(session)
        elif session.status == "processing_results":
            return self._verify_processing_stuck(session)
        return True

    def _verify_executing_stuck(self, session: SearchSession) -> bool:
        """Verify if an executing session is stuck."""
        from apps.serp_execution.models import SearchExecution

        active_executions = SearchExecution.objects.filter(
            query__session=session, status__in=["pending", "running"]
        ).count()

        if active_executions > 0:
            # Check if they're making progress
            latest_execution = (
                SearchExecution.objects.filter(query__session=session)
                .order_by("-updated_at")
                .first()
            )

            if latest_execution:
                time_since_update = timezone.now() - latest_execution.updated_at
                if time_since_update < timedelta(minutes=15):
                    return False  # Still making progress

        return True

    def _verify_processing_stuck(self, session: SearchSession) -> bool:
        """Verify if a processing session is stuck."""
        try:
            processing = ProcessingSession.objects.filter(
                search_session=session
            ).latest("created_at")

            if processing.status == "in_progress":
                # Check heartbeat
                if processing.last_heartbeat:
                    time_since_heartbeat = timezone.now() - processing.last_heartbeat
                    if time_since_heartbeat < timedelta(minutes=10):
                        return False  # Still active

            elif processing.status == "completed":
                # Processing completed but state not updated
                return True

        except ProcessingSession.DoesNotExist:
            # No processing session but in processing state
            return True

        return True

    def process_stuck_sessions(
        self, sessions: List[SearchSession], dry_run: bool
    ) -> Dict[str, Any]:
        """
        Process and attempt to fix stuck sessions.

        Args:
            sessions: List of stuck sessions
            dry_run: Whether to perform dry run only

        Returns:
            Recovery report dictionary
        """
        report = {
            "timestamp": timezone.now(),
            "sessions_checked": len(sessions),
            "sessions_recovered": 0,
            "sessions_failed": 0,
            "by_status": {},
            "actions_taken": [],
            "errors": [],
        }

        for session in sessions:
            original_status = session.status

            # Track by status
            if original_status not in report["by_status"]:
                report["by_status"][original_status] = {
                    "count": 0,
                    "recovered": 0,
                    "failed": 0,
                }
            report["by_status"][original_status]["count"] += 1

            # Determine fix action
            fix_action = self._determine_fix_action(session)

            if dry_run:
                action_record = {
                    "session_id": str(session.id),
                    "session_title": session.title,
                    "original_status": original_status,
                    "proposed_action": fix_action["action"],
                    "target_state": fix_action["target_state"],
                    "reason": fix_action["reason"],
                    "dry_run": True,
                }
                report["actions_taken"].append(action_record)
                self.stdout.write(
                    self.style.WARNING(
                        f"[DRY RUN] Would fix session {session.id}: "
                        f"{original_status} -> {fix_action['target_state']}"
                    )
                )
            else:
                # Attempt to fix
                success, error_msg = self._fix_session(session, fix_action)

                action_record = {
                    "session_id": str(session.id),
                    "session_title": session.title,
                    "original_status": original_status,
                    "action_taken": fix_action["action"],
                    "target_state": fix_action["target_state"],
                    "success": success,
                    "error": error_msg if not success else None,
                    "timestamp": timezone.now(),
                }
                report["actions_taken"].append(action_record)

                if success:
                    report["sessions_recovered"] += 1
                    report["by_status"][original_status]["recovered"] += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Fixed session {session.id}: "
                            f"{original_status} -> {fix_action['target_state']}"
                        )
                    )
                else:
                    report["sessions_failed"] += 1
                    report["by_status"][original_status]["failed"] += 1
                    report["errors"].append(
                        {"session_id": str(session.id), "error": error_msg}
                    )
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to fix session {session.id}: {error_msg}"
                        )
                    )

        return report

    def _determine_fix_action(self, session: SearchSession) -> Dict[str, Any]:
        """
        Determine the appropriate fix action for a stuck session.

        Args:
            session: The stuck session

        Returns:
            Dictionary with fix action details
        """
        fixes = {
            "executing": {
                "action": "reset_to_ready",
                "target_state": "ready_to_execute",
                "reason": "Execution timeout - resetting for retry",
            },
            "processing_results": {
                "action": "complete_processing",
                "target_state": "ready_for_review",
                "reason": "Processing completed or stalled",
            },
            "ready_to_execute": {
                "action": "reset_to_defining",
                "target_state": "defining_search",
                "reason": "Session idle too long in ready state",
            },
        }

        # Check for special cases
        if session.status == "processing_results":
            # Check if actually has results
            result_count = ProcessedResult.objects.filter(session=session).count()

            if result_count == 0:
                # No results, check raw results
                from apps.serp_execution.models import RawSearchResult

                raw_count = RawSearchResult.objects.filter(
                    execution__query__session=session
                ).count()

                if raw_count == 0:
                    # No results at all, move back to ready
                    return {
                        "action": "reset_no_results",
                        "target_state": "ready_to_execute",
                        "reason": "No results found to process",
                    }

        return fixes.get(
            session.status,
            {
                "action": "force_reset",
                "target_state": "draft",
                "reason": f"Unknown stuck state: {session.status}",
            },
        )

    def _fix_session(
        self, session: SearchSession, fix_action: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Apply fix to a stuck session.

        Args:
            session: Session to fix
            fix_action: Fix action details

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Try normal transition first
            try:
                state_machine.transition(
                    session.id,
                    fix_action["target_state"],
                    metadata={
                        "trigger": "management_command_fix",
                        "reason": fix_action["reason"],
                        "action": fix_action["action"],
                        "command": "fix_stuck_sessions",
                        "original_status": session.status,
                    },
                    triggered_by="command",
                )

                # Update result counts if needed
                if fix_action["action"] == "complete_processing":
                    result_count = ProcessedResult.objects.filter(
                        session=session
                    ).count()
                    session.total_results = result_count
                    session.save(update_fields=["total_results"])

                return True, ""

            except (InvalidTransition, Exception) as e:
                # Try force transition as fallback
                logger.info(
                    f"Normal transition failed for {session.id}, "
                    f"attempting force transition: {str(e)}"
                )

                try:
                    state_machine.force_transition(
                        session.id,
                        fix_action["target_state"],
                        reason=f"Force fix: {fix_action['reason']}",
                    )
                    return True, ""
                except Exception as force_error:
                    logger.error(f"Force transition also failed: {force_error}")
                    return False, f"Force transition failed: {force_error}"

        except Exception as e:
            logger.error(f"Failed to fix session {session.id}: {str(e)}", exc_info=True)
            return False, str(e)

    def _dry_run_auto_recovery(
        self, recovery_manager: WorkflowRecoveryManager, timeout_minutes: int
    ) -> Dict[str, Any]:
        """
        Perform dry run using WorkflowRecoveryManager.

        Args:
            recovery_manager: Recovery manager instance
            timeout_minutes: Timeout in minutes

        Returns:
            Dry run statistics
        """
        stats = {
            "dry_run": True,
            "sessions_checked": 0,
            "issues_detected": 0,
            "would_recover": [],
            "timestamp": timezone.now().isoformat(),
        }

        # Check each recovery rule
        for status, rules in recovery_manager.RECOVERY_RULES.items():
            stuck_sessions = recovery_manager._find_stuck_sessions(
                status, rules["timeout"]
            )

            stats["sessions_checked"] += len(stuck_sessions)

            for session in stuck_sessions:
                check_method = getattr(recovery_manager, rules["check_method"])
                is_healthy, reason = check_method(session)

                if not is_healthy:
                    stats["issues_detected"] += 1
                    stats["would_recover"].append(
                        {
                            "session_id": str(session.id),
                            "session_title": session.title,
                            "current_status": status,
                            "would_transition_to": rules["recovery_state"],
                            "reason": reason,
                        }
                    )

        return stats

    def _output_report(self, report: Dict[str, Any]) -> None:
        """
        Output formatted report to console.

        Args:
            report: Recovery report dictionary
        """
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("RECOVERY REPORT")
        self.stdout.write("=" * 50)

        self.stdout.write(f"Timestamp: {report['timestamp']}")
        self.stdout.write(f"Total sessions checked: {report['sessions_checked']}")
        self.stdout.write(
            self.style.SUCCESS(f"Sessions recovered: {report['sessions_recovered']}")
        )

        if report["sessions_failed"] > 0:
            self.stdout.write(
                self.style.ERROR(f"Sessions failed: {report['sessions_failed']}")
            )

        if report["by_status"]:
            self.stdout.write("\nBreakdown by status:")
            for status, counts in report["by_status"].items():
                self.stdout.write(
                    f"  {status}: {counts['count']} found, "
                    f"{counts['recovered']} recovered, "
                    f"{counts['failed']} failed"
                )

        if report.get("errors"):
            self.stdout.write("\nErrors encountered:")
            for error in report["errors"]:
                self.stdout.write(
                    self.style.ERROR(
                        f"  Session {error['session_id']}: {error['error']}"
                    )
                )

    def _handle_state_reconciliation(self, dry_run: bool, json_output: bool) -> None:
        """
        Handle state reconciliation for all sessions with potential desynchronization.

        Args:
            dry_run: If True, only show what would be done
            json_output: If True, output in JSON format
        """
        from apps.serp_execution.tasks.monitoring_helpers import (
            reconcile_session_states,
        )

        # Find sessions that might need reconciliation
        potential_sessions = SearchSession.objects.filter(
            status__in=["executing", "processing_results", "ready_for_review"]
        ).exclude(status="archived")

        reconciliation_report = {
            "sessions_checked": 0,
            "sessions_reconciled": 0,
            "changes": [],
            "errors": [],
        }

        for session in potential_sessions:
            reconciliation_report["sessions_checked"] += 1

            if dry_run:
                # Just check, don't actually reconcile
                self.stdout.write(
                    f"Would check session {session.id} (status: {session.status})"
                )
            else:
                result = reconcile_session_states(str(session.id))

                if result["reconciled"]:
                    reconciliation_report["sessions_reconciled"] += 1
                    reconciliation_report["changes"].append(
                        {"session_id": str(session.id), "changes": result["changes"]}
                    )

                    if not json_output:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Reconciled session {session.id}: {', '.join(result['changes'])}"
                            )
                        )

                if result["errors"]:
                    reconciliation_report["errors"].append(
                        {"session_id": str(session.id), "errors": result["errors"]}
                    )

                    if not json_output:
                        for error in result["errors"]:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"Error for session {session.id}: {error}"
                                )
                            )

        # Output final report
        if json_output:
            self.stdout.write(json.dumps(reconciliation_report, indent=2))
        else:
            self.stdout.write("\n" + "=" * 50)
            self.stdout.write("STATE RECONCILIATION REPORT")
            self.stdout.write("=" * 50)
            self.stdout.write(
                f"Sessions checked: {reconciliation_report['sessions_checked']}"
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sessions reconciled: {reconciliation_report['sessions_reconciled']}"
                )
            )

            if reconciliation_report["errors"]:
                self.stdout.write(
                    self.style.ERROR(
                        f"Sessions with errors: {len(reconciliation_report['errors'])}"
                    )
                )

    def _output_recovery_stats(self, stats: Dict[str, Any]) -> None:
        """
        Output WorkflowRecoveryManager stats to console.

        Args:
            stats: Recovery statistics
        """
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("WORKFLOW RECOVERY STATS")
        self.stdout.write("=" * 50)

        self.stdout.write(f"Timestamp: {stats.get('timestamp', 'N/A')}")
        self.stdout.write(f"Sessions checked: {stats.get('sessions_checked', 0)}")
        self.stdout.write(f"Issues detected: {stats.get('issues_detected', 0)}")

        if not stats.get("dry_run"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Recoveries succeeded: {stats.get('recoveries_succeeded', 0)}"
                )
            )
            if stats.get("recoveries_failed", 0) > 0:
                self.stdout.write(
                    self.style.ERROR(
                        f"Recoveries failed: {stats.get('recoveries_failed', 0)}"
                    )
                )

        if stats.get("details") or stats.get("would_recover"):
            details = stats.get("details", stats.get("would_recover", []))
            self.stdout.write(f"\nProcessed {len(details)} session(s):")
            for detail in details[:10]:  # Show first 10
                if stats.get("dry_run"):
                    self.stdout.write(
                        f"  - Would fix: {detail['session_title']} "
                        f"({detail['current_status']} -> {detail['would_transition_to']})"
                    )
                else:
                    status = "✓" if detail.get("recovery_success") else "✗"
                    self.stdout.write(
                        f"  {status} {detail['session_title']}: {detail.get('details', 'N/A')}"
                    )
