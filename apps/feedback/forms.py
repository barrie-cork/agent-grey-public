"""
Forms for user feedback submission.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import strip_tags

from .models import UserFeedback


class FeedbackForm(forms.ModelForm):
    """
    Form for submitting user feedback.

    Handles both authenticated and anonymous feedback submissions
    with proper validation and sanitization.
    """

    class Meta:
        model = UserFeedback
        fields = ["feedback_type", "subject", "message", "rating", "email"]
        widgets = {
            "feedback_type": forms.Select(
                attrs={"class": "form-select", "required": True}
            ),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Brief summary of your feedback (optional)",
                    "maxlength": 200,
                }
            ),
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Please provide detailed feedback...",
                    "rows": 4,
                    "required": True,
                }
            ),
            "rating": forms.Select(attrs={"class": "form-select"}),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "your.email@example.com (optional)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        # Extract user from kwargs if provided
        self.user = kwargs.pop("user", None)
        self.page_path = kwargs.pop("page_path", "")
        self.page_title = kwargs.pop("page_title", "")
        super().__init__(*args, **kwargs)

        # If user is authenticated, hide email field
        if self.user and self.user.is_authenticated:
            self.fields["email"].widget = forms.HiddenInput()
            self.fields["email"].required = False
        else:
            # For anonymous users, make email optional but recommended
            self.fields[
                "email"
            ].help_text = "Optional - provide if you'd like a response"

    def clean_message(self):
        """Clean and validate the message field."""
        message = self.cleaned_data.get("message", "")

        # Strip HTML tags for security
        message = strip_tags(message).strip()

        # Minimum length validation
        if len(message) < 10:
            raise ValidationError(
                "Please provide more detailed feedback (at least 10 characters)."
            )

        # Maximum length validation
        if len(message) > 2000:
            raise ValidationError(
                "Feedback message is too long. Please keep it under 2000 characters."
            )

        # Check for spam-like patterns
        if message.lower().count("http") > 2:
            raise ValidationError("Feedback cannot contain multiple links.")

        return message

    def clean_subject(self):
        """Clean and validate the subject field."""
        subject = self.cleaned_data.get("subject", "")
        if subject:
            subject = strip_tags(subject).strip()
        return subject

    def clean_email(self):
        """Clean and validate email for anonymous users."""
        email = self.cleaned_data.get("email", "")

        # If user is authenticated, ignore email field
        if self.user and self.user.is_authenticated:
            return ""

        return email

    def save(self, commit=True):
        """Save the feedback with additional context."""
        feedback = super().save(commit=False)

        # Set user if authenticated
        if self.user and self.user.is_authenticated:
            feedback.user = self.user
            feedback.email = ""  # Clear email for authenticated users

        # Set page context
        feedback.page_path = self.page_path
        feedback.page_title = self.page_title

        if commit:
            feedback.save()

        return feedback


class QuickFeedbackForm(forms.Form):
    """
    Simplified form for quick feedback submission.

    Used for simple thumbs up/down or star ratings
    without requiring detailed messages.
    """

    QUICK_TYPES = [
        ("helpful", "This page was helpful"),
        ("not_helpful", "This page was not helpful"),
        ("confusing", "This page was confusing"),
        ("missing_info", "Missing information"),
    ]

    feedback_type = forms.ChoiceField(
        choices=QUICK_TYPES, widget=forms.HiddenInput(), required=True
    )

    rating = forms.ChoiceField(
        choices=UserFeedback.RATING_CHOICES,
        required=False,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )

    additional_comment = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Any additional comments? (optional)",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        self.page_path = kwargs.pop("page_path", "")
        self.page_title = kwargs.pop("page_title", "")
        super().__init__(*args, **kwargs)

    def save(self):
        """Convert quick feedback to UserFeedback model."""
        feedback_type_map = {
            "helpful": "general",
            "not_helpful": "suggestion",
            "confusing": "suggestion",
            "missing_info": "suggestion",
        }

        quick_type = self.cleaned_data["feedback_type"]
        rating = self.cleaned_data.get("rating")
        comment = self.cleaned_data.get("additional_comment", "")

        # Generate message based on quick type
        messages = {
            "helpful": "This page was helpful.",
            "not_helpful": "This page was not helpful.",
            "confusing": "This page was confusing.",
            "missing_info": "This page was missing important information.",
        }

        message = messages[quick_type]
        if comment:
            message += f" Additional feedback: {comment}"

        feedback = UserFeedback(
            user=self.user if self.user and self.user.is_authenticated else None,
            page_path=self.page_path,
            page_title=self.page_title,
            feedback_type=feedback_type_map[quick_type],
            subject=f"Quick feedback: {dict(self.QUICK_TYPES)[quick_type]}",
            message=message,
            rating=int(rating) if rating else None,
        )

        feedback.save()
        return feedback
