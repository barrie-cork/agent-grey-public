"""
Management command to recover sessions stuck in ready_to_execute state.
This handles cases where automatic execution trigger failed due to cache/Redis issues.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.review_manager.models import SearchSession, SessionActivity

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Recover sessions stuck in ready_to_execute state due to failed automatic triggers"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--max-age-hours",
            type=int,
            default=1,
            help="Only recover sessions stuck for more than N hours (default: 1)",
        )
        parser.add_argument(
            "--session-id",
            type=str,
            help="Recover a specific session by ID",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force recovery even if session is recently stuck",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        max_age_hours = options["max_age_hours"]
        specific_session = options["session_id"]
        force = options["force"]

        self.stdout.write(self.style.SUCCESS("🔧 Starting stuck session recovery..."))

        try:
            if specific_session:
                # Recover specific session
                sessions = SearchSession.objects.filter(id=specific_session)
                if not sessions.exists():
                    self.stdout.write(
                        self.style.ERROR(f"❌ Session {specific_session} not found!")
                    )
                    return
            else:
                # Find stuck sessions
                cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
                sessions = SearchSession.objects.filter(
                    status="ready_to_execute",
                    updated_at__lt=cutoff_time if not force else timezone.now(),
                ).order_by("updated_at")

            session_count = sessions.count()

            if session_count == 0:
                self.stdout.write(
                    self.style.WARNING("📋 No stuck sessions found matching criteria")
                )
                return

            self.stdout.write(f"📊 Found {session_count} stuck session(s)")

            if dry_run:
                self._show_planned_recoveries(sessions)
                return

            # Execute recoveries
            self._recover_sessions(sessions, force)

        except Exception as e:
            logger.error(f"Session recovery failed: {str(e)}")
            self.stdout.write(self.style.ERROR(f"❌ Recovery failed: {str(e)}"))
            raise

    def _show_planned_recoveries(self, sessions):
        """Show what would be recovered in dry run mode."""
        self.stdout.write(self.style.WARNING("🔍 DRY RUN - Planned recoveries:"))

        for session in sessions:
            age_hours = (timezone.now() - session.updated_at).total_seconds() / 3600

            # Check for execution failures
            has_failures = SessionActivity.objects.filter(
                session=session,
                activity_type__in=["execution_failure", "fallback_execution"],
            ).exists()

            self.stdout.write(
                f"  🔄 Session {session.id} "
                f"(stuck for {age_hours:.1f}h, failures: {has_failures})"
            )
            self.stdout.write(
                f"     Owner: {session.owner.username if session.owner else 'anonymous'}"
            )
            self.stdout.write(f"     Updated: {session.updated_at}")

    def _recover_sessions(self, sessions, force):
        """Execute session recovery."""
        recovered = 0
        failed = 0

        for session in sessions:
            try:
                success = self._recover_single_session(session, force)
                if success:
                    recovered += 1
                    self.stdout.write(f"  ✅ Recovered session {session.id}")
                else:
                    failed += 1
                    self.stdout.write(f"  ❌ Failed to recover session {session.id}")
            except Exception as e:
                failed += 1
                logger.error(f"Failed to recover session {session.id}: {e}")
                self.stdout.write(
                    f"  ❌ Exception recovering session {session.id}: {e}"
                )

        # Summary
        total = recovered + failed
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"📊 Recovery completed: {recovered}/{total} sessions recovered"
            )
        )

        if failed > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠️  {failed} session(s) could not be recovered")
            )

    def _recover_single_session(self, session, force):
        """Recover a single stuck session."""
        try:
            with transaction.atomic():
                # Check if already being processed
                if not force and session.status != "ready_to_execute":
                    logger.info(
                        f"Session {session.id} status changed to {session.status}, skipping recovery"
                    )
                    return True

                # Log recovery attempt
                SessionActivity.log_activity(
                    session=session,
                    activity_type="manual_recovery",
                    description="Manual recovery initiated for stuck ready_to_execute session",
                    user=session.owner,
                    metadata={
                        "recovery_command": True,
                        "original_status": session.status,
                        "stuck_duration_hours": (
                            timezone.now() - session.updated_at
                        ).total_seconds()
                        / 3600,
                        "forced": force,
                    },
                )

                # Try to trigger execution directly
                success = self._trigger_execution_recovery(session)

                if success:
                    # Log successful recovery
                    SessionActivity.log_activity(
                        session=session,
                        activity_type="recovery_success",
                        description="Manual recovery successfully triggered execution",
                        user=session.owner,
                        metadata={"recovery_command": True},
                    )
                    return True
                else:
                    # Log failed recovery
                    SessionActivity.log_activity(
                        session=session,
                        activity_type="recovery_failure",
                        description="Manual recovery failed to trigger execution",
                        user=session.owner,
                        metadata={"recovery_command": True},
                    )
                    return False

        except Exception as e:
            logger.error(f"Error in single session recovery {session.id}: {e}")
            return False

    def _trigger_execution_recovery(self, session):
        """Trigger execution using multiple fallback methods."""
        session_id_str = str(session.id)

        # Method 1: Direct task trigger (bypass state manager)
        try:
            from apps.serp_execution.tasks import initiate_search_session_execution_task

            task = initiate_search_session_execution_task.delay(session_id_str)

            logger.info(
                f"Recovery: Direct execution triggered for session {session_id_str}. "
                f"Task ID: {task.id if hasattr(task, 'id') else 'unknown'}"
            )

            SessionActivity.log_activity(
                session=session,
                activity_type="direct_execution_recovery",
                description="Direct execution task triggered during recovery",
                user=session.owner,
                metadata={
                    "task_id": task.id if hasattr(task, "id") else None,
                    "method": "direct_task_trigger",
                    "recovery_command": True,
                },
            )

            return True

        except Exception as e:
            logger.error(
                f"Direct task trigger failed for session {session_id_str}: {e}"
            )

        # Method 2: State transition recovery
        try:
            # Try to transition back to defining_search then to ready_to_execute
            # This will trigger the automatic execution again
            from apps.review_manager.services.state_manager import SessionStateManager

            state_manager = SessionStateManager(session)

            # First, transition back to defining_search
            success1 = state_manager._legacy_transition_to(
                "defining_search",
                {"recovery_reason": "stuck_ready_to_execute", "recovery_command": True},
            )

            if success1:
                # Refresh session
                session.refresh_from_db()

                # Then transition back to ready_to_execute (which should trigger execution)
                success2 = state_manager._legacy_transition_to(
                    "ready_to_execute",
                    {
                        "recovery_reason": "retrigger_execution",
                        "recovery_command": True,
                    },
                )

                if success2:
                    logger.info(
                        f"Recovery: State transition method succeeded for session {session_id_str}"
                    )
                    return True

        except Exception as e:
            logger.error(
                f"State transition recovery failed for session {session_id_str}: {e}"
            )

        # Method 3: Force status change to executing (last resort)
        try:
            session.status = "executing"
            session.started_at = timezone.now()
            session.save(update_fields=["status", "started_at", "updated_at"])

            logger.warning(
                f"Recovery: Forced status change to executing for session {session_id_str}"
            )

            SessionActivity.log_activity(
                session=session,
                activity_type="forced_status_recovery",
                description="Forced status change to executing as recovery method",
                user=session.owner,
                metadata={
                    "method": "forced_status_change",
                    "recovery_command": True,
                    "warning": "May need manual monitoring",
                },
            )

            # Try to trigger the task anyway
            from apps.serp_execution.tasks import initiate_search_session_execution_task

            task = initiate_search_session_execution_task.delay(session_id_str)

            return True

        except Exception as e:
            logger.error(
                f"Forced status recovery also failed for session {session_id_str}: {e}"
            )

        return False
