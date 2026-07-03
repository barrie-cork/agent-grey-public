"""Tests for configuration helper utilities.

This module tests the utility functions in config_helpers.py that are used
for parsing and validating configuration values.

Created: 2025-10-17
Purpose: Phase 3 of Post-Deployment Refactoring Plan - Task 3.6.2
"""

from django.test import TestCase

from apps.core.utils.config_helpers import (
    create_ssl_redis_config,
    format_bytes,
    get_redis_ssl_connection_kwargs,
    is_empty_or_whitespace,
    merge_dict_settings,
    parse_boolean,
    parse_csv_env_var,
    parse_float,
    parse_integer,
    sanitize_secret_for_logging,
    validate_postgres_connection_string,
    validate_redis_connection_string,
    validate_url_format,
)


class ParseCSVEnvVarTestCase(TestCase):
    """Test parse_csv_env_var() function."""

    def test_empty_string_returns_empty_list(self):
        """Test that empty string returns empty list."""
        result = parse_csv_env_var("")
        self.assertEqual(result, [])

    def test_none_returns_empty_list(self):
        """Test that None returns empty list."""
        result = parse_csv_env_var(None)  # type: ignore[arg-type]
        self.assertEqual(result, [])

    def test_single_value_without_comma(self):
        """Test parsing single value without comma."""
        result = parse_csv_env_var("single")
        self.assertEqual(result, ["single"])

    def test_multiple_values_with_comma(self):
        """Test parsing multiple comma-separated values."""
        result = parse_csv_env_var("one,two,three")
        self.assertEqual(result, ["one", "two", "three"])

    def test_values_with_whitespace_stripped(self):
        """Test that whitespace is stripped from values."""
        result = parse_csv_env_var(" one , two , three ")
        self.assertEqual(result, ["one", "two", "three"])

    def test_empty_values_filtered_out(self):
        """Test that empty values between commas are filtered out."""
        result = parse_csv_env_var("one,,three,")
        self.assertEqual(result, ["one", "three"])

    def test_custom_separator(self):
        """Test parsing with custom separator."""
        result = parse_csv_env_var("one;two;three", separator=";")
        self.assertEqual(result, ["one", "two", "three"])

    def test_no_strip_whitespace(self):
        """Test parsing with strip_whitespace=False."""
        result = parse_csv_env_var(" one , two ", strip_whitespace=False)
        self.assertEqual(result, [" one ", " two "])

    def test_no_filter_empty(self):
        """Test parsing with filter_empty=False."""
        result = parse_csv_env_var("one,,three", filter_empty=False)
        self.assertEqual(result, ["one", "", "three"])


class IsEmptyOrWhitespaceTestCase(TestCase):
    """Test is_empty_or_whitespace() function."""

    def test_none_is_empty(self):
        """Test that None is considered empty."""
        self.assertTrue(is_empty_or_whitespace(None))

    def test_empty_string_is_empty(self):
        """Test that empty string is considered empty."""
        self.assertTrue(is_empty_or_whitespace(""))

    def test_whitespace_only_is_empty(self):
        """Test that whitespace-only string is considered empty."""
        self.assertTrue(is_empty_or_whitespace("   "))
        self.assertTrue(is_empty_or_whitespace("\t\n"))

    def test_non_empty_string_is_not_empty(self):
        """Test that non-empty string is not considered empty."""
        self.assertFalse(is_empty_or_whitespace("hello"))
        self.assertFalse(is_empty_or_whitespace(" hello "))

    def test_zero_is_not_empty(self):
        """Test that zero is not considered empty."""
        self.assertFalse(is_empty_or_whitespace(0))

    def test_false_is_not_empty(self):
        """Test that False is not considered empty."""
        self.assertFalse(is_empty_or_whitespace(False))


class ValidateURLFormatTestCase(TestCase):
    """Test validate_url_format() function."""

    def test_empty_url_is_invalid(self):
        """Test that empty URL is invalid."""
        is_valid, error = validate_url_format("")
        self.assertFalse(is_valid)
        self.assertIn("empty", error)

    def test_none_url_is_invalid(self):
        """Test that None URL is invalid."""
        is_valid, error = validate_url_format(None)  # type: ignore[arg-type]
        self.assertFalse(is_valid)

    def test_url_without_scheme_is_invalid(self):
        """Test that URL without scheme is invalid."""
        is_valid, error = validate_url_format("example.com")
        self.assertFalse(is_valid)
        self.assertIn("scheme", error.lower())

    def test_url_without_hostname_is_invalid(self):
        """Test that URL without hostname is invalid."""
        is_valid, error = validate_url_format("http://")
        self.assertFalse(is_valid)
        self.assertIn("hostname", error.lower())

    def test_valid_http_url(self):
        """Test that valid HTTP URL is valid."""
        is_valid, error = validate_url_format("http://example.com")
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

    def test_valid_https_url(self):
        """Test that valid HTTPS URL is valid."""
        is_valid, error = validate_url_format("https://example.com")
        self.assertTrue(is_valid)

    def test_valid_redis_url(self):
        """Test that valid Redis URL is valid."""
        is_valid, error = validate_url_format("redis://localhost:6379/0")
        self.assertTrue(is_valid)

    def test_allowed_schemes_validation(self):
        """Test validation with allowed_schemes parameter."""
        is_valid, error = validate_url_format(
            "http://example.com", allowed_schemes=["https"]
        )
        self.assertFalse(is_valid)
        self.assertIn("scheme", error)

    def test_allowed_schemes_pass(self):
        """Test validation passes with matching scheme."""
        is_valid, error = validate_url_format(
            "https://example.com", allowed_schemes=["https"]
        )
        self.assertTrue(is_valid)


class ParseBooleanTestCase(TestCase):
    """Test parse_boolean() function."""

    def test_parse_true_boolean(self):
        """Test parsing True boolean."""
        self.assertTrue(parse_boolean(True))

    def test_parse_false_boolean(self):
        """Test parsing False boolean."""
        self.assertFalse(parse_boolean(False))

    def test_parse_string_true(self):
        """Test parsing 'true' string."""
        self.assertTrue(parse_boolean("true"))
        self.assertTrue(parse_boolean("TRUE"))
        self.assertTrue(parse_boolean("True"))

    def test_parse_string_false(self):
        """Test parsing 'false' string."""
        self.assertFalse(parse_boolean("false"))
        self.assertFalse(parse_boolean("FALSE"))
        self.assertFalse(parse_boolean("False"))

    def test_parse_string_1(self):
        """Test parsing '1' string."""
        self.assertTrue(parse_boolean("1"))

    def test_parse_string_0(self):
        """Test parsing '0' string."""
        self.assertFalse(parse_boolean("0"))

    def test_parse_string_yes(self):
        """Test parsing 'yes' string."""
        self.assertTrue(parse_boolean("yes"))
        self.assertTrue(parse_boolean("YES"))

    def test_parse_string_no(self):
        """Test parsing 'no' string."""
        self.assertFalse(parse_boolean("no"))
        self.assertFalse(parse_boolean("NO"))

    def test_parse_string_on(self):
        """Test parsing 'on' string."""
        self.assertTrue(parse_boolean("on"))

    def test_parse_string_off(self):
        """Test parsing 'off' string."""
        self.assertFalse(parse_boolean("off"))

    def test_parse_integer_1(self):
        """Test parsing integer 1."""
        self.assertTrue(parse_boolean(1))

    def test_parse_integer_0(self):
        """Test parsing integer 0."""
        self.assertFalse(parse_boolean(0))

    def test_parse_invalid_string_strict_mode(self):
        """Test parsing invalid string in strict mode."""
        self.assertFalse(parse_boolean("invalid", strict=True))

    def test_parse_invalid_string_non_strict_mode(self):
        """Test parsing invalid string in non-strict mode."""
        result = parse_boolean("hello")
        # Non-strict mode uses Python truthiness
        self.assertTrue(result)


class ParseIntegerTestCase(TestCase):
    """Test parse_integer() function."""

    def test_parse_valid_integer_string(self):
        """Test parsing valid integer string."""
        self.assertEqual(parse_integer("42"), 42)

    def test_parse_valid_integer(self):
        """Test parsing integer value."""
        self.assertEqual(parse_integer(42), 42)

    def test_parse_invalid_string_returns_default(self):
        """Test that invalid string returns default."""
        self.assertEqual(parse_integer("invalid", default=10), 10)

    def test_parse_none_returns_default(self):
        """Test that None returns default."""
        self.assertEqual(parse_integer(None, default=5), 5)

    def test_parse_with_min_value_constraint(self):
        """Test parsing with min_value constraint."""
        self.assertEqual(parse_integer(-10, min_value=0), 0)

    def test_parse_with_max_value_constraint(self):
        """Test parsing with max_value constraint."""
        self.assertEqual(parse_integer(100, max_value=50), 50)

    def test_parse_value_within_range(self):
        """Test parsing value within min/max range."""
        self.assertEqual(parse_integer(25, min_value=0, max_value=50), 25)

    def test_parse_negative_integer(self):
        """Test parsing negative integer."""
        self.assertEqual(parse_integer("-42"), -42)


class ParseFloatTestCase(TestCase):
    """Test parse_float() function."""

    def test_parse_valid_float_string(self):
        """Test parsing valid float string."""
        self.assertEqual(parse_float("3.14"), 3.14)

    def test_parse_valid_float(self):
        """Test parsing float value."""
        self.assertEqual(parse_float(3.14), 3.14)

    def test_parse_invalid_string_returns_default(self):
        """Test that invalid string returns default."""
        self.assertEqual(parse_float("invalid", default=1.0), 1.0)

    def test_parse_none_returns_default(self):
        """Test that None returns default."""
        self.assertEqual(parse_float(None, default=2.5), 2.5)

    def test_parse_with_min_value_constraint(self):
        """Test parsing with min_value constraint."""
        self.assertEqual(parse_float(-1.5, min_value=0.0), 0.0)

    def test_parse_with_max_value_constraint(self):
        """Test parsing with max_value constraint."""
        self.assertEqual(parse_float(10.5, max_value=5.0), 5.0)

    def test_parse_value_within_range(self):
        """Test parsing value within min/max range."""
        self.assertEqual(parse_float(2.5, min_value=0.0, max_value=5.0), 2.5)

    def test_parse_integer_as_float(self):
        """Test parsing integer string as float."""
        self.assertEqual(parse_float("42"), 42.0)


class CreateSSLRedisConfigTestCase(TestCase):
    """Test create_ssl_redis_config() function."""

    def test_returns_ssl_config_dict(self):
        """Test that function returns SSL configuration dictionary."""
        config = create_ssl_redis_config()

        self.assertIsInstance(config, dict)
        self.assertIn("ssl_cert_reqs", config)
        self.assertIn("ssl_ca_certs", config)
        self.assertIn("ssl_certfile", config)
        self.assertIn("ssl_keyfile", config)

    def test_ssl_cert_reqs_is_none(self):
        """Test that ssl_cert_reqs is CERT_NONE."""
        import ssl

        config = create_ssl_redis_config()
        self.assertEqual(config["ssl_cert_reqs"], ssl.CERT_NONE)

    def test_ssl_parameters_are_none(self):
        """Test that other SSL parameters are None."""
        config = create_ssl_redis_config()
        self.assertIsNone(config["ssl_ca_certs"])
        self.assertIsNone(config["ssl_certfile"])
        self.assertIsNone(config["ssl_keyfile"])


class GetRedisSSLConnectionKwargsTestCase(TestCase):
    """Test get_redis_ssl_connection_kwargs() function."""

    def test_returns_connection_kwargs(self):
        """Test that function returns connection kwargs dictionary."""
        kwargs = get_redis_ssl_connection_kwargs()

        self.assertIsInstance(kwargs, dict)
        self.assertIn("connection_class", kwargs)

    def test_includes_ssl_config(self):
        """Test that result includes SSL configuration."""
        kwargs = get_redis_ssl_connection_kwargs()

        self.assertIn("ssl_cert_reqs", kwargs)


class ValidatePostgresConnectionStringTestCase(TestCase):
    """Test validate_postgres_connection_string() function."""

    def test_empty_connection_string_is_invalid(self):
        """Test that empty connection string is invalid."""
        is_valid, error = validate_postgres_connection_string("")
        self.assertFalse(is_valid)
        self.assertIn("empty", error.lower())

    def test_valid_postgresql_url(self):
        """Test that valid PostgreSQL URL is valid."""
        is_valid, error = validate_postgres_connection_string(
            "postgresql://user:pass@host:5432/db?sslmode=require"
        )
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

    def test_valid_postgres_url(self):
        """Test that postgres:// scheme is also valid."""
        is_valid, error = validate_postgres_connection_string(
            "postgres://user:pass@host:5432/db?sslmode=require"
        )
        self.assertTrue(is_valid)

    def test_invalid_scheme_mysql(self):
        """Test that MySQL scheme is invalid."""
        is_valid, error = validate_postgres_connection_string(
            "mysql://user:pass@host:3306/db"
        )
        self.assertFalse(is_valid)
        self.assertIn("scheme", error)

    def test_missing_ssl_mode_with_require_ssl_true(self):
        """Test that missing SSL mode is invalid when require_ssl=True."""
        is_valid, error = validate_postgres_connection_string(
            "postgresql://user:pass@host:5432/db", require_ssl=True
        )
        self.assertFalse(is_valid)
        self.assertIn("SSL", error)

    def test_missing_ssl_mode_with_require_ssl_false(self):
        """Test that missing SSL mode is OK when require_ssl=False."""
        is_valid, error = validate_postgres_connection_string(
            "postgresql://user:pass@host:5432/db", require_ssl=False
        )
        self.assertTrue(is_valid)


class ValidateRedisConnectionStringTestCase(TestCase):
    """Test validate_redis_connection_string() function."""

    def test_empty_connection_string_is_invalid(self):
        """Test that empty connection string is invalid."""
        is_valid, error = validate_redis_connection_string("")
        self.assertFalse(is_valid)
        self.assertIn("empty", error.lower())

    def test_valid_redis_url(self):
        """Test that valid redis:// URL is valid."""
        is_valid, warning = validate_redis_connection_string(
            "redis://host:6379/0", warn_non_ssl=False
        )
        self.assertTrue(is_valid)
        self.assertEqual(warning, "")

    def test_valid_rediss_url(self):
        """Test that valid rediss:// URL is valid."""
        is_valid, warning = validate_redis_connection_string("rediss://host:6380/0")
        self.assertTrue(is_valid)
        self.assertEqual(warning, "")

    def test_invalid_scheme_http(self):
        """Test that HTTP scheme is invalid."""
        is_valid, error = validate_redis_connection_string("http://host:6379/0")
        self.assertFalse(is_valid)
        self.assertIn("scheme", error)

    def test_non_ssl_redis_warning(self):
        """Test that non-SSL Redis generates warning."""
        is_valid, warning = validate_redis_connection_string(
            "redis://host:6379/0", warn_non_ssl=True
        )
        self.assertTrue(is_valid)
        self.assertIn("non-SSL", warning)

    def test_ssl_redis_no_warning(self):
        """Test that SSL Redis does not generate warning."""
        is_valid, warning = validate_redis_connection_string(
            "rediss://host:6380/0", warn_non_ssl=True
        )
        self.assertTrue(is_valid)
        self.assertEqual(warning, "")


class MergeDictSettingsTestCase(TestCase):
    """Test merge_dict_settings() function."""

    def test_merge_empty_dicts(self):
        """Test merging empty dictionaries."""
        result = merge_dict_settings({}, {})
        self.assertEqual(result, {})

    def test_merge_single_dict(self):
        """Test merging single dictionary."""
        result = merge_dict_settings({"a": 1, "b": 2})
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_merge_two_dicts_no_overlap(self):
        """Test merging two dictionaries with no overlapping keys."""
        result = merge_dict_settings({"a": 1}, {"b": 2})
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_merge_two_dicts_with_overlap(self):
        """Test merging two dictionaries with overlapping keys."""
        result = merge_dict_settings({"a": 1, "b": 2}, {"b": 3, "c": 4})
        self.assertEqual(result, {"a": 1, "b": 3, "c": 4})

    def test_merge_multiple_dicts(self):
        """Test merging multiple dictionaries."""
        result = merge_dict_settings({"a": 1}, {"b": 2}, {"c": 3})
        self.assertEqual(result, {"a": 1, "b": 2, "c": 3})

    def test_merge_with_none_values(self):
        """Test merging with None values."""
        result = merge_dict_settings({"a": 1}, None, {"b": 2})  # type: ignore[arg-type]
        self.assertEqual(result, {"a": 1, "b": 2})


class SanitizeSecretForLoggingTestCase(TestCase):
    """Test sanitize_secret_for_logging() function."""

    def test_empty_secret_returns_stars(self):
        """Test that empty secret returns stars."""
        result = sanitize_secret_for_logging("")
        self.assertEqual(result, "****")

    def test_none_secret_returns_stars(self):
        """Test that None secret returns stars."""
        result = sanitize_secret_for_logging(None)  # type: ignore[arg-type]
        self.assertEqual(result, "****")

    def test_short_secret_returns_stars(self):
        """Test that short secret returns stars."""
        result = sanitize_secret_for_logging("short")
        self.assertEqual(result, "****")

    def test_long_secret_reveals_first_and_last_chars(self):
        """Test that long secret reveals first and last 4 characters."""
        result = sanitize_secret_for_logging("my_secret_key_1234567890")
        self.assertEqual(result, "my_s...7890")

    def test_custom_reveal_chars(self):
        """Test with custom reveal_chars parameter."""
        result = sanitize_secret_for_logging("my_secret_key_12345", reveal_chars=2)
        self.assertEqual(result, "my...45")


class FormatBytesTestCase(TestCase):
    """Test format_bytes() function."""

    def test_format_bytes(self):
        """Test formatting bytes."""
        self.assertEqual(format_bytes(512), "512.0 B")

    def test_format_kilobytes(self):
        """Test formatting kilobytes."""
        self.assertEqual(format_bytes(1024), "1.0 KB")

    def test_format_kilobytes_decimal(self):
        """Test formatting kilobytes with decimal."""
        self.assertEqual(format_bytes(1536), "1.5 KB")

    def test_format_megabytes(self):
        """Test formatting megabytes."""
        self.assertEqual(format_bytes(1048576), "1.0 MB")

    def test_format_gigabytes(self):
        """Test formatting gigabytes."""
        self.assertEqual(format_bytes(1073741824), "1.0 GB")

    def test_format_zero_bytes(self):
        """Test formatting zero bytes."""
        self.assertEqual(format_bytes(0), "0.0 B")
