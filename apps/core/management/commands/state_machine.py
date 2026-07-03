"""Management command for state machine operations."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.state_machine import state_machine
from apps.core.state_machine.event_store import event_store
from apps.core.state_machine.recovery import recovery_service


class Command(BaseCommand):
    """Manage state machine operations."""

    help = "State machine management commands"

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(
            dest="subcommand", help="Available subcommands"
        )

        # Transition command
        transition_parser = subparsers.add_parser(
            "transition", help="Manually transition a session"
        )
        transition_parser.add_argument("session_id", help="Session UUID")
        transition_parser.add_argument("target_state", help="Target state")
        transition_parser.add_argument(
            "--force", action="store_true", help="Force transition"
        )

        # Recovery command
        recovery_parser = subparsers.add_parser(
            "recover", help="Recover stuck sessions"
        )
        recovery_parser.add_argument(
            "--timeout", type=int, default=30, help="Timeout in minutes (default: 30)"
        )

        # Status command
        status_parser = subparsers.add_parser("status", help="Show session status")
        status_parser.add_argument("session_id", help="Session UUID")

        # Health command
        health_parser = subparsers.add_parser("health", help="Check session health")
        health_parser.add_argument("session_id", help="Session UUID")

        # History command
        history_parser = subparsers.add_parser(
            "history", help="Show session transition history"
        )
        history_parser.add_argument("session_id", help="Session UUID")
        history_parser.add_argument(
            "--limit", type=int, default=10, help="Limit events"
        )

        # Events command
        events_parser = subparsers.add_parser("events", help="Show recent events")
        events_parser.add_argument("--session", help="Filter by session ID")
        events_parser.add_argument("--type", help="Filter by event type")
        events_parser.add_argument("--limit", type=int, default=20, help="Limit events")

        # Test command
        subparsers.add_parser("test", help="Test state machine functionality")

    def handle(self, *args, **options):
        subcommand = options.get("subcommand")

        if subcommand == "transition":
            self.handle_transition(options)
        elif subcommand == "recover":
            self.handle_recovery(options)
        elif subcommand == "status":
            self.handle_status(options)
        elif subcommand == "health":
            self.handle_health(options)
        elif subcommand == "history":
            self.handle_history(options)
        elif subcommand == "events":
            self.handle_events(options)
        elif subcommand == "test":
            self.handle_test()
        else:
            self.print_help("manage.py", "state_machine")

    def handle_transition(self, options):
        """Handle manual transition."""
        session_id = options["session_id"]
        target_state = options["target_state"]
        force = options.get("force", False)

        try:
            if force:
                state_machine.force_transition(
                    session_id,
                    target_state,
                    reason="Manual force transition via command",
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Force transitioned {session_id} to {target_state}"
                    )
                )
            else:
                with transaction.atomic():
                    state_machine.transition(
                        session_id, target_state, triggered_by="manual_command"
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Transitioned {session_id} to {target_state}"
                        )
                    )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Transition failed: {e}"))

    def handle_recovery(self, options):
        """Handle session recovery."""
        timeout = options["timeout"]

        self.stdout.write(f"Recovering sessions older than {timeout} minutes...")
        recovered = recovery_service.recover_stuck_sessions(timeout_minutes=timeout)

        if recovered:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Recovered {len(recovered)} sessions:")
            )
            for session_id in recovered:
                self.stdout.write(f"  - {session_id}")
        else:
            self.stdout.write("No stuck sessions found")

    def handle_status(self, options):
        """Show session status."""
        from apps.review_manager.models import SearchSession

        session_id = options["session_id"]

        try:
            session = SearchSession.objects.get(id=session_id)
            self.stdout.write(f"\nSession: {session.title}")
            self.stdout.write(f"Status: {self.style.WARNING(session.status)}")
            self.stdout.write(f"Created: {session.created_at}")
            self.stdout.write(f"Updated: {session.updated_at}")

            # Show allowed transitions
            current_state = session.status
            state_def = state_machine.registry.get_state(current_state)
            if state_def:
                self.stdout.write("\nAllowed transitions:")
                for next_state in state_def.allowed_transitions:
                    self.stdout.write(f"  → {next_state}")

                if state_def.is_automated:
                    self.stdout.write(
                        self.style.WARNING("\n⚙ This is an automated state")
                    )
                if state_def.is_terminal:
                    self.stdout.write(self.style.ERROR("\n⛔ This is a terminal state"))

        except SearchSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Session {session_id} not found"))

    def handle_health(self, options):
        """Check session health."""
        session_id = options["session_id"]
        health = recovery_service.check_session_health(session_id)

        if health["is_healthy"]:
            self.stdout.write(self.style.SUCCESS(f"✓ Session {session_id} is healthy"))
        else:
            self.stdout.write(self.style.ERROR(f"✗ Session {session_id} has issues"))

        self.stdout.write(f"\nCurrent state: {health.get('current_state', 'Unknown')}")

        if health.get("issues"):
            self.stdout.write("\nIssues:")
            for issue in health["issues"]:
                self.stdout.write(f"  • {issue}")

        if health.get("recommendations"):
            self.stdout.write("\nRecommendations:")
            for rec in health["recommendations"]:
                self.stdout.write(f"  → {rec}")

        if health.get("recent_errors"):
            self.stdout.write(f"\nRecent errors: {health['recent_errors']}")
            self.stdout.write(f"Last error: {health.get('last_error', 'Unknown')}")

    def handle_history(self, options):
        """Show session transition history."""
        session_id = options["session_id"]
        limit = options.get("limit", 10)

        history = state_machine.get_session_history(session_id)

        if not history:
            self.stdout.write("No transition history found")
            return

        # Show only last N events
        if len(history) > limit:
            history = history[-limit:]
            self.stdout.write(f"Showing last {limit} transitions:\n")
        else:
            self.stdout.write(f"Complete history ({len(history)} transitions):\n")

        for event in history:
            timestamp = event.get("timestamp", "Unknown time")
            old_state = event.get("old_state", "Unknown")
            new_state = event.get("new_state", "Unknown")
            triggered_by = event.get("triggered_by", "Unknown")

            self.stdout.write(
                f"{timestamp}: {old_state} → {new_state} (by {triggered_by})"
            )

    def handle_events(self, options):
        """Show recent events."""
        session_id = options.get("session")
        event_type = options.get("type")
        limit = options.get("limit", 20)

        if session_id:
            events = event_store.get_session_events(session_id, event_type, limit)
            self.stdout.write(f"Events for session {session_id}:\n")
        elif event_type:
            events = event_store.get_recent_events(minutes=60, event_type=event_type)
            self.stdout.write(f"Recent {event_type} events:\n")
        else:
            events = []
            self.stdout.write("Please specify --session or --type filter")
            return

        if not events:
            self.stdout.write("No events found")
            return

        for event in events[:limit]:
            event_type = event.get("event_type", "unknown")
            timestamp = event.get("timestamp", "Unknown")
            session = event.get("session_id", "Unknown")

            self.stdout.write(f"{timestamp}: [{event_type}] Session: {session[:8]}...")

            # Show event-specific details
            if event_type == "state_transition":
                self.stdout.write(
                    f"  {event.get('old_state')} → {event.get('new_state')}"
                )
            elif event_type == "error":
                self.stdout.write(
                    f"  {event.get('error_type')}: {event.get('error_message')}"
                )
            elif event_type == "progress_update":
                self.stdout.write(
                    f"  {event.get('component')}: {event.get('progress')}%"
                )
            elif event_type == "recovery":
                self.stdout.write(
                    f"  {event.get('recovery_action')}: {event.get('reason')}"
                )

    def handle_test(self):
        """Test state machine functionality."""
        self.stdout.write("Testing state machine...\n")

        # Test registry
        states = state_machine.registry.get_all_states()
        self.stdout.write(f"✓ Registry has {len(states)} states")
        self.stdout.write(f"  States: {', '.join(sorted(states))}")

        # Test automated states
        automated = state_machine.registry.get_automated_states()
        self.stdout.write(f"\n✓ {len(automated)} automated states")
        self.stdout.write(f"  Automated: {', '.join(automated)}")

        # Test transitions
        self.stdout.write("\n✓ Testing transition matrix:")
        test_transitions = [
            ("draft", "defining_search", True),
            ("draft", "completed", False),
            ("defining_search", "ready_to_execute", True),
            ("executing", "processing_results", True),
            ("completed", "archived", True),
            ("archived", "draft", True),
        ]

        for from_state, to_state, expected in test_transitions:
            result = state_machine.can_transition(from_state, to_state)
            symbol = "✓" if result == expected else "✗"
            status = "allowed" if result else "denied"

            if result == expected:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {symbol} {from_state} → {to_state}: {status}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"  {symbol} {from_state} → {to_state}: expected {expected}, got {result}"
                    )
                )

        # Test event bus
        listener_count = state_machine.event_bus.get_listener_count()
        self.stdout.write(f"\n✓ Event bus has {listener_count} listeners")

        self.stdout.write(self.style.SUCCESS("\n✓ State machine test complete"))
