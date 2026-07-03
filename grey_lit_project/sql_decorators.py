"""
SQL Logging Decorators for Django Views and Functions
======================================================

Simple decorators to enable SQL query logging for specific views or functions.
"""

import functools
import logging
import time

from django.conf import settings
from django.db import connection, reset_queries

logger = logging.getLogger("django.db.backends")


def log_sql_queries(func=None, *, log_level=logging.DEBUG, threshold=0.1):
    """
    Decorator to log SQL queries executed within a function.

    Args:
        log_level: Logging level for query output
        threshold: Slow query threshold in seconds

    Usage:
        @log_sql_queries
        def my_view(request):
            # Your view code

        @log_sql_queries(threshold=0.05)  # 50ms threshold
        def fast_view(request):
            # Your view code
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Only log if SQL logging is enabled
            if not getattr(settings, "LOG_SQL_QUERIES", False):
                return func(*args, **kwargs)

            # Reset queries before execution
            reset_queries()

            # Execute the function
            start_time = time.time()
            try:
                result = func(*args, **kwargs)

                # Log query summary
                _log_query_summary(func.__name__, start_time, threshold, log_level)

                return result
            except Exception as e:
                # Log queries even on exception
                _log_query_summary(
                    func.__name__, start_time, threshold, logging.ERROR, error=str(e)
                )
                raise

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def count_queries(func):
    """
    Decorator to count and log the number of queries executed.

    Useful for detecting N+1 query problems.

    Usage:
        @count_queries
        def my_view(request):
            # Your view code
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Reset queries
        reset_queries()

        # Execute function
        result = func(*args, **kwargs)

        # Log query count
        query_count = len(connection.queries)

        if query_count > 10:
            logger.warning(
                f"{func.__name__} executed {query_count} queries (potential optimization needed)"
            )
        else:
            logger.info(f"{func.__name__} executed {query_count} queries")

        return result

    return wrapper


def assert_max_queries(max_queries=10):
    """
    Decorator to assert that a function doesn't exceed a query limit.

    Raises an exception if the limit is exceeded (useful for tests).

    Args:
        max_queries: Maximum number of queries allowed

    Usage:
        @assert_max_queries(5)
        def optimized_view(request):
            # Should execute <= 5 queries
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Reset queries
            reset_queries()

            # Execute function
            result = func(*args, **kwargs)

            # Check query count
            query_count = len(connection.queries)

            if query_count > max_queries:
                raise AssertionError(
                    f"{func.__name__} executed {query_count} queries, "
                    f"exceeding limit of {max_queries}"
                )

            return result

        return wrapper

    return decorator


def profile_queries(func):
    """
    Decorator to profile SQL queries with detailed analysis.

    Provides a detailed breakdown of query types and performance.

    Usage:
        @profile_queries
        def complex_view(request):
            # Your view code
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Reset queries
        reset_queries()

        # Execute function
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time

        # Analyze queries
        queries = connection.queries
        if queries:
            _profile_query_details(func.__name__, queries, execution_time)

        return result

    return wrapper


def _log_query_summary(func_name, start_time, threshold, log_level, error=None):
    """Log a summary of executed queries."""
    execution_time = time.time() - start_time
    queries = connection.queries

    if not queries:
        return

    total_query_time = sum(float(q.get("time", 0)) for q in queries)
    query_count = len(queries)

    # Find slow queries
    slow_queries = [q for q in queries if float(q.get("time", 0)) > threshold]

    # Create summary message
    message_parts = [
        f"Function: {func_name}",
        f"Queries: {query_count}",
        f"Query Time: {total_query_time:.3f}s",
        f"Total Time: {execution_time:.3f}s",
        (
            f"Query %: {(total_query_time / execution_time) * 100:.1f}%"
            if execution_time > 0
            else "N/A"
        ),
    ]

    if slow_queries:
        message_parts.append(f"Slow Queries: {len(slow_queries)} (>{threshold}s)")

    if error:
        message_parts.append(f"Error: {error}")

    # Log the summary
    message = " | ".join(message_parts)
    logger.log(log_level, f"SQL Summary: {message}")

    # Log individual slow queries
    if slow_queries and log_level <= logging.WARNING:
        for i, query in enumerate(slow_queries[:5], 1):  # Log top 5 slow queries
            logger.warning(
                f"  Slow Query #{i} ({query['time']}s): {query['sql'][:200]}"
            )


def _categorize_queries(queries):
    """Categorize queries by type and return timing data."""
    query_types = {"SELECT": [], "INSERT": [], "UPDATE": [], "DELETE": [], "OTHER": []}

    for query in queries:
        sql = query["sql"].strip().upper()
        query_time = float(query.get("time", 0))

        if sql.startswith("SELECT"):
            query_types["SELECT"].append(query_time)
        elif sql.startswith("INSERT"):
            query_types["INSERT"].append(query_time)
        elif sql.startswith("UPDATE"):
            query_types["UPDATE"].append(query_time)
        elif sql.startswith("DELETE"):
            query_types["DELETE"].append(query_time)
        else:
            query_types["OTHER"].append(query_time)

    return query_types


def _find_duplicate_queries(queries):
    """Identify duplicate query patterns."""
    seen_queries = {}
    for query in queries:
        sql = query["sql"]
        if sql in seen_queries:
            seen_queries[sql] += 1
        else:
            seen_queries[sql] = 1

    return [(sql, count) for sql, count in seen_queries.items() if count > 1]


def _find_slowest_queries(queries, limit=5):
    """Find slowest queries by execution time."""
    return sorted(queries, key=lambda q: float(q.get("time", 0)), reverse=True)[:limit]


def _profile_query_details(func_name, queries, execution_time):
    """Profile queries with detailed breakdown."""
    # Categorize queries by type
    query_types = _categorize_queries(queries)

    # Calculate statistics
    total_queries = len(queries)
    total_query_time = sum(float(q.get("time", 0)) for q in queries)

    # Create profile report header
    profile_lines = [
        f"\n{'=' * 60}",
        f"Query Profile for {func_name}",
        f"{'=' * 60}",
        f"Total Execution Time: {execution_time:.3f}s",
        f"Total Query Time: {total_query_time:.3f}s ({(total_query_time / execution_time) * 100:.1f}%)",
        f"Total Queries: {total_queries}",
        (
            f"Average Query Time: {total_query_time / total_queries:.4f}s"
            if total_queries > 0
            else "N/A"
        ),
        "",
        "Query Breakdown:",
    ]

    # Add query type breakdown
    for query_type, times in query_types.items():
        if times:
            count = len(times)
            total = sum(times)
            avg = total / count
            profile_lines.append(
                f"  {query_type:8} {count:3} queries, {total:.3f}s total, {avg:.4f}s avg"
            )

    # Find and report duplicates
    duplicates = _find_duplicate_queries(queries)
    if duplicates:
        profile_lines.append("")
        profile_lines.append("Duplicate Queries Detected:")
        for sql, count in sorted(duplicates, key=lambda x: x[1], reverse=True)[:5]:
            profile_lines.append(f"  {count}x: {sql[:100]}")

    # Find and report slowest queries
    slowest = _find_slowest_queries(queries, limit=5)
    if slowest:
        profile_lines.append("")
        profile_lines.append("Slowest Queries:")
        for i, query in enumerate(slowest, 1):
            profile_lines.append(f"  #{i} ({query['time']}s): {query['sql'][:100]}")

    profile_lines.append("=" * 60)

    # Log the profile
    logger.info("\n".join(profile_lines))


# Context manager for query logging
class SQLQueryLogger:
    """
    Context manager for SQL query logging.

    Usage:
        with SQLQueryLogger('my_operation'):
            # Your code here
    """

    def __init__(self, name, log_level=logging.DEBUG):
        self.name = name
        self.log_level = log_level
        self.start_time = None

    def __enter__(self):
        """Enter the context and start logging."""
        reset_queries()
        self.start_time = time.time()
        logger.log(self.log_level, f"Starting SQL logging for: {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context and log summary."""
        execution_time = time.time() - self.start_time
        queries = connection.queries

        if queries:
            query_count = len(queries)
            total_query_time = sum(float(q.get("time", 0)) for q in queries)

            logger.log(
                self.log_level,
                f"Completed {self.name}: {query_count} queries in {total_query_time:.3f}s "
                f"(total: {execution_time:.3f}s)",
            )
        else:
            logger.log(self.log_level, f"Completed {self.name}: No queries executed")

        # Don't suppress exceptions
        return False
