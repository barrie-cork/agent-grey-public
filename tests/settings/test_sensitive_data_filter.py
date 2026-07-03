"""
Tests for SensitiveDataFilter and its attachment to logging handlers.

Verifies that the filter correctly redacts sensitive data (passwords, API keys,
tokens, emails) and is attached to all handlers in the logging configuration.
"""

import logging

from django.test import TestCase

from grey_lit_project.logging_filters import SensitiveDataFilter
from grey_lit_project.settings.logging import get_logging_config


class SensitiveDataFilterTest(TestCase):
    """Unit tests for the SensitiveDataFilter class."""

    def setUp(self):
        self.filter = SensitiveDataFilter()

    def _make_record(self, msg, args=None):
        """Create a log record with the given message and optional args."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=args,
            exc_info=None,
        )
        return record

    def test_filter_redacts_password(self):
        """Passwords in log messages should be redacted."""
        record = self._make_record("User login password=secret123")
        self.filter.filter(record)
        self.assertNotIn("secret123", record.msg)
        self.assertIn("***REDACTED***", record.msg)

    def test_filter_redacts_api_key(self):
        """API keys in log messages should be redacted."""
        record = self._make_record("Request with api_key=test_key_value_123")
        self.filter.filter(record)
        self.assertNotIn("test_key_value_123", record.msg)
        self.assertIn("***REDACTED***", record.msg)

    def test_filter_redacts_bearer_token(self):
        """Bearer tokens in log messages should be redacted."""
        record = self._make_record("Auth header: Bearer eyJhbGciOiJIUzI1NiJ9")
        self.filter.filter(record)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", record.msg)
        self.assertIn("***REDACTED***", record.msg)

    def test_filter_redacts_email(self):
        """Email addresses in log messages should be partially redacted."""
        record = self._make_record("User john.doe@example.com logged in")
        self.filter.filter(record)
        self.assertNotIn("john.doe@example.com", record.msg)
        self.assertIn("***@example.com", record.msg)

    def test_filter_never_suppresses_messages(self):
        """The filter should always return True (never suppress log records)."""
        messages = [
            "Normal message",
            "password=secret123",
            "api_key=abc123",
            "Bearer token123",
            "user@example.com",
            "",
        ]
        for msg in messages:
            record = self._make_record(msg)
            result = self.filter.filter(record)
            self.assertTrue(
                result,
                f"Filter suppressed message: {msg!r}",
            )

    def test_filter_redacts_args(self):
        """Sensitive data in log record args should also be redacted."""
        record = self._make_record(
            "Login attempt: %s",
            ("password=hunter2",),
        )
        self.filter.filter(record)
        self.assertNotIn("hunter2", str(record.args))


class SensitiveDataFilterAttachmentTest(TestCase):
    """Integration tests verifying the filter is attached to all handlers."""

    def test_filter_attached_to_all_handlers_in_logging_config(self):
        """Every handler in get_logging_config() must have sensitive_data_filter."""
        config = get_logging_config(debug=False)
        handlers = config["handlers"]

        for handler_name, handler_config in handlers.items():
            filters = handler_config.get("filters", [])
            self.assertIn(
                "sensitive_data_filter",
                filters,
                f"Handler '{handler_name}' is missing the "
                f"sensitive_data_filter. Filters: {filters}",
            )

    def test_filter_attached_in_debug_mode(self):
        """Filter should be present on all handlers even in debug mode."""
        config = get_logging_config(debug=True)
        handlers = config["handlers"]

        for handler_name, handler_config in handlers.items():
            filters = handler_config.get("filters", [])
            self.assertIn(
                "sensitive_data_filter",
                filters,
                f"Handler '{handler_name}' missing sensitive_data_filter "
                f"in debug mode. Filters: {filters}",
            )

    def test_production_logging_has_filter(self):
        """Production LOGGING dict should define and attach the filter."""
        import pathlib

        production_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "grey_lit_project"
            / "settings"
            / "production.py"
        )
        content = production_path.read_text()

        # Verify the real production.py defines the sensitive_data_filter
        self.assertIn('"sensitive_data_filter"', content)
        self.assertIn("grey_lit_project.logging_filters.SensitiveDataFilter", content)

    def test_filter_definition_uses_correct_class(self):
        """The filter definition should reference the correct class path."""
        config = get_logging_config(debug=False)
        filter_def = config["filters"]["sensitive_data_filter"]
        self.assertEqual(
            filter_def["()"],
            "grey_lit_project.logging_filters.SensitiveDataFilter",
        )
