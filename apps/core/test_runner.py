"""Custom test runner with DB connection cleanup."""

from django.db import close_old_connections
from django.test.runner import DiscoverRunner


class ConnectionCleanupTestRunner(DiscoverRunner):
    """Closes stale DB connections between test suites."""

    def run_suite(self, suite, **kwargs):
        result = super().run_suite(suite, **kwargs)
        close_old_connections()
        return result

    def teardown_test_environment(self, **kwargs):
        close_old_connections()
        super().teardown_test_environment(**kwargs)
