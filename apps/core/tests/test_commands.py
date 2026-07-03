"""
Tests for management commands in the core app.
"""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase


class TestDockerHealthCommand(TestCase):
    """Test the check_docker_health management command."""

    def setUp(self):
        """Set up test fixtures."""
        self.healthy_containers_json = [
            {
                "Service": "web",
                "Name": "agent-grey-web-1",
                "Status": "Up 5 minutes",
                "Health": "healthy",
            },
            {
                "Service": "db",
                "Name": "agent-grey-db-1",
                "Status": "Up 10 minutes",
                "Health": "",
            },
        ]

        self.unhealthy_containers_json = [
            {
                "Service": "web",
                "Name": "agent-grey-web-1",
                "Status": "Up 5 minutes",
                "Health": "healthy",
            },
            {
                "Service": "celery_worker",
                "Name": "agent-grey-celery-1",
                "Status": "Up 3 minutes",
                "Health": "unhealthy",
            },
        ]

    @patch("apps.core.management.commands.check_docker_health.subprocess.run")
    @patch("os.path.exists")
    def test_command_with_healthy_containers(self, mock_exists, mock_run):
        """Test command execution with all healthy containers."""
        # Mock that we're not in a container
        mock_exists.return_value = False

        # Mock successful docker-compose command with healthy containers
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(self.healthy_containers_json)
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Capture output
        out = StringIO()

        # Run command - should NOT raise SystemExit (all healthy)
        call_command("check_docker_health", stdout=out)

        # Verify docker-compose was called
        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "docker-compose")

        # Check output contains expected information
        output = out.getvalue()
        self.assertIn("Docker Health Status Report", output)
        self.assertIn("All services with health checks are healthy", output)

    @patch("apps.core.management.commands.check_docker_health.subprocess.run")
    @patch("os.path.exists")
    def test_command_with_unhealthy_containers(self, mock_exists, mock_run):
        """Test command execution with unhealthy containers."""
        # Mock that we're not in a container
        mock_exists.return_value = False

        # Mock docker-compose command with unhealthy containers
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(self.unhealthy_containers_json)
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Capture output
        out = StringIO()

        # Run command - should raise SystemExit due to unhealthy container
        with self.assertRaises(SystemExit) as cm:
            call_command("check_docker_health", stdout=out)

        # Check exit code is 1 (unhealthy)
        self.assertEqual(cm.exception.code, 1)

        # Check output contains expected information
        output = out.getvalue()
        self.assertIn("Docker Health Status Report", output)
        self.assertIn("Unhealthy", output)
        self.assertIn("celery_worker", output)

    @patch("apps.core.management.commands.check_docker_health.subprocess.run")
    @patch("os.path.exists")
    def test_command_in_container_warning(self, mock_exists, mock_run):
        """Test command execution inside a container shows warning."""
        # Mock that we're inside a container
        mock_exists.return_value = True

        # Mock docker ps command
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(self.healthy_containers_json)
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Capture output
        out = StringIO()

        # Run command
        call_command("check_docker_health", stdout=out)

        # Verify docker was called (not docker-compose)
        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "docker")

        # Check for warning about running in container
        output = out.getvalue()
        self.assertIn("Running inside container", output)

    @patch("apps.core.management.commands.check_docker_health.subprocess.run")
    @patch("os.path.exists")
    def test_json_output_format(self, mock_exists, mock_run):
        """Test JSON output format."""
        mock_exists.return_value = False

        # Mock successful docker-compose command
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(self.healthy_containers_json)
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Capture output
        out = StringIO()

        # Run command with JSON flag
        call_command("check_docker_health", "--json", stdout=out)

        # Parse JSON output
        output = out.getvalue()
        result_json = json.loads(output)

        # Verify JSON structure
        self.assertIn("healthy", result_json)
        self.assertIn("unhealthy", result_json)
        self.assertIn("no_health_check", result_json)
        self.assertIn("timestamp", result_json)
        self.assertIn("total", result_json)

        # Check counts
        self.assertEqual(len(result_json["healthy"]), 1)
        self.assertEqual(len(result_json["unhealthy"]), 0)
        self.assertEqual(len(result_json["no_health_check"]), 1)

    @patch("apps.core.management.commands.check_docker_health.subprocess.run")
    @patch("os.path.exists")
    def test_docker_not_running(self, mock_exists, mock_run):
        """Test handling when Docker is not running."""
        mock_exists.return_value = False

        # Mock subprocess error
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "docker-compose")

        # Capture output
        out = StringIO()

        # Run command - should handle error gracefully
        call_command("check_docker_health", stdout=out)

        # Check error message
        output = out.getvalue()
        self.assertIn("Failed to get container status", output)

    @patch("apps.core.management.commands.check_docker_health.subprocess.run")
    @patch("os.path.exists")
    def test_text_output_fallback(self, mock_exists, mock_run):
        """Test fallback to text parsing when JSON is not available."""
        mock_exists.return_value = False

        # First call returns empty JSON
        mock_result1 = MagicMock()
        mock_result1.stdout = ""
        mock_result1.returncode = 0

        # Second call returns text output
        mock_result2 = MagicMock()
        mock_result2.stdout = """
NAME                       STATUS          PORTS
agent-grey-web-1          Up 5 minutes    0.0.0.0:8000->8000/tcp (healthy)
agent-grey-db-1           Up 10 minutes   5432/tcp
"""
        mock_result2.returncode = 0

        mock_run.side_effect = [mock_result1, mock_result2]

        # Capture output
        out = StringIO()

        # Run command - should work with text fallback
        call_command("check_docker_health", stdout=out)

        # Verify both JSON and text commands were tried
        self.assertEqual(mock_run.call_count, 2)

        # Check output contains parsed information
        output = out.getvalue()
        self.assertIn("Docker Health Status Report", output)
