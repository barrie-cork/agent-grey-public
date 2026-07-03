"""
Management command to test SERP execution workflow integration.
Creates a test session with search strategy and transitions it through the workflow.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery
from apps.search_strategy.signals import mark_strategy_complete

User = get_user_model()


class Command(BaseCommand):
    help = "Test SERP execution workflow integration"

    def handle(self, *args, **options):
        """Execute the test command."""
        self.stdout.write(
            self.style.NOTICE("Testing SERP execution workflow integration...\n")
        )

        # Get or create test user
        user, created = User.objects.get_or_create(
            username="test_serp_user",
            defaults={"email": "test_serp@example.com", "is_active": True},
        )
        if created:
            user.set_password("testpass123")
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created test user: {user.username}"))
        else:
            self.stdout.write(f"Using existing test user: {user.username}")

        # Create a test session
        session = SearchSession.objects.create(
            title="Test SERP Integration Session",
            description="Testing the workflow integration between search strategy and SERP execution",
            owner=user,
            status="draft",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCreated test session: {session.title} (ID: {session.id})"
            )
        )
        self.stdout.write(f"Initial status: {session.get_status_display()}")

        # Create search queries
        query1 = SearchQuery.objects.create(
            session=session,
            population="healthcare workers",
            interest="burnout prevention programs",
            context="hospital settings",
            max_results=50,
            is_active=True,
        )
        self.stdout.write(f"\nCreated query 1: {query1.query_string}")

        query2 = SearchQuery.objects.create(
            session=session,
            population="nurses",
            interest="mental health interventions",
            context="COVID-19 pandemic",
            max_results=50,
            is_active=True,
        )
        self.stdout.write(f"Created query 2: {query2.query_string}")

        # Check if status auto-transitioned
        session.refresh_from_db()
        self.stdout.write(
            f"\nStatus after adding queries: {session.get_status_display()}"
        )

        # If not auto-transitioned, manually mark complete
        if session.status != "ready_to_execute":
            self.stdout.write("\nManually marking strategy as complete...")
            success, error = mark_strategy_complete(session)

            if success:
                session.refresh_from_db()
                self.stdout.write(self.style.SUCCESS("Strategy marked complete!"))
                self.stdout.write(f"New status: {session.get_status_display()}")
            else:
                self.stdout.write(self.style.ERROR(f"Failed to mark complete: {error}"))
                return

        # Display workflow information
        self.stdout.write(
            self.style.NOTICE("\n=== Workflow Integration Test Complete ===")
        )
        self.stdout.write(f"\nSession: {session.title}")
        self.stdout.write(f"Status: {session.get_status_display()}")
        self.stdout.write(f"Total queries: {session.total_queries}")
        self.stdout.write(
            f"Allowed transitions: {', '.join(session.get_allowed_transitions())}"
        )

        # Display URLs
        self.stdout.write(self.style.NOTICE("\nURLs for testing:"))
        self.stdout.write(
            f"Session detail: http://localhost:8000/review/session/{session.id}/"
        )
        self.stdout.write(
            f"Execute search: http://localhost:8000/review/session/{session.id}/execute/"
        )
        self.stdout.write(
            f"Execution status: http://localhost:8000/review/session/{session.id}/execution/status/"
        )

        self.stdout.write(self.style.SUCCESS("\nWorkflow integration test complete!"))
