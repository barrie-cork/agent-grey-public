"""
Tests for Django SECRET_KEY generator utility.

Comprehensive test coverage for secret key generation, validation,
and management functions.
"""

from django.test import TestCase

from apps.core.utils.secret_key_generator import (
    generate_secret_key,
    get_or_generate_secret_key,
    validate_secret_key,
)


class SecretKeyGeneratorTest(TestCase):
    """Test cases for secret key generator functions."""

    def test_generate_secret_key_default_length(self):
        """Test generating a key with default length (50)."""
        key = generate_secret_key()
        self.assertEqual(len(key), 50)
        # Ensure it's a string
        self.assertIsInstance(key, str)
        # Ensure no quotes or backslashes (Django-safe)
        self.assertNotIn("'", key)
        self.assertNotIn('"', key)
        self.assertNotIn("\\", key)

    def test_generate_secret_key_custom_length(self):
        """Test generating keys with custom lengths."""
        # Test various valid lengths
        for length in [32, 40, 64, 100]:
            key = generate_secret_key(length)
            self.assertEqual(len(key), length)

    def test_generate_secret_key_minimum_length_error(self):
        """Test that keys below minimum length raise ValueError."""
        with self.assertRaises(ValueError) as context:
            generate_secret_key(31)
        self.assertIn("32 characters", str(context.exception))

        with self.assertRaises(ValueError) as context:
            generate_secret_key(10)
        self.assertIn("32 characters", str(context.exception))

    def test_generate_secret_key_uniqueness(self):
        """Test that generated keys are unique."""
        keys = set()
        for _ in range(100):
            key = generate_secret_key()
            # Ensure no duplicates
            self.assertNotIn(key, keys)
            keys.add(key)

    def test_get_or_generate_secret_key_with_valid_existing(self):
        """Test returning existing key when it's valid."""
        existing_key = "a" * 50  # 50 character key
        result = get_or_generate_secret_key(existing_key)
        self.assertEqual(result, existing_key)

        # Test with exactly minimum length
        existing_key = "b" * 32
        result = get_or_generate_secret_key(existing_key, min_length=32)
        self.assertEqual(result, existing_key)

    def test_get_or_generate_secret_key_with_invalid_existing(self):
        """Test generating new key when existing is invalid."""
        # Test with short key
        short_key = "too-short"
        result = get_or_generate_secret_key(short_key)
        self.assertNotEqual(result, short_key)
        self.assertGreaterEqual(len(result), 50)

        # Test with None
        result = get_or_generate_secret_key(None)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result), 50)

        # Test with empty string
        result = get_or_generate_secret_key("")
        self.assertNotEqual(result, "")
        self.assertGreaterEqual(len(result), 50)

    def test_get_or_generate_secret_key_custom_min_length(self):
        """Test get_or_generate with custom minimum length."""
        # Existing key meets custom requirement
        existing_key = "c" * 60
        result = get_or_generate_secret_key(existing_key, min_length=60)
        self.assertEqual(result, existing_key)

        # Existing key doesn't meet custom requirement
        short_key = "d" * 40
        result = get_or_generate_secret_key(short_key, min_length=60)
        self.assertNotEqual(result, short_key)
        self.assertGreaterEqual(len(result), 70)  # min_length + 10

    def test_validate_secret_key_valid(self):
        """Test validation of valid secret keys."""
        # Valid key with default min length
        valid_key = "a" * 50
        is_valid, error = validate_secret_key(valid_key)
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

        # Valid key at exactly minimum length
        valid_key = "b" * 32
        is_valid, error = validate_secret_key(valid_key)
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

        # Valid key with custom min length
        valid_key = "c" * 100
        is_valid, error = validate_secret_key(valid_key, min_length=100)
        self.assertTrue(is_valid)
        self.assertEqual(error, "")

    def test_validate_secret_key_too_short(self):
        """Test validation fails for short keys."""
        short_key = "short-key"
        is_valid, error = validate_secret_key(short_key)
        self.assertFalse(is_valid)
        self.assertIn("32 characters", error)
        self.assertIn("current: 9", error)

        # Test with custom min length
        key = "a" * 40
        is_valid, error = validate_secret_key(key, min_length=50)
        self.assertFalse(is_valid)
        self.assertIn("50 characters", error)
        self.assertIn("current: 40", error)

    def test_validate_secret_key_empty(self):
        """Test validation of empty or None keys."""
        # Empty string
        is_valid, error = validate_secret_key("")
        self.assertFalse(is_valid)
        self.assertEqual(error, "SECRET_KEY is not set")

        # None is handled by type checking in real usage,
        # but if passed as string it would be caught
        is_valid, error = validate_secret_key(None)  # type: ignore[arg-type]
        self.assertFalse(is_valid)
        self.assertEqual(error, "SECRET_KEY is not set")

    def test_validate_secret_key_insecure_patterns(self):
        """Test validation detects insecure patterns."""
        insecure_keys = [
            "django-insecure-" + "a" * 40,
            "change-this-" + "b" * 40,
            "your-secret-key-" + "c" * 40,
            "placeholder-" + "d" * 40,
            "example-" + "e" * 40,
            "test-key-" + "f" * 40,
        ]

        for insecure_key in insecure_keys:
            is_valid, error = validate_secret_key(insecure_key)
            self.assertFalse(is_valid)
            self.assertIn("insecure pattern", error)

    def test_validate_secret_key_case_insensitive_patterns(self):
        """Test that insecure pattern detection is case-insensitive."""
        # Test uppercase
        insecure_key = "DJANGO-INSECURE-" + "A" * 40
        is_valid, error = validate_secret_key(insecure_key)
        self.assertFalse(is_valid)
        self.assertIn("insecure pattern", error)

        # Test mixed case
        insecure_key = "Django-Insecure-" + "B" * 40
        is_valid, error = validate_secret_key(insecure_key)
        self.assertFalse(is_valid)
        self.assertIn("insecure pattern", error)

    def test_generated_keys_are_valid(self):
        """Test that all generated keys pass validation."""
        for _ in range(10):
            key = generate_secret_key()
            is_valid, error = validate_secret_key(key)
            self.assertTrue(is_valid)
            self.assertEqual(error, "")

    def test_get_or_generate_produces_valid_keys(self):
        """Test that get_or_generate always produces valid keys."""
        # With no existing key
        key = get_or_generate_secret_key(None)
        is_valid, error = validate_secret_key(key)
        self.assertTrue(is_valid)

        # With invalid existing key
        key = get_or_generate_secret_key("short")
        is_valid, error = validate_secret_key(key)
        self.assertTrue(is_valid)

        # With valid existing key
        valid_existing = "x" * 50
        key = get_or_generate_secret_key(valid_existing)
        is_valid, error = validate_secret_key(key)
        self.assertTrue(is_valid)

    def test_secret_key_character_set(self):
        """Test that generated keys only use allowed characters."""
        allowed_chars = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()-_=+[]{}|;:,.<>?"
        )

        for _ in range(10):
            key = generate_secret_key()
            key_chars = set(key)
            # All characters in key should be in allowed set
            self.assertTrue(key_chars.issubset(allowed_chars))
            # No quotes or backslashes
            self.assertNotIn("'", key_chars)
            self.assertNotIn('"', key_chars)
            self.assertNotIn("\\", key_chars)
