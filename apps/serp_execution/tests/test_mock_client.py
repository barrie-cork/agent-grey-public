"""Tests for get_serper_client() factory function environment gating."""

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from apps.serp_execution.services.mock_serper_client import (
    MockSerperClient,
    get_serper_client,
)


class GetSerperClientProductionTests(TestCase):
    """Test that mock client is never returned in production/staging."""

    @override_settings(
        ENVIRONMENT="production",
        SERPER_API_KEY="sk-real-production-key-abc123",
        ENABLE_SERPER_MOCKING=False,
    )
    def test_production_with_valid_key_returns_real_client(self):
        client = get_serper_client()
        self.assertNotIsInstance(client, MockSerperClient)

    @override_settings(
        ENVIRONMENT="production",
        SERPER_API_KEY="",
        ENABLE_SERPER_MOCKING=False,
    )
    def test_production_with_empty_key_raises_error(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            get_serper_client()
        self.assertIn("SERPER_API_KEY is required", str(ctx.exception))

    @override_settings(
        ENVIRONMENT="production",
        SERPER_API_KEY="sk-real-production-key-abc123",
        ENABLE_SERPER_MOCKING=True,
    )
    def test_production_ignores_enable_mocking_flag(self):
        """Environment gate overrides ENABLE_SERPER_MOCKING in production."""
        client = get_serper_client()
        self.assertNotIsInstance(client, MockSerperClient)

    @override_settings(
        ENVIRONMENT="staging",
        SERPER_API_KEY="",
        ENABLE_SERPER_MOCKING=False,
    )
    def test_staging_with_empty_key_raises_error(self):
        with self.assertRaises(ImproperlyConfigured):
            get_serper_client()

    @override_settings(
        ENVIRONMENT="staging",
        SERPER_API_KEY="sk-staging-key-xyz789",
        ENABLE_SERPER_MOCKING=False,
    )
    def test_staging_with_valid_key_returns_real_client(self):
        client = get_serper_client()
        self.assertNotIsInstance(client, MockSerperClient)


class GetSerperClientLocalTests(TestCase):
    """Test that mock client works correctly in local/test environments."""

    @override_settings(
        ENVIRONMENT="local",
        SERPER_API_KEY="",
        ENABLE_SERPER_MOCKING=False,
    )
    def test_local_with_empty_key_returns_mock(self):
        client = get_serper_client()
        self.assertIsInstance(client, MockSerperClient)

    @override_settings(
        ENVIRONMENT="local",
        SERPER_API_KEY="sk-real-key-for-local-dev",
        ENABLE_SERPER_MOCKING=True,
    )
    def test_local_with_mocking_enabled_returns_mock(self):
        client = get_serper_client()
        self.assertIsInstance(client, MockSerperClient)

    @override_settings(
        ENVIRONMENT="local",
        SERPER_API_KEY="sk-real-key-for-local-dev",
        ENABLE_SERPER_MOCKING=False,
    )
    def test_local_with_valid_key_returns_real_client(self):
        client = get_serper_client()
        self.assertNotIsInstance(client, MockSerperClient)

    @override_settings(
        ENVIRONMENT="local",
        SERPER_API_KEY="test-api-key-for-ci",
        ENABLE_SERPER_MOCKING=False,
    )
    def test_local_with_test_key_returns_mock(self):
        """Keys containing 'test' trigger mock in local environment."""
        client = get_serper_client()
        self.assertIsInstance(client, MockSerperClient)

    @override_settings(
        ENVIRONMENT="",
        SERPER_API_KEY="",
        ENABLE_SERPER_MOCKING=False,
    )
    def test_unknown_environment_with_empty_key_returns_mock(self):
        """When ENVIRONMENT is not set, default to allowing mock."""
        client = get_serper_client()
        self.assertIsInstance(client, MockSerperClient)
