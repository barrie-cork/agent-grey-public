"""
Management command to check Docker container health status.
Part of the Docker health check improvements (PRP implementation).
"""

import json
import os
import subprocess
from typing import Any, Dict, List

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Check Docker container health status for all Agent Grey services"

    def add_arguments(self, parser):
        parser.add_argument(
            "--compose-file",
            type=str,
            default="docker-compose.dev.yml",
            help="Docker Compose file to use (default: docker-compose.dev.yml)",
        )
        parser.add_argument(
            "--json", action="store_true", help="Output results in JSON format"
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Attempt to fix unhealthy containers by restarting them",
        )

    def handle(self, *args, **options):
        compose_file = options["compose_file"]
        output_json = options["json"]
        attempt_fix = options["fix"]

        # Get container status
        containers = self.get_container_status(compose_file)

        if not containers:
            self.stdout.write(
                self.style.ERROR("No containers found. Is Docker running?")
            )
            return False

        # Categorize containers by health status
        health_categories = self._categorize_containers(containers)

        # Output results
        self._output_results(health_categories, len(containers), output_json)

        # Apply fixes if requested
        if attempt_fix:
            self._attempt_fixes(compose_file, health_categories["unhealthy"])

        # Exit with appropriate code
        self._exit_with_status(health_categories["unhealthy"])

    def _categorize_containers(self, containers):
        """Categorize containers by health status."""
        unhealthy = []
        healthy = []
        starting = []
        no_health_check = []

        for container in containers:
            name = container.get("Service", "unknown")
            status = container.get("Status", "")
            health = container.get("Health", "")

            # Check unhealthy first since "unhealthy" contains "healthy"
            if "unhealthy" in health.lower():
                unhealthy.append({"name": name, "status": status, "health": health})
            elif "healthy" in health.lower():
                healthy.append(name)
            elif "starting" in health.lower():
                starting.append(name)
            elif health == "":
                no_health_check.append(name)

        return {
            "unhealthy": unhealthy,
            "healthy": healthy,
            "starting": starting,
            "no_health_check": no_health_check,
        }

    def _output_results(self, health_categories, total_containers, output_json):
        """Output health check results in requested format."""
        if output_json:
            result = {
                "timestamp": timezone.now().isoformat(),
                "healthy": health_categories["healthy"],
                "unhealthy": [c["name"] for c in health_categories["unhealthy"]],
                "starting": health_categories["starting"],
                "no_health_check": health_categories["no_health_check"],
                "total": total_containers,
            }
            self.stdout.write(json.dumps(result, indent=2))
        else:
            self.print_status_report(
                health_categories["healthy"],
                health_categories["unhealthy"],
                health_categories["starting"],
                health_categories["no_health_check"],
                total_containers,
            )

    def _attempt_fixes(self, compose_file, unhealthy_containers):
        """Attempt to fix unhealthy containers by restarting them."""
        if not unhealthy_containers:
            return

        self.stdout.write(
            self.style.WARNING(
                f"\n🔧 Attempting to fix {len(unhealthy_containers)} unhealthy containers..."
            )
        )
        for container in unhealthy_containers:
            self.restart_container(compose_file, container["name"])

    def _exit_with_status(self, unhealthy_containers):
        """Exit with appropriate status code based on health check results."""
        if unhealthy_containers:
            import sys

            sys.exit(1)

    def get_docker_command(self) -> List[str]:
        """Determine the appropriate Docker command based on environment."""
        # Check if running inside a Docker container
        if os.path.exists("/.dockerenv"):
            # Inside container - use docker directly (requires docker.sock mount)
            # This would need additional configuration to work properly
            self.stdout.write(
                self.style.WARNING(
                    "Running inside container. Docker commands may not work without docker.sock mount."
                )
            )
            return ["docker"]
        else:
            # On host - use docker-compose
            return ["docker-compose"]

    def get_container_status(self, compose_file: str) -> List[Dict[str, Any]]:
        """Get status of all containers from docker-compose."""
        docker_cmd = self.get_docker_command()

        try:
            # Build command based on environment
            if docker_cmd[0] == "docker":
                # Use docker ps directly inside container
                cmd = ["docker", "ps", "--format", "json", "--all"]
            else:
                # Use docker-compose on host
                cmd = docker_cmd + ["-f", compose_file, "ps", "--format", "json"]

            # Run command
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            if result.stdout:
                # Parse JSON output
                containers = json.loads(result.stdout)
                return containers if isinstance(containers, list) else [containers]

            # Fallback to regular ps if JSON not available
            if docker_cmd[0] == "docker":
                cmd = ["docker", "ps", "--all"]
            else:
                cmd = docker_cmd + ["-f", compose_file, "ps"]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Parse text output (less reliable but works)
            return self.parse_text_output(result.stdout)

        except subprocess.CalledProcessError as e:
            self.stdout.write(self.style.ERROR(f"Failed to get container status: {e}"))
            return []
        except json.JSONDecodeError:
            # Try parsing as text
            return self.parse_text_output(result.stdout)

    def parse_text_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse text output from docker-compose ps."""
        containers = []
        lines = output.strip().split("\n")

        # Skip header lines
        for line in lines[2:]:  # Skip header and separator
            if line.strip():
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[0]
                    # Extract service name from container name
                    service = name.split("-")[-2] if "-" in name else name

                    # Check if health status is in the line
                    health = ""
                    if "(healthy)" in line:
                        health = "healthy"
                    elif "(unhealthy)" in line:
                        health = "unhealthy"
                    elif "(health: starting)" in line:
                        health = "starting"

                    containers.append(
                        {
                            "Service": service,
                            "Name": name,
                            "Status": " ".join(parts[1:]),
                            "Health": health,
                        }
                    )

        return containers

    def print_status_report(
        self,
        healthy: List[str],
        unhealthy: List[Dict],
        starting: List[str],
        no_health_check: List[str],
        total: int,
    ):
        """Print a formatted status report."""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("🐳 Docker Health Status Report"))
        self.stdout.write("=" * 50)
        self.stdout.write(f"Timestamp: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"Total containers: {total}\n")

        # Healthy containers
        if healthy:
            self.stdout.write(self.style.SUCCESS(f"✅ Healthy ({len(healthy)}):"))
            for service in healthy:
                self.stdout.write(f"   • {service}")

        # Starting containers
        if starting:
            self.stdout.write(self.style.WARNING(f"\n⏳ Starting ({len(starting)}):"))
            for service in starting:
                self.stdout.write(f"   • {service}")

        # Unhealthy containers
        if unhealthy:
            self.stdout.write(self.style.ERROR(f"\n❌ Unhealthy ({len(unhealthy)}):"))
            for container in unhealthy:
                self.stdout.write(f"   • {container['name']}")
                self.stdout.write(f"     Status: {container['status']}")

        # No health check
        if no_health_check:
            self.stdout.write(
                self.style.WARNING(f"\n⚠️  No health check ({len(no_health_check)}):")
            )
            for service in no_health_check:
                self.stdout.write(f"   • {service}")

        # Summary
        self.stdout.write("\n" + "=" * 50)
        if unhealthy:
            self.stdout.write(
                self.style.ERROR(f"⚠️  {len(unhealthy)} services need attention!")
            )
            self.stdout.write("Run with --fix to attempt automatic recovery")
        else:
            self.stdout.write(
                self.style.SUCCESS("✨ All services with health checks are healthy!")
            )
        self.stdout.write("=" * 50 + "\n")

    def restart_container(self, compose_file: str, service_name: str):
        """Restart a specific container."""
        docker_cmd = self.get_docker_command()

        try:
            self.stdout.write(f"   Restarting {service_name}...")

            if docker_cmd[0] == "docker":
                # Use docker restart directly
                cmd = ["docker", "restart", service_name]
            else:
                # Use docker-compose restart
                cmd = docker_cmd + ["-f", compose_file, "restart", service_name]

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            self.stdout.write(self.style.SUCCESS(f"   ✅ {service_name} restarted"))
        except subprocess.CalledProcessError as e:
            self.stdout.write(
                self.style.ERROR(f"   ❌ Failed to restart {service_name}: {e}")
            )
        except subprocess.TimeoutExpired:
            self.stdout.write(
                self.style.ERROR(f"   ❌ Timeout restarting {service_name}")
            )
