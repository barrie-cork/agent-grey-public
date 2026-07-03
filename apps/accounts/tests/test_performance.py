#!/usr/bin/env python
"""
Performance Tests for Accounts App
Tests: Performance and load testing
Based on: Accounts_ComprehensiveTestStrategy_20250808_1200.md
"""

import concurrent.futures
import time

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import Client, TransactionTestCase
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class AccountsPerformanceTests(TransactionTestCase):
    """Performance and load testing for Accounts app"""

    def tearDown(self):
        """Close all thread-local DB connections opened by ThreadPoolExecutor workers."""
        connections.close_all()
        super().tearDown()

    def test_login_response_time(self):
        """Test login response time < 200ms"""
        # Create test user
        user = create_test_user(username_prefix="perfuser")

        # Warm up
        self.client.post(
            reverse("accounts:login"),
            {"email": user.email, "password": "testpass123"},
        )

        # Measure actual request
        start = time.time()
        response = self.client.post(
            reverse("accounts:login"),
            {"email": user.email, "password": "testpass123"},
        )
        duration = time.time() - start

        # Should be under 200ms (relaxed to 500ms for test environment)
        self.assertLess(duration, 0.5, f"Login took {duration:.3f}s, expected < 0.5s")
        self.assertEqual(response.status_code, 302)

    def test_registration_response_time(self):
        """Test registration response time < 500ms"""
        start = time.time()
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": f"user_{int(time.time())}",
                "email": f"user_{int(time.time())}@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        duration = time.time() - start

        # Should be under 500ms (relaxed to 1s for test environment)
        self.assertLess(
            duration, 1.0, f"Registration took {duration:.3f}s, expected < 1s"
        )
        self.assertEqual(response.status_code, 302)

    def test_profile_update_response_time(self):
        """Test profile update response time < 300ms"""
        perf_user = create_test_user(username_prefix="profileperfuser")

        self.client.login(username=perf_user.username, password="testpass123")

        start = time.time()
        _response = self.client.post(
            reverse("accounts:profile"),
            {
                "email": "updated@example.com",
                "first_name": "Updated",
                "last_name": "Name",
            },
        )
        duration = time.time() - start

        # Should be under 300ms (relaxed to 500ms for test environment)
        self.assertLess(
            duration, 0.5, f"Profile update took {duration:.3f}s, expected < 0.5s"
        )

    def test_password_reset_request_response_time(self):
        """Test password reset request response time < 200ms"""
        create_test_user(username_prefix="resetperfuser")

        start = time.time()
        _response = self.client.post(
            reverse("accounts:password_reset"), {"email": "resetperf@example.com"}
        )
        duration = time.time() - start

        # Should be under 200ms (relaxed to 500ms for test environment)
        self.assertLess(
            duration, 0.5, f"Password reset took {duration:.3f}s, expected < 0.5s"
        )

    def test_bulk_user_creation_performance(self):
        """Test creating 100 users performance < 1s per 100 users"""
        start = time.time()

        users = []
        for i in range(100):
            users.append(User(username=f"bulkuser{i}", email=f"bulk{i}@example.com"))

        User.objects.bulk_create(users)

        duration = time.time() - start

        # Should be under 1 second for 100 users (relaxed to 2s for test environment)
        self.assertLess(
            duration, 2.0, f"Bulk creation took {duration:.3f}s, expected < 2s"
        )

        # Verify users were created
        self.assertEqual(
            User.objects.filter(username__startswith="bulkuser").count(), 100
        )

    def test_user_lookup_by_email_performance(self):
        """Test user lookup by email < 50ms"""
        # Create test user
        user = create_test_user(username_prefix="lookupuser")

        # Warm up database
        User.objects.get(email=user.email)

        # Measure lookup time
        start = time.time()
        found_user = User.objects.get(email=user.email)
        duration = time.time() - start

        # Should be under 50ms (relaxed to 100ms for test environment)
        self.assertLess(
            duration, 0.1, f"Email lookup took {duration:.3f}s, expected < 0.1s"
        )
        self.assertEqual(found_user.id, user.id)

    def test_user_lookup_by_username_performance(self):
        """Test user lookup by username < 50ms"""
        # Create test user
        user = create_test_user(username_prefix="lookupuser2")

        # Warm up database
        User.objects.get(username=user.username)

        # Measure lookup time
        start = time.time()
        found_user = User.objects.get(username=user.username)
        duration = time.time() - start

        # Should be under 50ms (relaxed to 100ms for test environment)
        self.assertLess(
            duration, 0.1, f"Username lookup took {duration:.3f}s, expected < 0.1s"
        )
        self.assertEqual(found_user.id, user.id)

    def test_concurrent_login_load(self):
        """Test system under concurrent login load"""
        # Create test user
        user = create_test_user(username_prefix="loaduser")
        user_email = user.email

        def attempt_login():
            connection.close()
            try:
                client = Client()
                response = client.post(
                    reverse("accounts:login"),
                    {"email": user_email, "password": "testpass123"},
                )
                return response.status_code
            finally:
                connection.close()

        # Simulate 10 concurrent login attempts
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            start = time.time()
            futures = [executor.submit(attempt_login) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
            duration = time.time() - start

        # All should succeed
        self.assertTrue(all(status == 302 for status in results))

        # Should handle 10 concurrent requests in reasonable time
        self.assertLess(duration, 5.0, f"Concurrent logins took {duration:.3f}s")

    def test_database_query_optimization(self):
        """Test that queries are optimized (no N+1 problems)"""
        # Create test users
        for i in range(10):
            create_test_user()

        # Reset queries
        from django.conf import settings
        from django.db import reset_queries

        # Temporarily enable debug to count queries
        original_debug = settings.DEBUG
        settings.DEBUG = True
        reset_queries()

        try:
            # Fetch all users
            _users = list(User.objects.all())

            # Should be a single query
            query_count = len(connection.queries)

            # Should use minimal queries (1-2 expected)
            self.assertLessEqual(
                query_count, 2, f"Too many queries: {query_count}, expected <= 2"
            )
        finally:
            settings.DEBUG = original_debug
