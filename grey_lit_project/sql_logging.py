"""
Enhanced SQL Query Logging for Django
======================================

This module provides enhanced SQL query logging with:
- Query execution time tracking
- Query formatting for readability
- Query analysis and warnings
- Stack trace for query origin
"""

import logging
import time
import traceback
from decimal import Decimal

import sqlparse
from django.conf import settings
from django.db import connection
from django.db.backends import utils

logger = logging.getLogger("django.db.backends")


class SQLLoggingMiddleware:
    """
    Middleware to log SQL queries with enhanced formatting and metrics.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_query_threshold = getattr(
            settings, "SLOW_QUERY_THRESHOLD", 0.1
        )  # 100ms

    def __call__(self, request):
        # Reset queries at the start of request
        from django.db import reset_queries

        reset_queries()

        # Store request start time
        request._sql_log_start = time.time()

        # Process the request
        response = self.get_response(request)

        # Log query summary after request
        self.log_query_summary(request)

        return response

    def log_query_summary(self, request):
        """Log a summary of all queries executed during the request."""
        from django.db import connection

        if not connection.queries:
            return

        total_time = sum(float(q.get("time", 0)) for q in connection.queries)
        query_count = len(connection.queries)
        request_time = time.time() - request._sql_log_start

        # Log summary
        logger.info(
            f"SQL Summary for {request.method} {request.path}",
            extra={
                "request_path": request.path,
                "query_count": query_count,
                "total_query_time": f"{total_time:.3f}s",
                "request_time": f"{request_time:.3f}s",
                "query_percentage": (
                    f"{(total_time / request_time) * 100:.1f}%"
                    if request_time > 0
                    else "0%"
                ),
            },
        )

        # Log slow queries
        slow_queries = [
            q
            for q in connection.queries
            if float(q.get("time", 0)) > self.slow_query_threshold
        ]
        if slow_queries:
            logger.warning(
                f"Found {len(slow_queries)} slow queries (>{self.slow_query_threshold}s)",
                extra={"slow_query_count": len(slow_queries)},
            )


class EnhancedSQLCursorWrapper(utils.CursorWrapper):
    """
    Enhanced cursor wrapper that provides detailed SQL logging.
    """

    def execute(self, sql, params=None):
        self.db.validate_no_broken_transaction()

        # Get the stack trace to identify where the query originated
        stack = traceback.extract_stack()
        origin = self._get_query_origin(stack)

        # Start timing
        start_time = time.time()

        try:
            # Execute the query
            with self.db.wrap_database_errors:
                if params is None:
                    return self.cursor.execute(sql)
                else:
                    return self.cursor.execute(sql, params)
        finally:
            # Calculate execution time
            duration = time.time() - start_time

            # Log the query
            self._log_query(sql, params, duration, origin)

    def executemany(self, sql, param_list):
        self.db.validate_no_broken_transaction()

        # Get the stack trace
        stack = traceback.extract_stack()
        origin = self._get_query_origin(stack)

        # Start timing
        start_time = time.time()
        row_count = len(param_list) if param_list else 0

        try:
            # Execute the queries
            with self.db.wrap_database_errors:
                return self.cursor.executemany(sql, param_list)
        finally:
            # Calculate execution time
            duration = time.time() - start_time

            # Log the batch query
            self._log_batch_query(sql, row_count, duration, origin)

    def _get_query_origin(self, stack):
        """Extract the origin of the query from the stack trace."""
        # Skip Django internals and find the actual calling code
        app_frames = []
        for frame in reversed(stack[:-3]):  # Skip the last few frames (this wrapper)
            filename = frame.filename
            # Look for app code
            if "/apps/" in filename or "/grey_lit_project/" in filename:
                app_frames.append(frame)
            # Also include views, models, forms
            elif any(
                x in filename
                for x in ["/views.py", "/models.py", "/forms.py", "/tasks.py"]
            ):
                app_frames.append(frame)

        if app_frames:
            frame = app_frames[0]
            # Make the path relative for cleaner output
            filename = frame.filename
            if settings.BASE_DIR:
                filename = filename.replace(str(settings.BASE_DIR) + "/", "")
            return f"{filename}:{frame.lineno} in {frame.name}"

        return "Unknown origin"

    def _log_query(self, sql, params, duration, origin):
        """Log a single SQL query with formatting and analysis."""
        # Format the SQL query
        formatted_sql = self._format_sql(sql, params)

        # Determine log level based on duration
        if duration > 1.0:
            level = logging.ERROR
            level_name = "SLOW QUERY"
        elif duration > 0.1:
            level = logging.WARNING
            level_name = "SLOW"
        else:
            level = logging.DEBUG
            level_name = "SQL"

        # Analyze the query
        analysis = self._analyze_query(sql)

        # Create the log message
        message_parts = [
            f"[{level_name}] {duration:.3f}s",
            f"Origin: {origin}",
        ]

        if analysis:
            message_parts.append(f"Analysis: {analysis}")

        message_parts.append(f"Query:\n{formatted_sql}")

        # Log the query
        logger.log(level, "\n".join(message_parts))

    def _log_batch_query(self, sql, row_count, duration, origin):
        """Log a batch SQL query."""
        formatted_sql = self._format_sql(sql, None)

        avg_time = duration / row_count if row_count > 0 else 0

        message = (
            f"[BATCH] {duration:.3f}s for {row_count} rows (avg: {avg_time:.4f}s/row)\n"
            f"Origin: {origin}\n"
            f"Query:\n{formatted_sql}"
        )

        logger.debug(message)

    def _substitute_params(self, formatted_sql, params):
        """Substitute parameters into formatted SQL."""
        if not params:
            return formatted_sql

        try:
            # Convert params to a format we can work with
            if isinstance(params, (list, tuple)):
                for i, param in enumerate(params):
                    placeholder = "%s" if "%s" in formatted_sql else f"${i + 1}"
                    if isinstance(param, str):
                        value = f"'{param}'"
                    elif isinstance(param, (int, float, Decimal)):
                        value = str(param)
                    elif param is None:
                        value = "NULL"
                    else:
                        value = str(param)

                    # Replace first occurrence only
                    formatted_sql = formatted_sql.replace(placeholder, value, 1)
        except Exception:
            # If substitution fails, append params at the end
            formatted_sql += f"\n-- Params: {params}"

        return formatted_sql

    def _apply_syntax_highlighting(self, formatted_sql):
        """Apply Pygments syntax highlighting if available."""
        if not settings.DEBUG:
            return formatted_sql

        try:
            from pygments import highlight
            from pygments.formatters import TerminalFormatter
            from pygments.lexers import SqlLexer

            return highlight(formatted_sql, SqlLexer(), TerminalFormatter())
        except ImportError:
            pass  # Pygments not installed

        return formatted_sql

    def _format_sql(self, sql, params):
        """Format SQL query for better readability."""
        # First, use sqlparse for basic formatting
        formatted = sqlparse.format(
            sql,
            reindent=True,
            keyword_case="upper",
            strip_comments=True,
            use_space_around_operators=True,
        )

        # Substitute parameters if provided
        formatted = self._substitute_params(formatted, params)

        # Apply syntax highlighting if in development
        formatted = self._apply_syntax_highlighting(formatted)

        return formatted

    def _analyze_query(self, sql):
        """Analyze the query for potential issues."""
        warnings = []

        sql_upper = sql.upper()

        # Check for SELECT *
        if "SELECT *" in sql_upper:
            warnings.append("SELECT * detected - specify columns explicitly")

        # Check for missing WHERE in UPDATE/DELETE
        if (
            "UPDATE " in sql_upper or "DELETE " in sql_upper
        ) and "WHERE" not in sql_upper:
            warnings.append("UPDATE/DELETE without WHERE clause!")

        # Check for N+1 query patterns
        if (
            sql_upper.startswith("SELECT")
            and "WHERE" in sql_upper
            and "IN (" not in sql_upper
        ):
            # This might be an N+1 query if it's selecting by ID
            if any(
                x in sql_upper for x in ['WHERE "ID" =', "WHERE ID =", "WHERE `ID` ="]
            ):
                warnings.append("Possible N+1 query pattern")

        # Check for LIKE with leading wildcard
        if "LIKE '%" in sql_upper or 'LIKE "%' in sql_upper:
            warnings.append("Leading wildcard in LIKE - cannot use index")

        # Check for missing indexes (basic heuristic)
        if "WHERE" in sql_upper and "SELECT" in sql_upper:
            # Look for common unindexed fields
            unindexed_fields = ["created_at", "updated_at", "status", "type"]
            for field in unindexed_fields:
                if field.upper() in sql_upper:
                    warnings.append(f"Query on potentially unindexed field: {field}")

        # Check for large LIMIT without ORDER BY
        if "LIMIT" in sql_upper and "ORDER BY" not in sql_upper:
            warnings.append("LIMIT without ORDER BY - results may be unpredictable")

        return " | ".join(warnings) if warnings else None


def install_sql_logging():
    """
    Install enhanced SQL logging for Django.

    This should be called in settings when SQL logging is enabled.
    """
    # Only install if SQL logging is enabled
    if not getattr(settings, "LOG_SQL_QUERIES", False):
        return

    # Monkey-patch the cursor wrapper
    original_cursor = connection.cursor

    def enhanced_cursor():
        cursor = original_cursor()
        return EnhancedSQLCursorWrapper(cursor, connection)

    connection.cursor = enhanced_cursor

    logger.info("Enhanced SQL logging installed")


def log_query_stats():
    """
    Log statistics about queries executed so far.

    Useful for debugging and optimization.
    """
    from django.db import connection

    if not connection.queries:
        logger.info("No queries executed yet")
        return

    queries = connection.queries
    total_time = sum(float(q.get("time", 0)) for q in queries)

    # Group queries by type
    query_types = {}
    for query in queries:
        sql = query["sql"].upper().strip()
        if sql.startswith("SELECT"):
            query_type = "SELECT"
        elif sql.startswith("INSERT"):
            query_type = "INSERT"
        elif sql.startswith("UPDATE"):
            query_type = "UPDATE"
        elif sql.startswith("DELETE"):
            query_type = "DELETE"
        else:
            query_type = "OTHER"

        if query_type not in query_types:
            query_types[query_type] = {"count": 0, "time": 0}

        query_types[query_type]["count"] += 1
        query_types[query_type]["time"] += float(query.get("time", 0))

    # Find slowest queries
    sorted_queries = sorted(
        queries, key=lambda q: float(q.get("time", 0)), reverse=True
    )
    slowest = sorted_queries[:5] if len(sorted_queries) >= 5 else sorted_queries

    # Log the statistics
    slowest_times = [f"{float(q.get('time', 0)):.3f}s" for q in slowest]
    logger.info(
        f"Query Statistics:\n"
        f"  Total queries: {len(queries)}\n"
        f"  Total time: {total_time:.3f}s\n"
        f"  Average time: {total_time / len(queries):.4f}s\n"
        f"  Query types: {query_types}\n"
        f"  Slowest queries: {slowest_times}"
    )


class QueryCountDebugMiddleware:
    """
    Middleware that logs the number of queries for each request.

    Useful for detecting N+1 query problems.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.db import connection, reset_queries

        # Reset queries before request
        reset_queries()

        # Store initial query count
        queries_before = len(connection.queries)

        # Process request
        response = self.get_response(request)

        # Calculate queries executed
        queries_after = len(connection.queries)
        query_count = queries_after - queries_before

        # Add query count to response headers (useful for debugging)
        response["X-DB-Query-Count"] = str(query_count)

        # Log if query count is high
        if query_count > 10:
            logger.warning(
                f"High query count: {query_count} queries for {request.method} {request.path}"
            )

        return response
