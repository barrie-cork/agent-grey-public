"""
Tests for provider implementations in review_results app.

This module tests the concrete provider implementations that implement
the interfaces for cross-app communication.
"""

from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import TestCase

from apps.review_results.interfaces import IResultsProvider, ISessionProvider
from apps.review_results.providers import (
    DjangoResultsProvider,
    DjangoSessionProvider,
    get_results_provider,
    get_session_provider,
)


class TestDjangoResultsProvider(TestCase):
    """Test the Django ORM-based results provider implementation."""

    def setUp(self):
        """Set up test data."""
        self.provider = DjangoResultsProvider()
        self.session_id = uuid4()
        self.result_id = uuid4()

    @patch("apps.review_results.providers.apps.get_model")
    def test_get_results_for_session(self, mock_get_model):
        """Test retrieving results for a session."""
        # Mock the ProcessedResult model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock the queryset
        mock_result1 = Mock(id=uuid4())
        mock_result2 = Mock(id=uuid4())
        mock_filter = Mock()
        mock_prefetch = Mock()
        mock_order = [mock_result1, mock_result2]

        # Set up the chained calls correctly
        mock_model.objects.filter.return_value = mock_filter
        mock_filter.prefetch_related.return_value = mock_prefetch
        mock_prefetch.order_by.return_value = mock_order

        # Test the method
        results = self.provider.get_results_for_session(self.session_id)

        # Verify the calls
        mock_get_model.assert_called_with("results_manager", "ProcessedResult")
        mock_model.objects.filter.assert_called_with(
            session_id=self.session_id, processing_status="success", is_hidden=False
        )
        mock_filter.prefetch_related.assert_called_with("simplereviewdecision")
        mock_prefetch.order_by.assert_called_with("-processed_at")

        # Check results
        self.assertEqual(len(results), 2)
        self.assertEqual(results, [mock_result1, mock_result2])

    @patch("apps.review_results.providers.apps.get_model")
    def test_get_result_by_id_found(self, mock_get_model):
        """Test retrieving a specific result by ID when it exists."""
        # Mock the ProcessedResult model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock the result
        mock_result = Mock(id=self.result_id)
        mock_model.objects.get.return_value = mock_result

        # Test the method
        result = self.provider.get_result_by_id(self.result_id, self.session_id)

        # Verify the calls
        mock_model.objects.get.assert_called_with(
            id=self.result_id, session_id=self.session_id
        )

        # Check result
        self.assertEqual(result, mock_result)

    @patch("apps.review_results.providers.apps.get_model")
    def test_get_result_by_id_not_found(self, mock_get_model):
        """Test retrieving a specific result by ID when it doesn't exist."""
        # Mock the ProcessedResult model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock DoesNotExist exception
        mock_model.DoesNotExist = Exception
        mock_model.objects.get.side_effect = mock_model.DoesNotExist

        # Test the method
        result = self.provider.get_result_by_id(self.result_id, self.session_id)

        # Check result
        self.assertIsNone(result)

    @patch("apps.review_results.providers.apps.get_model")
    def test_mark_result_as_reviewed_success(self, mock_get_model):
        """Test marking a result as reviewed successfully."""
        # Mock the ProcessedResult model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock the result
        mock_result = Mock()
        mock_model.objects.get.return_value = mock_result

        # Test the method
        success = self.provider.mark_result_as_reviewed(self.result_id)

        # Verify the calls
        mock_model.objects.get.assert_called_with(id=self.result_id)
        mock_result.save.assert_called_with(update_fields=["is_reviewed"])

        # Check result
        self.assertTrue(success)
        self.assertTrue(mock_result.is_reviewed)

    @patch("apps.review_results.providers.apps.get_model")
    def test_mark_result_as_reviewed_not_found(self, mock_get_model):
        """Test marking a result as reviewed when it doesn't exist."""
        # Mock the ProcessedResult model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock DoesNotExist exception
        mock_model.DoesNotExist = Exception
        mock_model.objects.get.side_effect = mock_model.DoesNotExist

        # Test the method
        success = self.provider.mark_result_as_reviewed(self.result_id)

        # Check result
        self.assertFalse(success)

    def test_implements_interface(self):
        """Test that DjangoResultsProvider implements IResultsProvider."""
        self.assertIsInstance(self.provider, IResultsProvider)

    @patch("apps.review_results.providers.apps.get_model")
    def test_get_results_queryset_for_session_returns_queryset(self, mock_get_model):
        """Test that get_results_queryset_for_session returns a queryset, not a list."""
        # Mock the ProcessedResult model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock the queryset chain (NOT converting to list)
        mock_queryset = Mock()
        mock_filter = Mock()
        mock_prefetch = Mock()

        mock_model.objects.filter.return_value = mock_filter
        mock_filter.prefetch_related.return_value = mock_prefetch
        mock_prefetch.order_by.return_value = mock_queryset

        # Test the method
        result = self.provider.get_results_queryset_for_session(self.session_id)

        # Verify the calls
        mock_get_model.assert_called_with("results_manager", "ProcessedResult")
        mock_model.objects.filter.assert_called_with(
            session_id=self.session_id, processing_status="success", is_hidden=False
        )
        mock_filter.prefetch_related.assert_called_with("simplereviewdecision")
        mock_prefetch.order_by.assert_called_with("-processed_at")

        # Critical: Should return queryset, not list
        self.assertEqual(result, mock_queryset)
        # Ensure list() was NOT called (the queryset is returned as-is)
        self.assertNotIsInstance(result, list)


class TestDjangoSessionProvider(TestCase):
    """Test the Django ORM-based session provider implementation."""

    def setUp(self):
        """Set up test data."""
        self.provider = DjangoSessionProvider()
        self.session_id = uuid4()
        self.owner_id = uuid4()

    @patch("apps.review_results.providers.apps.get_model")
    def test_get_session_found(self, mock_get_model):
        """Test retrieving a session when it exists."""
        # Mock the SearchSession model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock the session
        mock_session = Mock(id=self.session_id)
        mock_model.objects.get.return_value = mock_session

        # Test the method
        session = self.provider.get_session(self.session_id)

        # Verify the calls
        mock_get_model.assert_called_with("review_manager", "SearchSession")
        mock_model.objects.get.assert_called_with(id=self.session_id)

        # Check result
        self.assertEqual(session, mock_session)

    @patch("apps.review_results.providers.apps.get_model")
    def test_get_session_not_found(self, mock_get_model):
        """Test retrieving a session when it doesn't exist."""
        # Mock the SearchSession model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock DoesNotExist exception
        mock_model.DoesNotExist = Exception
        mock_model.objects.get.side_effect = mock_model.DoesNotExist

        # Test the method
        session = self.provider.get_session(self.session_id)

        # Check result
        self.assertIsNone(session)

    @patch("apps.review_results.providers.apps.get_model")
    def test_get_session_owner_id_found(self, mock_get_model):
        """Test retrieving session owner ID when session exists."""
        # Mock the SearchSession model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock the session with only owner_id
        mock_session = Mock(owner_id=self.owner_id)
        mock_queryset = Mock()
        mock_queryset.only.return_value.get.return_value = mock_session
        mock_model.objects = mock_queryset

        # Test the method
        owner_id = self.provider.get_session_owner_id(self.session_id)

        # Verify the calls
        mock_queryset.only.assert_called_with("owner_id")
        mock_queryset.only.return_value.get.assert_called_with(id=self.session_id)

        # Check result
        self.assertEqual(owner_id, self.owner_id)

    @patch("apps.review_results.providers.apps.get_model")
    def test_get_session_owner_id_not_found(self, mock_get_model):
        """Test retrieving session owner ID when session doesn't exist."""
        # Mock the SearchSession model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock DoesNotExist exception
        mock_model.DoesNotExist = Exception
        mock_queryset = Mock()
        mock_queryset.only.return_value.get.side_effect = mock_model.DoesNotExist
        mock_model.objects = mock_queryset

        # Test the method
        owner_id = self.provider.get_session_owner_id(self.session_id)

        # Check result
        self.assertIsNone(owner_id)

    @patch("apps.review_results.providers.apps.get_model")
    def test_update_session_status_success(self, mock_get_model):
        """Test updating session status successfully."""
        # Mock the SearchSession model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock the update
        mock_queryset = Mock()
        mock_queryset.filter.return_value.update.return_value = 1
        mock_model.objects = mock_queryset

        # Test the method
        success = self.provider.update_session_status(self.session_id, "completed")

        # Verify the calls
        mock_queryset.filter.assert_called_with(id=self.session_id)
        mock_queryset.filter.return_value.update.assert_called_with(status="completed")

        # Check result
        self.assertTrue(success)

    @patch("apps.review_results.providers.apps.get_model")
    def test_update_session_status_failure(self, mock_get_model):
        """Test updating session status when it fails."""
        # Mock the SearchSession model
        mock_model = Mock()
        mock_get_model.return_value = mock_model

        # Mock the update failure
        mock_queryset = Mock()
        mock_queryset.filter.return_value.update.side_effect = Exception(
            "Update failed"
        )
        mock_model.objects = mock_queryset

        # Test the method
        success = self.provider.update_session_status(self.session_id, "completed")

        # Check result
        self.assertFalse(success)

    def test_implements_interface(self):
        """Test that DjangoSessionProvider implements ISessionProvider."""
        self.assertIsInstance(self.provider, ISessionProvider)


class TestProviderFactories(TestCase):
    """Test the factory functions for getting provider instances."""

    def test_get_results_provider(self):
        """Test getting a results provider instance."""
        provider = get_results_provider()
        self.assertIsInstance(provider, DjangoResultsProvider)
        self.assertIsInstance(provider, IResultsProvider)

    def test_get_session_provider(self):
        """Test getting a session provider instance."""
        provider = get_session_provider()
        self.assertIsInstance(provider, DjangoSessionProvider)
        self.assertIsInstance(provider, ISessionProvider)
