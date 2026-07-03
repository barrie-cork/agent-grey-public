"""
Tests for feedback forms.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..forms import FeedbackForm, QuickFeedbackForm
from apps.core.tests.utils import create_test_user

User = get_user_model()


class FeedbackFormTest(TestCase):
    """Test FeedbackForm."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

    def test_valid_form_authenticated_user(self):
        """Test valid form with authenticated user."""
        form_data = {
            "feedback_type": "bug",
            "subject": "Test Bug",
            "message": "This is a detailed test bug report with sufficient length to pass validation requirements.",
            "rating": "2",
        }

        form = FeedbackForm(
            data=form_data,
            user=self.user,
            page_path="/test-page/",
            page_title="Test Page",
        )

        self.assertTrue(form.is_valid())

        feedback = form.save()
        self.assertEqual(feedback.user, self.user)
        self.assertEqual(feedback.page_path, "/test-page/")
        self.assertEqual(feedback.page_title, "Test Page")
        self.assertEqual(feedback.email, "")  # Should be empty for authenticated users

    def test_valid_form_anonymous_user(self):
        """Test valid form with anonymous user."""
        form_data = {
            "feedback_type": "suggestion",
            "subject": "Anonymous Suggestion",
            "message": "This is an anonymous suggestion with sufficient length to pass validation requirements.",
            "email": "anonymous@example.com",
        }

        form = FeedbackForm(
            data=form_data, user=None, page_path="/test-page/", page_title="Test Page"
        )

        self.assertTrue(form.is_valid())

        feedback = form.save()
        self.assertIsNone(feedback.user)
        self.assertEqual(feedback.email, "anonymous@example.com")

    def test_message_too_short(self):
        """Test form validation with message too short."""
        form_data = {
            "feedback_type": "bug",
            "message": "Too short",  # Less than 10 characters
        }

        form = FeedbackForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)
        self.assertIn("at least 10 characters", form.errors["message"][0])

    def test_message_too_long(self):
        """Test form validation with message too long."""
        form_data = {
            "feedback_type": "bug",
            "message": "x" * 2001,  # Over 2000 characters
        }

        form = FeedbackForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)
        self.assertIn("under 2000 characters", form.errors["message"][0])

    def test_message_with_multiple_links(self):
        """Test form validation rejects messages with multiple links (spam protection)."""
        form_data = {
            "feedback_type": "bug",
            "message": "Check out http://example.com and http://test.com and http://spam.com for more info. This message has enough length to pass the minimum character requirement.",
        }

        form = FeedbackForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)
        self.assertIn("multiple links", form.errors["message"][0])

    def test_html_stripping(self):
        """Test that HTML tags are stripped from message."""
        form_data = {
            "feedback_type": "bug",
            "subject": '<script>alert("xss")</script>Clean Subject',
            "message": '<p>This is a <b>test</b> message with <script>alert("xss")</script> HTML tags that should be stripped but is long enough to pass validation.</p>',
        }

        form = FeedbackForm(data=form_data, user=self.user)
        self.assertTrue(form.is_valid())

        cleaned_subject = form.cleaned_data["subject"]
        cleaned_message = form.cleaned_data["message"]

        # HTML tags should be stripped
        self.assertNotIn("<script>", cleaned_subject)
        self.assertNotIn("<script>", cleaned_message)
        self.assertNotIn("<p>", cleaned_message)
        self.assertNotIn("<b>", cleaned_message)
        self.assertIn("Clean Subject", cleaned_subject)
        self.assertIn("This is a test message", cleaned_message)

    def test_required_fields(self):
        """Test that required fields are validated."""
        form_data = {}  # Empty form

        form = FeedbackForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())

        # feedback_type and message are required
        self.assertIn("feedback_type", form.errors)
        self.assertIn("message", form.errors)

    def test_email_hidden_for_authenticated_user(self):
        """Test that email field is hidden for authenticated users."""
        form = FeedbackForm(user=self.user)

        # Email field should be hidden input
        email_widget = form.fields["email"].widget
        self.assertEqual(email_widget.__class__.__name__, "HiddenInput")
        self.assertFalse(form.fields["email"].required)

    def test_email_visible_for_anonymous_user(self):
        """Test that email field is visible for anonymous users."""
        form = FeedbackForm(user=None)

        # Email field should be email input
        email_widget = form.fields["email"].widget
        self.assertEqual(email_widget.__class__.__name__, "EmailInput")
        self.assertFalse(form.fields["email"].required)  # Optional but recommended


class QuickFeedbackFormTest(TestCase):
    """Test QuickFeedbackForm."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

    def test_valid_quick_feedback(self):
        """Test valid quick feedback submission."""
        form_data = {
            "feedback_type": "helpful",
            "rating": "5",
            "additional_comment": "This page was very helpful!",
        }

        form = QuickFeedbackForm(
            data=form_data,
            user=self.user,
            page_path="/helpful-page/",
            page_title="Helpful Page",
        )

        self.assertTrue(form.is_valid())

        feedback = form.save()
        self.assertEqual(feedback.feedback_type, "general")  # Mapped from 'helpful'
        self.assertEqual(feedback.rating, 5)
        self.assertEqual(feedback.page_path, "/helpful-page/")
        self.assertIn("This page was helpful", feedback.message)
        self.assertIn("This page was very helpful!", feedback.message)

    def test_quick_feedback_without_comment(self):
        """Test quick feedback without additional comment."""
        form_data = {"feedback_type": "not_helpful", "rating": "2"}

        form = QuickFeedbackForm(
            data=form_data,
            user=self.user,
            page_path="/test-page/",
            page_title="Test Page",
        )

        self.assertTrue(form.is_valid())

        feedback = form.save()
        self.assertEqual(
            feedback.feedback_type, "suggestion"
        )  # Mapped from 'not_helpful'
        self.assertEqual(feedback.rating, 2)
        self.assertEqual(feedback.message, "This page was not helpful.")

    def test_quick_feedback_type_mapping(self):
        """Test that quick feedback types are correctly mapped."""
        mappings = [
            ("helpful", "general"),
            ("not_helpful", "suggestion"),
            ("confusing", "suggestion"),
            ("missing_info", "suggestion"),
        ]

        for quick_type, expected_type in mappings:
            with self.subTest(quick_type=quick_type):
                form_data = {"feedback_type": quick_type, "rating": "3"}

                form = QuickFeedbackForm(
                    data=form_data,
                    user=self.user,
                    page_path="/test-page/",
                    page_title="Test Page",
                )

                self.assertTrue(form.is_valid())
                feedback = form.save()
                self.assertEqual(feedback.feedback_type, expected_type)

                # Clean up for next iteration
                feedback.delete()
