"""Tests for BaseEmailNotificationService shared email infrastructure."""

import smtplib
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.core.services.base_email_service import BaseEmailNotificationService


class ConcreteEmailService(BaseEmailNotificationService):
    """Concrete subclass for testing the abstract base."""

    SERVICE_NAME = "TestEmailService"
    SERVICE_VERSION = "1.0.0"


class BaseEmailNotificationServiceTests(TestCase):
    """Tests for shared email notification infrastructure."""

    def setUp(self):
        self.service = ConcreteEmailService()

    def test_initialize_is_noop(self):
        """_initialize should complete without error."""
        self.service._initialize()

    def test_get_default_config_returns_expected_keys(self):
        config = self.service.get_default_config()
        self.assertIn("cache_timeout", config)
        self.assertIn("send_email", config)
        self.assertIn("from_email", config)
        self.assertIn("site_domain", config)
        self.assertIn("use_https", config)
        self.assertEqual(config["cache_timeout"], 300)
        self.assertTrue(config["send_email"])

    def test_get_base_url_http(self):
        self.service.config = {"use_https": False, "site_domain": "example.com"}
        self.assertEqual(self.service._get_base_url(), "http://example.com")

    def test_get_base_url_https(self):
        self.service.config = {"use_https": True, "site_domain": "example.com"}
        self.assertEqual(self.service._get_base_url(), "https://example.com")

    def test_get_base_url_defaults(self):
        self.service.config = {}
        self.assertEqual(self.service._get_base_url(), "http://localhost:8000")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    @patch("apps.core.services.base_email_service.EmailMultiAlternatives")
    @patch("apps.core.services.base_email_service.render_to_string")
    def test_send_email_success(self, mock_render, mock_email_class):
        mock_render.return_value = "<html>Test</html>"
        mock_email = MagicMock()
        mock_email_class.return_value = mock_email

        result = self.service._send_email(
            subject="Test Subject",
            html_template="emails/test.html",
            context={"key": "value"},
            recipient_list=["test@example.com"],
        )

        self.assertTrue(result)
        mock_email.send.assert_called_once_with(fail_silently=False)
        mock_email.attach_alternative.assert_called_once()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    @patch("apps.core.services.base_email_service.EmailMultiAlternatives")
    @patch("apps.core.services.base_email_service.render_to_string")
    def test_send_email_adds_base_context(self, mock_render, mock_email_class):
        mock_render.return_value = "<html>Test</html>"
        mock_email_class.return_value = MagicMock()

        context = {"key": "value"}
        self.service._send_email(
            subject="Test",
            html_template="emails/test.html",
            context=context,
            recipient_list=["test@example.com"],
        )

        # Caller's context should NOT be mutated
        self.assertNotIn("site_name", context)
        self.assertNotIn("preferences_url", context)

        # Base context should have been passed to render_to_string
        rendered_context = mock_render.call_args_list[0][0][1]
        self.assertEqual(rendered_context["site_name"], "Agent Grey")
        self.assertIn("preferences_url", rendered_context)
        self.assertEqual(rendered_context["key"], "value")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    @patch("apps.core.services.base_email_service.EmailMultiAlternatives")
    @patch("apps.core.services.base_email_service.render_to_string")
    def test_send_email_tries_text_template(self, mock_render, mock_email_class):
        mock_render.return_value = "<html>Test</html>"
        mock_email_class.return_value = MagicMock()

        self.service._send_email(
            subject="Test",
            html_template="emails/test.html",
            context={},
            recipient_list=["test@example.com"],
        )

        # Should try both HTML and TXT templates
        render_calls = [call[0][0] for call in mock_render.call_args_list]
        self.assertIn("emails/test.html", render_calls)
        self.assertIn("emails/test.txt", render_calls)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    @patch("apps.core.services.base_email_service.EmailMultiAlternatives")
    @patch("apps.core.services.base_email_service.render_to_string")
    def test_send_email_failure_returns_false(self, mock_render, mock_email_class):
        mock_render.return_value = "<html>Test</html>"
        mock_email = MagicMock()
        mock_email.send.side_effect = smtplib.SMTPException("SMTP error")
        mock_email_class.return_value = mock_email

        result = self.service._send_email(
            subject="Test",
            html_template="emails/test.html",
            context={},
            recipient_list=["test@example.com"],
        )

        self.assertFalse(result)

    def test_health_check_default_returns_true(self):
        """Default health_check just returns True (no model dependency)."""
        result = self.service.health_check()
        self.assertTrue(result)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    @patch("apps.core.services.base_email_service.render_to_string")
    def test_send_email_renders_on_console_backend(self, mock_render):
        """Issue #229: non-SMTP backends must still render/send so dev can see the email."""
        mock_render.return_value = "<html>Test</html>"

        result = self.service._send_email(
            subject="Test",
            html_template="emails/test.html",
            context={},
            recipient_list=["test@example.com"],
        )

        self.assertTrue(result)
        mock_render.assert_called()
