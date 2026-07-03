"""
Forms for the SERP execution module.
Handles error recovery.
"""

from django import forms
from django.core.exceptions import ValidationError


class ErrorRecoveryForm(forms.Form):
    """
    Form for handling failed execution recovery.
    Provides options for retry, skip, or manual intervention.
    """

    RECOVERY_CHOICES = [
        ("retry", "Retry Execution"),
        ("skip", "Skip and Continue"),
        ("manual", "Manual Intervention Required"),
    ]

    recovery_action = forms.ChoiceField(
        choices=RECOVERY_CHOICES,
        widget=forms.RadioSelect,
        label="Recovery Action",
        help_text="Choose how to handle this failed execution",
    )

    retry_delay = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=3600,
        initial=60,
        label="Retry Delay (seconds)",
        help_text="Time to wait before retrying (only for retry action)",
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Notes",
        help_text=" notes about this recovery action",
    )

    def __init__(self, *args, **kwargs):
        self.execution = kwargs.pop("execution", None)
        super().__init__(*args, **kwargs)

        # Add Bootstrap classes
        self.fields["recovery_action"].widget.attrs["class"] = "form-check-input"
        self.fields["retry_delay"].widget.attrs["class"] = "form-control"
        self.fields["notes"].widget.attrs["class"] = "form-control"

        # Disable retry if max attempts reached
        if self.execution and not self.execution.can_retry():
            self.fields["recovery_action"].choices = [
                choice for choice in self.RECOVERY_CHOICES if choice[0] != "retry"
            ]

    def clean_retry_delay(self):
        """Validate retry delay if retry action is selected."""
        retry_delay = self.cleaned_data.get("retry_delay")
        recovery_action = self.cleaned_data.get("recovery_action")

        if recovery_action == "retry" and not retry_delay:
            raise ValidationError("Retry delay is required when retrying.")

        return retry_delay

    def clean(self):
        """Additional validation based on execution state."""
        cleaned_data = super().clean()
        recovery_action = cleaned_data.get("recovery_action")

        if self.execution and recovery_action == "retry":
            if not self.execution.can_retry():
                raise ValidationError(
                    "This execution cannot be retried. Maximum attempts reached."
                )

        return cleaned_data


class BulkRetryForm(forms.Form):
    """
    Form for retrying multiple failed executions at once.
    """

    execution_ids = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        label="Select Executions to Retry",
        help_text="Choose which failed executions to retry",
    )

    retry_strategy = forms.ChoiceField(
        choices=[
            ("immediate", "Retry Immediately"),
            ("staggered", "Staggered Retry (5 min intervals)"),
            ("exponential", "Exponential Backoff"),
        ],
        initial="staggered",
        label="Retry Strategy",
        help_text="How to schedule the retries",
    )

    def __init__(self, *args, failed_executions=None, **kwargs):
        super().__init__(*args, **kwargs)

        if failed_executions:
            # Build choices from failed executions
            choices = [
                (
                    str(exec.id),
                    f"{exec.query.query_string[:50]}... - {exec.error_message[:30]}...",
                )
                for exec in failed_executions
                if exec.can_retry()
            ]
            self.fields["execution_ids"].choices = choices

        # Add Bootstrap classes
        self.fields["execution_ids"].widget.attrs["class"] = "form-check-input"
        self.fields["retry_strategy"].widget.attrs["class"] = "form-select"
