"""
Tests for review_results views with workflow detection.

Phase 04: Django Template Multi-Reviewer Mode
Tests that templates correctly detect and render workflow-specific UI.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organisation.models import Organisation
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.results_manager.models import ProcessedResult
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ResultsOverviewTemplateTest(TestCase):
    """Test results_overview.html template workflow detection."""

    def setUp(self):
        """Create test data."""
        self.user = create_test_user()
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Workflow #1 session (single reviewer)
        self.session_workflow1 = SearchSession.objects.create(
            title="Workflow 1 Session",
            owner=self.user,
            organisation=self.org,
            status="under_review",
        )
        self.config_workflow1 = ReviewConfiguration.objects.create(
            session=self.session_workflow1,
            min_reviewers_per_result=1,
            created_by=self.user,
            organisation=self.org,
        )
        self.session_workflow1.current_configuration = self.config_workflow1
        self.session_workflow1.save()

        # Workflow #2 session (dual screening)
        self.session_workflow2 = SearchSession.objects.create(
            title="Workflow 2 Session",
            owner=self.user,
            organisation=self.org,
            status="under_review",
        )
        self.config_workflow2 = ReviewConfiguration.objects.create(
            session=self.session_workflow2,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            created_by=self.user,
            organisation=self.org,
        )
        self.session_workflow2.current_configuration = self.config_workflow2
        self.session_workflow2.save()

        # Add some results
        for i in range(3):
            ProcessedResult.objects.create(
                session=self.session_workflow1,
                title=f"Result {i + 1}",
                url=f"http://example.com/{i + 1}",
                processing_status="unique",
            )
            ProcessedResult.objects.create(
                session=self.session_workflow2,
                title=f"Result {i + 1}",
                url=f"http://example.com/{i + 1}",
                processing_status="unique",
            )

        self.client = Client()
        self.client.login(username=self.user.username, password="testpass123")

    def test_workflow1_template_renders(self):
        """Test Workflow #1 template renders correctly (single reviewer)."""
        url = reverse("review_results:overview", args=[self.session_workflow1.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "review_results/results_overview.html")

        # Should NOT show blinding indicator
        self.assertNotContains(response, 'data-testid="blinding-indicator"')

        # Should show standard Complete Review button
        self.assertContains(response, 'data-testid="complete-review-btn"')

    def test_workflow2_template_renders(self):
        """Test Workflow #2 template renders correctly (dual screening)."""
        # After dual-screening refactoring, the Django template fully supports both workflows.
        # No redirection needed - the template handles both cases appropriately.
        url = reverse("review_results:overview", args=[self.session_workflow2.id])
        response = self.client.get(url)

        # Should render the template (no redirect)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "review_results/results_overview.html")

    def test_workflow2_blinding_indicator_shows_with_no_results(self):
        """Test blinding indicator shows in Workflow #2 when no results exist."""
        # Remove results to bypass redirect
        ProcessedResult.objects.filter(session=self.session_workflow2).delete()

        url = reverse("review_results:overview", args=[self.session_workflow2.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "review_results/results_overview.html")

        # Should show blinding indicator
        self.assertContains(response, 'data-testid="blinding-indicator"')
        self.assertContains(response, "Blinded PRISMA Mode")
        self.assertContains(response, "Active")

        # Should show Mark My Review Complete button
        self.assertContains(response, 'data-testid="mark-complete-button"')

    def test_workflow_detection_logic_present(self):
        """Test that workflow detection logic is present in template."""
        # Remove results to bypass redirect
        ProcessedResult.objects.filter(session=self.session_workflow2).delete()

        url = reverse("review_results:overview", args=[self.session_workflow2.id])
        response = self.client.get(url)

        # Check that workflow 2-specific content is rendered (Kappa widget)
        content = response.content.decode("utf-8")
        self.assertIn("kappa-widget", content)

    def test_reviewer_completion_context_data(self):
        """Test that ReviewerCompletion data is passed to template context."""
        from apps.review_manager.models import ReviewInvitation
        from apps.review_results.models import ReviewerDecision
        import secrets

        # Remove any existing results and create exactly 10 reviewable results
        ProcessedResult.objects.filter(session=self.session_workflow2).delete()
        results = [
            ProcessedResult(
                session=self.session_workflow2,
                title=f"Result {i}",
                url=f"https://example.com/{i}",
                processing_status="success",
                is_hidden=False,
            )
            for i in range(10)
        ]
        ProcessedResult.objects.bulk_create(results)

        # Create invitation and ReviewerCompletion (auto-created by signal)
        ReviewInvitation.objects.create(
            session=self.session_workflow2,
            inviter=self.user,
            invitee=self.user,
            invitee_email=self.user.email,
            token=secrets.token_urlsafe(32),
            status="ACCEPTED",
        )

        # Create 5 ReviewerDecision records (live sync will count these)
        for result in results[:5]:
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.user,
                decision="INCLUDE",
                organisation=self.org,
            )

        url = reverse("review_results:overview", args=[self.session_workflow2.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check context data
        self.assertIn("user_completion", response.context)
        self.assertIn("all_completions", response.context)

        # Verify user_completion data (live-synced from DB)
        user_completion = response.context["user_completion"]
        self.assertIsNotNone(user_completion)
        self.assertEqual(user_completion.total_results, 10)
        self.assertEqual(user_completion.reviewed_results, 5)
