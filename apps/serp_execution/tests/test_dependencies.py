"""
Tests for serp_execution dependencies module.
Validates dependency injection and provider management.
"""

import threading
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import TestCase

from apps.serp_execution.dependencies import (
    get_notification_service,
    get_session_provider,
    reset_providers,
)


class TestDependencyProviders(TestCase):
    """Test dependency provider functions."""

    def setUp(self):
        """Reset providers before each test."""
        reset_providers()

    def tearDown(self):
        """Reset providers after each test."""
        reset_providers()

    def test_session_provider_lifecycle(self):
        """Test getting and setting session provider."""
        # Initially should create default provider
        with patch(
            "apps.serp_execution.dependencies.DefaultSessionProvider"
        ) as mock_class:
            mock_provider = Mock()
            mock_class.return_value = mock_provider

            provider1 = get_session_provider()
            self.assertEqual(provider1, mock_provider)
            mock_class.assert_called_once()

        # Getting again should return same instance
        provider2 = get_session_provider()
        self.assertEqual(provider1, provider2)

    def test_notification_service_lifecycle(self):
        """Test getting notification service."""
        with patch(
            "apps.serp_execution.dependencies.DefaultNotificationService"
        ) as mock_class:
            mock_service = Mock()
            mock_class.return_value = mock_service

            service = get_notification_service()
            self.assertEqual(service, mock_service)

    def test_reset_providers(self):
        """Test resetting all providers."""
        # Get providers to populate cache
        get_session_provider()
        get_notification_service()

        # Reset all
        reset_providers()

        # All should create new defaults
        with patch(
            "apps.serp_execution.dependencies.DefaultSessionProvider"
        ) as mock_session:
            mock_session.return_value = Mock()

            get_session_provider()
            mock_session.assert_called_once()

    def test_concurrent_session_provider_returns_single_instance(self):
        """Concurrent calls must produce exactly one provider instance."""
        results = []
        barrier = threading.Barrier(4)

        def get_provider():
            barrier.wait()
            results.append(get_session_provider())

        threads = [threading.Thread(target=get_provider) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 4)
        self.assertTrue(all(r is results[0] for r in results))

    def test_concurrent_notification_service_returns_single_instance(self):
        """Concurrent calls must produce exactly one notification service."""
        results = []
        barrier = threading.Barrier(4)

        def get_service():
            barrier.wait()
            results.append(get_notification_service())

        threads = [threading.Thread(target=get_service) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 4)
        self.assertTrue(all(r is results[0] for r in results))


class TestDefaultProviders(TestCase):
    """Test default provider implementations."""

    @patch("apps.review_manager.models.SearchSession")
    def test_default_session_provider(self, mock_model):
        """Test DefaultSessionProvider implementation."""
        from apps.serp_execution.dependencies import DefaultSessionProvider

        provider = DefaultSessionProvider()
        session_id = str(uuid4())
        mock_session = Mock()
        mock_model.objects.get.return_value = mock_session

        # Test get_session
        result = provider.get_session(session_id)
        self.assertEqual(result, mock_session)
        mock_model.objects.get.assert_called_once_with(id=session_id)
