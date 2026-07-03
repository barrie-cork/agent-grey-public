"""
Tests for environment configuration utilities.
"""

import os
from unittest.mock import patch

from django.test import TestCase

from apps.core.env_config import get_env, get_env_bool, get_env_float, get_env_int


class EnvConfigTestCase(TestCase):
    """Test environment configuration utilities."""

    def setUp(self):
        """Set up test environment."""
        # Clear any existing env vars that might interfere
        self.test_vars = [
            "TEST_STRING",
            "TEST_BOOL",
            "TEST_INT",
            "TEST_FLOAT",
            "TEST_CALLABLE",
            "TEST_NONE",
        ]
        for var in self.test_vars:
            if var in os.environ:
                del os.environ[var]

    def tearDown(self):
        """Clean up test environment."""
        for var in self.test_vars:
            if var in os.environ:
                del os.environ[var]

    # Basic get_env tests
    def test_get_env_string_value(self):
        """Test getting string environment variable."""
        os.environ["TEST_STRING"] = "test_value"
        result = get_env("TEST_STRING")
        self.assertEqual(result, "test_value")

    def test_get_env_default_value(self):
        """Test getting default value when env var not set."""
        result = get_env("TEST_MISSING", default="default_value")
        self.assertEqual(result, "default_value")

    def test_get_env_no_default(self):
        """Test getting None when no env var and no default."""
        result = get_env("TEST_MISSING")
        self.assertIsNone(result)

    # Boolean casting tests
    def test_get_env_bool_true_values(self):
        """Test boolean casting for true values."""
        true_values = ["true", "True", "1", "yes", "YES", "on", "t", "y"]
        for value in true_values:
            os.environ["TEST_BOOL"] = value
            result = get_env_bool("TEST_BOOL")
            self.assertTrue(result, f"Failed for value: {value}")

    def test_get_env_bool_false_values(self):
        """Test boolean casting for false values."""
        false_values = ["false", "False", "0", "no", "NO", "off", "f", "n", ""]
        for value in false_values:
            os.environ["TEST_BOOL"] = value
            result = get_env_bool("TEST_BOOL")
            self.assertFalse(result, f"Failed for value: {value}")

    def test_get_env_bool_default(self):
        """Test boolean default value."""
        result = get_env_bool("TEST_MISSING", default=True)
        self.assertTrue(result)

    # Integer casting tests
    def test_get_env_int_valid(self):
        """Test integer casting with valid values."""
        os.environ["TEST_INT"] = "42"
        result = get_env_int("TEST_INT")
        self.assertEqual(result, 42)

    def test_get_env_int_invalid(self):
        """Test integer casting with invalid values."""
        os.environ["TEST_INT"] = "not_a_number"
        result = get_env_int("TEST_INT", default=10)
        self.assertEqual(result, 10)

    def test_get_env_int_negative(self):
        """Test integer casting with negative values."""
        os.environ["TEST_INT"] = "-100"
        result = get_env_int("TEST_INT")
        self.assertEqual(result, -100)

    # Float casting tests
    def test_get_env_float_valid(self):
        """Test float casting with valid values."""
        os.environ["TEST_FLOAT"] = "3.14"
        result = get_env_float("TEST_FLOAT")
        self.assertAlmostEqual(result, 3.14)

    def test_get_env_float_integer(self):
        """Test float casting with integer values."""
        os.environ["TEST_FLOAT"] = "42"
        result = get_env_float("TEST_FLOAT")
        self.assertEqual(result, 42.0)

    def test_get_env_float_invalid(self):
        """Test float casting with invalid values."""
        os.environ["TEST_FLOAT"] = "not_a_float"
        result = get_env_float("TEST_FLOAT", default=1.5)
        self.assertEqual(result, 1.5)

    # Callable cast function tests
    def test_get_env_callable_cast(self):
        """Test using callable as cast function."""
        os.environ["TEST_CALLABLE"] = "test_value"

        def custom_cast(value):
            return f"custom_{value}"

        result = get_env("TEST_CALLABLE", cast=custom_cast)  # type: ignore[arg-type]
        self.assertEqual(result, "custom_test_value")

    def test_get_env_callable_cast_returns_none(self):
        """Test callable cast returning None falls back to default."""
        os.environ["TEST_NONE"] = "test_value"

        def returns_none(value):
            return None

        result = get_env("TEST_NONE", cast=returns_none, default="default_value")  # type: ignore[arg-type]
        self.assertEqual(result, "default_value")

    def test_get_env_callable_cast_exception(self):
        """Test callable cast raising exception falls back to default."""
        os.environ["TEST_CALLABLE"] = "test_value"

        def raises_error(value):
            raise ValueError("Test error")

        result = get_env("TEST_CALLABLE", cast=raises_error, default="default_value")  # type: ignore[arg-type]
        self.assertEqual(result, "default_value")

    def test_get_env_lambda_cast(self):
        """Test using lambda as cast function."""
        os.environ["TEST_CALLABLE"] = "10"

        result = get_env("TEST_CALLABLE", cast=lambda x: int(x) * 2)  # type: ignore[arg-type]
        self.assertEqual(result, 20)

    # Edge cases
    def test_get_env_with_bool_cast_type(self):
        """Test using bool as cast parameter."""
        os.environ["TEST_BOOL"] = "yes"
        result = get_env("TEST_BOOL", cast=bool)
        self.assertTrue(result)

    def test_get_env_with_int_cast_type(self):
        """Test using int as cast parameter."""
        os.environ["TEST_INT"] = "99"
        result = get_env("TEST_INT", cast=int)
        self.assertEqual(result, 99)

    def test_get_env_with_float_cast_type(self):
        """Test using float as cast parameter."""
        os.environ["TEST_FLOAT"] = "2.718"
        result = get_env("TEST_FLOAT", cast=float)
        self.assertAlmostEqual(result, 2.718)

    def test_get_env_with_str_cast_type(self):
        """Test using str as cast parameter."""
        os.environ["TEST_STRING"] = "123"
        result = get_env("TEST_STRING", cast=str)
        self.assertEqual(result, "123")
        self.assertIsInstance(result, str)

    # Test with decouple mock
    @patch("apps.core.env_config._is_debug_mode")
    def test_get_env_with_decouple_in_debug(self, mock_is_debug):
        """Test that decouple is used in debug mode."""
        # Mock debug mode to return True
        mock_is_debug.return_value = True

        # Mock the decouple.config import that happens inside _get_from_decouple
        with patch("decouple.config") as mock_decouple_config:
            mock_decouple_config.return_value = "decouple_value"

            # This should trigger the decouple path since DEBUG=True
            result = get_env("TEST_KEY", default="default_value")

            # In debug mode with decouple available, it should use decouple
            mock_decouple_config.assert_called_once_with(
                "TEST_KEY", default="default_value"
            )
            self.assertEqual(result, "decouple_value")

    @patch("apps.core.env_config._is_debug_mode")
    def test_get_env_skips_decouple_in_production(self, mock_is_debug):
        """Test that decouple is skipped when DEBUG=False."""
        # Mock debug mode to return False
        mock_is_debug.return_value = False
        os.environ["TEST_KEY"] = "production_value"

        # In production (DEBUG=False), should use os.environ directly
        result = get_env("TEST_KEY")

        self.assertEqual(result, "production_value")

    @patch("apps.core.env_config._is_debug_mode")
    def test_get_env_fallback_when_decouple_not_available(self, mock_is_debug):
        """Test fallback to os.environ when decouple import fails."""
        # Mock debug mode to return True
        mock_is_debug.return_value = True

        # Temporarily make decouple unimportable
        with patch.dict("sys.modules", {"decouple": None}):
            os.environ["TEST_KEY"] = "fallback_value"

            # Should fall back to os.environ when decouple can't be imported
            result = get_env("TEST_KEY")

            self.assertEqual(result, "fallback_value")

            # Clean up
            del os.environ["TEST_KEY"]

    # Test default value casting scenarios
    def test_get_env_default_not_cast(self):
        """Test that default values are returned as-is when casting fails."""
        result = get_env("TEST_MISSING", default="default", cast=int)
        self.assertEqual(result, "default")

    def test_get_env_none_default_with_cast(self):
        """Test None default with cast function."""
        result = get_env("TEST_MISSING", default=None, cast=int)
        self.assertIsNone(result)

    def test_get_env_empty_string_cast_to_int(self):
        """Test empty string casting to int returns default."""
        os.environ["TEST_INT"] = ""
        result = get_env_int("TEST_INT", default=0)
        self.assertEqual(result, 0)


class HelperFunctionTestCase(TestCase):
    """Test helper functions for specific types."""

    def setUp(self):
        """Set up test environment."""
        self.test_vars = ["TEST_BOOL", "TEST_INT", "TEST_FLOAT"]
        for var in self.test_vars:
            if var in os.environ:
                del os.environ[var]

    def tearDown(self):
        """Clean up test environment."""
        for var in self.test_vars:
            if var in os.environ:
                del os.environ[var]

    def test_get_env_bool_helper(self):
        """Test get_env_bool helper function."""
        os.environ["TEST_BOOL"] = "true"
        self.assertTrue(get_env_bool("TEST_BOOL"))

        os.environ["TEST_BOOL"] = "false"
        self.assertFalse(get_env_bool("TEST_BOOL"))

        del os.environ["TEST_BOOL"]
        self.assertFalse(get_env_bool("TEST_BOOL"))
        self.assertTrue(get_env_bool("TEST_BOOL", default=True))

    def test_get_env_int_helper(self):
        """Test get_env_int helper function."""
        os.environ["TEST_INT"] = "123"
        self.assertEqual(get_env_int("TEST_INT"), 123)

        os.environ["TEST_INT"] = "invalid"
        self.assertEqual(get_env_int("TEST_INT", default=999), 999)

        del os.environ["TEST_INT"]
        self.assertEqual(get_env_int("TEST_INT", default=0), 0)

    def test_get_env_float_helper(self):
        """Test get_env_float helper function."""
        os.environ["TEST_FLOAT"] = "123.456"
        self.assertAlmostEqual(get_env_float("TEST_FLOAT"), 123.456)

        os.environ["TEST_FLOAT"] = "invalid"
        self.assertEqual(get_env_float("TEST_FLOAT", default=0.0), 0.0)

        del os.environ["TEST_FLOAT"]
        self.assertEqual(get_env_float("TEST_FLOAT", default=1.0), 1.0)
