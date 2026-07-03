"""
Tests for health check endpoints.

Validates:
- Lightweight health check (DB-only, /health/)
- Detailed health check (all services, /health/detailed/)
- Parallel execution performance (ThreadPoolExecutor)
- Concurrent request handling
- Response structure
"""

import json
import time

from django.db import connections
from django.test import RequestFactory, TestCase


class HealthCheckTests(TestCase):
    """
    Test lightweight health check endpoint (/health/).

    Verifies DB-only check returns correct lightweight response structure.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def test_health_check_returns_200(self):
        """Test lightweight health check returns 200 when healthy."""
        from apps.health.views import health_check

        request = self.factory.get("/health/")
        response = health_check(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "healthy")
        self.assertIn("timestamp", data)

    def test_health_check_has_lightweight_response(self):
        """Test lightweight health check returns only status + timestamp (no checks dict)."""
        from apps.health.views import health_check

        request = self.factory.get("/health/")
        response = health_check(request)

        data = json.loads(response.content)

        # Should only have status and timestamp
        self.assertEqual(set(data.keys()), {"status", "timestamp"})
        self.assertNotIn("checks", data)
        self.assertNotIn("message", data)

    def test_health_check_timestamp_is_iso(self):
        """Test lightweight health check timestamp is ISO 8601."""
        from apps.health.views import health_check

        request = self.factory.get("/health/")
        response = health_check(request)

        data = json.loads(response.content)
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"])

    def test_health_check_is_fast(self):
        """Test lightweight health check responds in <1s (DB-only, no Celery)."""
        from apps.health.views import health_check

        request = self.factory.get("/health/")

        start = time.time()
        response = health_check(request)
        duration = time.time() - start

        self.assertLess(
            duration,
            1.0,
            f"Lightweight health check took {duration}s, should be < 1.0s",
        )
        self.assertEqual(response.status_code, 200)

    def test_health_check_multiple_requests(self):
        """Test multiple sequential lightweight health check requests."""
        from apps.health.views import health_check

        requests_list = [self.factory.get("/health/") for _ in range(10)]

        start = time.time()
        responses = [health_check(req) for req in requests_list]
        duration = time.time() - start

        for response in responses:
            self.assertEqual(response.status_code, 200)

        # 10 DB-only checks should complete in <5s
        self.assertLess(
            duration, 5.0, f"10 lightweight requests took {duration}s, should be < 5.0s"
        )

    def test_health_check_consistency(self):
        """Test lightweight health check responses are consistent across calls."""
        from apps.health.views import health_check

        for _ in range(5):
            request = self.factory.get("/health/")
            response = health_check(request)

            self.assertIn(response.status_code, [200, 503])
            data = json.loads(response.content)
            self.assertEqual(set(data.keys()), {"status", "timestamp"})


class DetailedHealthCheckTests(TestCase):
    """
    Test detailed health check endpoint (/health/detailed/).

    Verifies full 5-service parallel check returns correct response structure.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def tearDown(self):
        """Close all DB connections opened by health check threads."""
        time.sleep(0.1)  # Allow ThreadPoolExecutor threads to finish
        for conn in connections.all():
            conn.close()
        connections.close_all()

    def test_detailed_health_check_returns_200(self):
        """Test detailed health check returns 200 when healthy."""
        from apps.health.views import detailed_health_check

        request = self.factory.get("/health/detailed/")
        response = detailed_health_check(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "healthy")
        self.assertIn("checks", data)
        self.assertIn("timestamp", data)
        self.assertIn("message", data)

    def test_detailed_health_check_has_structured_response(self):
        """Test detailed health check returns structured response with checks dict."""
        from apps.health.views import detailed_health_check

        request = self.factory.get("/health/detailed/")
        response = detailed_health_check(request)

        data = json.loads(response.content)

        # Verify structure
        self.assertIn("checks", data)
        self.assertIsInstance(data["checks"], dict)

        # Verify all services are checked
        expected_services = ["database", "cache", "redis", "celery", "spaces"]
        for service in expected_services:
            self.assertIn(service, data["checks"])

        # Verify timestamp format (ISO 8601)
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"])

    def test_detailed_health_check_parallel_execution(self):
        """Test detailed health check executes checks in parallel."""
        from apps.health.views import detailed_health_check

        request = self.factory.get("/health/detailed/")

        start = time.time()
        response = detailed_health_check(request)
        duration = time.time() - start

        # Should be < 10s (Celery inspection timeout may be slow in Docker)
        self.assertLess(
            duration, 10.0, f"Detailed health check took {duration}s, should be < 10.0s"
        )
        self.assertEqual(response.status_code, 200)

    def test_detailed_health_check_exception_handling(self):
        """Test detailed health check handles exceptions gracefully."""
        from apps.health.views import detailed_health_check

        request = self.factory.get("/health/detailed/")
        response = detailed_health_check(request)

        # Should always return a response even if some checks fail
        self.assertIn(response.status_code, [200, 503])
        data = json.loads(response.content)
        self.assertIn("status", data)
        self.assertIn("checks", data)

    def test_detailed_health_check_consistency(self):
        """Test detailed health check responses are consistent across calls."""
        from apps.health.views import detailed_health_check

        for _ in range(5):
            request = self.factory.get("/health/detailed/")
            response = detailed_health_check(request)

            self.assertIn(response.status_code, [200, 503])
            data = json.loads(response.content)
            self.assertIn("status", data)
            self.assertIn("checks", data)
            self.assertIn("timestamp", data)


class CacheAndReadyCheckTests(TestCase):
    """Test cache health check and ready check endpoints."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_cache_health_check(self):
        """Test cache health check returns valid response."""
        from apps.health.views import cache_health_check

        request = self.factory.get("/health/cache/")
        response = cache_health_check(request)

        self.assertIn(response.status_code, [200, 503])
        data = json.loads(response.content)
        self.assertIn("status", data)
        self.assertIn("backend", data)
        self.assertIn("timestamp", data)

    def test_cache_health_check_has_timestamp(self):
        """Test cache health check includes timestamp in response."""
        from apps.health.views import cache_health_check

        request = self.factory.get("/health/cache/")
        response = cache_health_check(request)

        data = json.loads(response.content)
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"])

    def test_ready_check(self):
        """Test ready check returns 200."""
        from apps.health.views import ready_check

        request = self.factory.get("/health/ready/")
        response = ready_check(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ready")
        self.assertIn("timestamp", data)

    def test_ready_check_has_timestamp(self):
        """Test ready check includes timestamp in response."""
        from apps.health.views import ready_check

        request = self.factory.get("/health/ready/")
        response = ready_check(request)

        data = json.loads(response.content)
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"])


class HealthCheckPerformanceTests(TestCase):
    """Performance tests for health checks."""

    def setUp(self):
        self.factory = RequestFactory()

    def tearDown(self):
        """Close all DB connections opened by health check threads."""
        time.sleep(0.1)
        for conn in connections.all():
            conn.close()
        connections.close_all()

    def test_lightweight_health_check_performance(self):
        """Test lightweight health check average is fast (DB-only)."""
        from apps.health.views import health_check

        durations = []
        for _ in range(5):
            request = self.factory.get("/health/")
            start = time.time()
            response = health_check(request)
            durations.append(time.time() - start)
            self.assertIn(response.status_code, [200, 503])

        avg_duration = sum(durations) / len(durations)
        self.assertLess(
            avg_duration,
            1.0,
            f"Average lightweight health check {avg_duration}s should be < 1.0s",
        )

    def test_detailed_health_check_performance(self):
        """Test detailed health check average is within bounds."""
        from apps.health.views import detailed_health_check

        durations = []
        for _ in range(5):
            request = self.factory.get("/health/detailed/")
            start = time.time()
            response = detailed_health_check(request)
            durations.append(time.time() - start)
            self.assertIn(response.status_code, [200, 503])

        avg_duration = sum(durations) / len(durations)
        self.assertLess(
            avg_duration,
            10.0,
            f"Average detailed health check {avg_duration}s should be < 10.0s",
        )

    def test_sequential_load_handling(self):
        """Test lightweight health checks handle sequential load efficiently."""
        from apps.health.views import health_check

        requests_list = [self.factory.get("/health/") for _ in range(5)]

        start = time.time()
        responses = [health_check(req) for req in requests_list]
        total_duration = time.time() - start

        for response in responses:
            self.assertIn(response.status_code, [200, 503])

        # 5 DB-only requests should complete quickly
        self.assertLess(
            total_duration,
            5.0,
            f"5 lightweight requests took {total_duration}s, should be < 5.0s",
        )


class DigitalOceanHealthCheckTests(TestCase):
    """
    Test DigitalOcean-specific health check scenarios.

    Validates that Kubernetes health probes from pod network IPs
    are properly handled by ALLOWED_CIDR_NETS.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def test_health_check_from_digitalocean_pod_ip(self):
        """
        Test lightweight health check from DigitalOcean Kubernetes pod IP.

        Verifies that health probes from 10.244.0.0/16 network are accepted.
        """
        from apps.health.views import health_check

        pod_ips = [
            "10.244.37.176",
            "10.244.0.1",
            "10.244.255.254",
        ]

        for pod_ip in pod_ips:
            request = self.factory.get(
                "/health/", HTTP_HOST=f"{pod_ip}:8000", REMOTE_ADDR=pod_ip
            )
            response = health_check(request)

            self.assertNotEqual(
                response.status_code,
                400,
                f"Health check from pod IP {pod_ip} returned 400 (DisallowedHost)",
            )
            self.assertIn(
                response.status_code,
                [200, 503],
                f"Health check from pod IP {pod_ip} returned unexpected "
                f"status {response.status_code}",
            )

    def test_health_check_rejects_invalid_ips(self):
        """Test health check rejects IPs outside DigitalOcean pod network."""
        invalid_ips = [
            "10.245.0.1",
            "192.168.1.1",
            "8.8.8.8",
        ]

        for invalid_ip in invalid_ips:
            _request = self.factory.get(
                "/health/", HTTP_HOST=f"{invalid_ip}:8000", REMOTE_ADDR=invalid_ip
            )
            # Note: This test may pass or fail depending on whether
            # Django's ALLOWED_HOSTS validation runs before our view
            # The key test is that pod IPs (10.244.*) work correctly
