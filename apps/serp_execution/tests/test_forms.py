"""
Tests for SERP execution forms.

Tests for ErrorRecoveryForm.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.forms import ErrorRecoveryForm
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestErrorRecoveryForm(TestCase):
    """Test cases for ErrorRecoveryForm."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers"],
            interest_terms=["testing"],
            context_terms=["python"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
        )
        self.execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="failed",
            error_message="Rate limit exceeded",
            retry_count=0,
        )

    def test_form_valid_retry(self):
        """Test form with valid retry action."""
        form_data = {
            "recovery_action": "retry",
            "retry_delay": 60,
            "notes": "Retrying after rate limit",
        }

        form = ErrorRecoveryForm(data=form_data, execution=self.execution)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["recovery_action"], "retry")
        self.assertEqual(form.cleaned_data["retry_delay"], 60)

    def test_form_valid_skip(self):
        """Test form with skip action."""
        form_data = {"recovery_action": "skip", "notes": "Skipping problematic query"}

        form = ErrorRecoveryForm(data=form_data, execution=self.execution)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["recovery_action"], "skip")

    def test_form_valid_manual(self):
        """Test form with manual intervention action."""
        form_data = {
            "recovery_action": "manual",
            "notes": "Need to check API credentials",
        }

        form = ErrorRecoveryForm(data=form_data, execution=self.execution)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["recovery_action"], "manual")

    def test_form_retry_requires_delay(self):
        """Test retry action requires delay when specified."""
        form_data = {
            "recovery_action": "retry",
            "retry_delay": 0,  # Invalid delay
            "notes": "Test",
        }

        form = ErrorRecoveryForm(data=form_data, execution=self.execution)
        self.assertFalse(form.is_valid())
        self.assertIn("retry_delay", form.errors)

    def test_form_removes_retry_when_max_retries_exceeded(self):
        """Test form removes retry choice when max retries exceeded."""
        self.execution.retry_count = 3  # Max retries
        self.execution.save()

        form = ErrorRecoveryForm(execution=self.execution)
        choice_values = [c[0] for c in form.fields["recovery_action"].choices]
        self.assertNotIn("retry", choice_values)
        self.assertIn("skip", choice_values)
        self.assertIn("manual", choice_values)

    def test_form_delay_field_configuration(self):
        """Test retry delay field configuration."""
        form = ErrorRecoveryForm(execution=self.execution)
        delay_field = form.fields["retry_delay"]

        # IntegerField with min/max validation
        self.assertEqual(delay_field.min_value, 0)
        self.assertEqual(delay_field.max_value, 3600)
        self.assertEqual(delay_field.initial, 60)

    def test_form_notes_field(self):
        """Test notes field configuration."""
        form = ErrorRecoveryForm(execution=self.execution)
        notes_field = form.fields["notes"]

        self.assertFalse(notes_field.required)
        self.assertIsInstance(notes_field.widget.attrs.get("rows"), int)
        self.assertIn("form-control", notes_field.widget.attrs.get("class", ""))

    def test_form_action_field_help_text(self):
        """Test recovery action field has appropriate help text."""
        form = ErrorRecoveryForm(execution=self.execution)
        action_field = form.fields["recovery_action"]

        # Check each choice has descriptive help
        for choice_value, choice_label in action_field.choices:
            if choice_value == "retry":
                self.assertIn("Retry", choice_label)
            elif choice_value == "skip":
                self.assertIn("Skip", choice_label)
            elif choice_value == "manual":
                self.assertIn("Manual", choice_label)

    def test_form_removes_retry_for_non_failed_execution(self):
        """Test form removes retry for non-failed executions."""
        self.execution.status = "completed"
        self.execution.save()

        form = ErrorRecoveryForm(execution=self.execution)
        choice_values = [c[0] for c in form.fields["recovery_action"].choices]
        # Retry should not be available for completed executions
        self.assertNotIn("retry", choice_values)
