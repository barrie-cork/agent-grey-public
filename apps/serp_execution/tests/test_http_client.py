"""
Tests for the HTTPClient service.
"""

from unittest.mock import Mock, patch

import requests
from django.test import TestCase

from apps.core.services.http_client import HTTPClient


class HTTPClientTests(TestCase):
    """Tests for HTTPClient class."""

    def setUp(self):
        self.base_url = "https://api.example.com"
        self.api_key = "test-api-key"
        self.http_client = HTTPClient(
            base_url=self.base_url, api_key=self.api_key, timeout=10, max_retries=2
        )

    def test_initialization(self):
        """Test HTTPClient initialization."""
        self.assertEqual(self.http_client.base_url, self.base_url)
        self.assertEqual(self.http_client.api_key, self.api_key)
        self.assertEqual(self.http_client.timeout, 10)
        self.assertEqual(self.http_client.max_retries, 2)

        # Check session headers
        self.assertEqual(self.http_client.session.headers["X-API-KEY"], self.api_key)
        self.assertEqual(
            self.http_client.session.headers["Content-Type"], "application/json"
        )

    def test_initialization_with_config_defaults(self):
        """Test HTTPClient initialization using config defaults."""
        # Create without timeout and max_retries - should use config
        client = HTTPClient(base_url=self.base_url, api_key=self.api_key)

        # Should have values from config
        self.assertGreater(client.timeout, 0)
        self.assertGreater(client.max_retries, 0)

    @patch("requests.Session.get")
    def test_get_request_success(self, mock_get):
        """Test successful GET request."""
        # Mock successful response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Make request
        response = self.http_client.get("/test", params={"key": "value"})

        # Verify call
        mock_get.assert_called_once_with(
            f"{self.base_url}/test", params={"key": "value"}, timeout=10
        )
        self.assertEqual(response, mock_response)

    @patch("requests.Session.get")
    def test_get_request_with_empty_endpoint(self, mock_get):
        """Test GET request with empty endpoint."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Make request with empty endpoint
        self.http_client.get("", params={"key": "value"})

        # Should use base URL only
        mock_get.assert_called_once_with(
            self.base_url, params={"key": "value"}, timeout=10
        )

    @patch("requests.Session.get")
    def test_get_request_timeout(self, mock_get):
        """Test GET request timeout handling."""
        # Mock timeout exception
        mock_get.side_effect = requests.exceptions.Timeout()

        # Should raise timeout exception
        with self.assertRaises(requests.exceptions.Timeout):
            self.http_client.get("/test")

    @patch("requests.Session.post")
    def test_post_request_with_json(self, mock_post):
        """Test successful POST request with JSON."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        json_data = {"key": "value"}
        response = self.http_client.post("/test", json_data=json_data)

        mock_post.assert_called_once_with(
            f"{self.base_url}/test", json=json_data, data=None, timeout=10
        )
        self.assertEqual(response, mock_response)

    @patch("requests.Session.post")
    def test_post_request_with_form_data(self, mock_post):
        """Test successful POST request with form data."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        form_data = {"key": "value"}
        response = self.http_client.post("/test", data=form_data)

        mock_post.assert_called_once_with(
            f"{self.base_url}/test", json=None, data=form_data, timeout=10
        )
        self.assertEqual(response, mock_response)

    @patch("requests.Session.post")
    def test_post_request_error(self, mock_post):
        """Test POST request error handling."""
        # Mock request exception
        mock_post.side_effect = requests.exceptions.RequestException("Network error")

        with self.assertRaises(requests.exceptions.RequestException):
            self.http_client.post("/test", json_data={"key": "value"})

    def test_close_session(self):
        """Test closing the session."""
        # Mock the session close method
        with patch.object(self.http_client.session, "close") as mock_close:
            self.http_client.close()
            mock_close.assert_called_once()

    def test_session_configuration(self):
        """Test that session is configured with retry logic."""
        # Verify session has adapters mounted
        adapters = self.http_client.session.adapters
        self.assertIn("http://", adapters)
        self.assertIn("https://", adapters)

        # Verify adapters have retry configuration
        http_adapter = adapters["http://"]
        https_adapter = adapters["https://"]

        self.assertIsNotNone(http_adapter.max_retries)  # type: ignore[attr-defined]
        self.assertIsNotNone(https_adapter.max_retries)  # type: ignore[attr-defined]
