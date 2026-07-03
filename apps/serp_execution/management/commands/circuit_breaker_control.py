"""
Management command for circuit breaker control and monitoring.

Provides manual control and testing capabilities for circuit breakers.
"""

import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.services.circuit_breaker import (
    DynamicCircuitBreaker,
    get_circuit_breaker_status,
    reset_all_circuit_breakers,
    serper_circuit_breaker,
)


class Command(BaseCommand):
    """
    Control and monitor circuit breakers.

    Available actions:
    - status: Show current status of all circuit breakers
    - reset: Reset all circuit breakers to closed state
    - reset-one: Reset a specific circuit breaker
    - test: Simulate failures to test circuit breaker
    - stats: Show detailed statistics
    """

    help = "Control and monitor circuit breakers"

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=["status", "reset", "reset-one", "test", "stats"],
            help="Action to perform",
        )

        parser.add_argument(
            "--breaker",
            type=str,
            choices=["serper_api", "database"],
            help="Specific circuit breaker to target",
        )

        parser.add_argument(
            "--failures",
            type=int,
            default=6,
            help="Number of failures to simulate (for test action)",
        )

        parser.add_argument("--json", action="store_true", help="Output in JSON format")

    def handle(self, *args, **options):
        action = options["action"]
        breaker_name = options.get("breaker")
        json_output = options.get("json", False)

        try:
            if action == "status":
                self.show_status(json_output)

            elif action == "reset":
                self.reset_breakers(breaker_name)

            elif action == "reset-one":
                if not breaker_name:
                    raise CommandError("--breaker is required for reset-one action")
                self.reset_one_breaker(breaker_name)

            elif action == "test":
                if not breaker_name:
                    breaker_name = "serper_api"
                self.test_breaker(breaker_name, options["failures"])

            elif action == "stats":
                self.show_statistics(breaker_name, json_output)

        except Exception as e:
            raise CommandError(f"Operation failed: {str(e)}")

    def show_status(self, json_output=False):
        """Show current status of all circuit breakers."""
        status = get_circuit_breaker_status()

        if json_output:
            self.stdout.write(json.dumps(status, indent=2, default=str))
        else:
            self.stdout.write(self.style.SUCCESS("\n=== Circuit Breaker Status ===\n"))
            self.stdout.write(f"Enabled: {status['enabled']}")

            for name, breaker_status in status["breakers"].items():
                self.stdout.write(f"\n{name.upper()}:")
                self._format_breaker_status(breaker_status)

            self.stdout.write("\n=== Configuration ===")
            for name, config in status["configuration"].items():
                self.stdout.write(f"\n{name}:")
                for key, value in config.items():
                    self.stdout.write(f"  {key}: {value}")

    def _format_breaker_status(self, status):
        """Format individual breaker status for display."""
        state = status.get("current_state", "unknown")

        # Color code based on state
        if state == "closed":
            state_display = self.style.SUCCESS(state.upper())
        elif state == "open":
            state_display = self.style.ERROR(state.upper())
        else:
            state_display = self.style.WARNING(state.upper())

        self.stdout.write(f"  State: {state_display}")
        self.stdout.write(f"  Failures: {status.get('failure_count', 0)}")

        if status.get("opened_at"):
            opened_at = timezone.datetime.fromtimestamp(status["opened_at"])
            time_open = timezone.now() - opened_at
            self.stdout.write(f"  Opened At: {opened_at}")
            self.stdout.write(f"  Time Open: {time_open}")

        # Show recent state changes if available
        if status.get("recent_state_changes"):
            self.stdout.write("  Recent Changes:")
            for change in status["recent_state_changes"][:3]:
                timestamp = change.get("timestamp", "Unknown")
                old_state = change.get("old_state", "?")
                new_state = change.get("new_state", "?")
                self.stdout.write(f"    {timestamp}: {old_state} -> {new_state}")

    def reset_breakers(self, breaker_name=None):
        """Reset circuit breakers."""
        if breaker_name:
            DynamicCircuitBreaker.reset_breaker(breaker_name)
            self.stdout.write(
                self.style.SUCCESS(f"Circuit breaker '{breaker_name}' has been reset")
            )
        else:
            reset_all_circuit_breakers()
            self.stdout.write(
                self.style.SUCCESS("All circuit breakers have been reset")
            )

    def reset_one_breaker(self, breaker_name):
        """Reset a specific circuit breaker."""
        DynamicCircuitBreaker.reset_breaker(breaker_name)
        self.stdout.write(
            self.style.SUCCESS(f"Circuit breaker '{breaker_name}' has been reset")
        )

    def test_breaker(self, breaker_name, num_failures):
        """Simulate failures to test circuit breaker."""
        self.stdout.write(f"\nTesting {breaker_name} with {num_failures} failures...")

        if breaker_name == "serper_api":
            breaker = serper_circuit_breaker
        else:
            # For database breaker, we'd need to import it
            self.stdout.write(
                self.style.WARNING("Database breaker testing not implemented")
            )
            return

        # Get initial state
        initial_state = breaker.state.name
        self.stdout.write(f"Initial state: {initial_state}")

        # Simulate failures
        for i in range(num_failures):
            try:
                # This will trigger the circuit breaker's failure counter
                @breaker
                def failing_function():
                    raise Exception(f"Test failure {i + 1}")

                failing_function()
            except Exception:
                pass

            self.stdout.write(f"  Failure {i + 1}/{num_failures} recorded")

        # Check final state
        final_state = breaker.state.name
        self.stdout.write(f"Final state: {final_state}")

        if final_state == "open":
            self.stdout.write(
                self.style.ERROR(
                    f"Circuit breaker is now OPEN after {num_failures} failures"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Circuit breaker is still {final_state} after {num_failures} failures"
                )
            )

    def show_statistics(self, breaker_name=None, json_output=False):
        """Show detailed statistics for circuit breakers."""
        if breaker_name:
            breakers = [breaker_name]
        else:
            breakers = ["serper_api", "database"]

        all_stats = {}

        for name in breakers:
            stats = DynamicCircuitBreaker.get_breaker_status(name)
            all_stats[name] = stats

        if json_output:
            self.stdout.write(json.dumps(all_stats, indent=2, default=str))
        else:
            self.stdout.write(
                self.style.SUCCESS("\n=== Circuit Breaker Statistics ===\n")
            )

            for name, stats in all_stats.items():
                self.stdout.write(f"\n{name.upper()}:")
                self.stdout.write(
                    f"  Current State: {stats.get('current_state', 'unknown')}"
                )
                self.stdout.write(f"  Total Failures: {stats.get('failure_count', 0)}")

                # Show daily failure stats if available
                daily_failures = stats.get("daily_failures", {})
                if daily_failures:
                    self.stdout.write("  Daily Failures:")
                    for date, count in sorted(daily_failures.items())[-7:]:
                        self.stdout.write(f"    {date}: {count}")

                # Show time in open state if applicable
                if stats.get("time_in_open_state"):
                    duration = timedelta(seconds=stats["time_in_open_state"])
                    self.stdout.write(f"  Time in Open State: {duration}")
