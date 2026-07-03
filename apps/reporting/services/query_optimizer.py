"""
Query optimization service.
Business capability: Analyze and optimize search query performance.
"""

from typing import Any

from django.db.models import QuerySet

from apps.core.logging import ServiceLoggerMixin

from ..constants import PerformanceConstants, SearchStrategyConstants
from ..dependencies import get_search_strategy


class QueryOptimizer(ServiceLoggerMixin):
    """Handles query optimization recommendations and performance analysis."""

    def __init__(self):
        """Initialize optimizer with dependencies."""
        self.search_strategy = get_search_strategy()

    def get_optimization_suggestions(self, session_id: str):
        """
        Generate report on query optimization and effectiveness.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with query optimization analysis
        """
        # Use interface methods instead of direct model references
        queries = self.search_strategy.get_search_queries(session_id)
        optimization_data = self._initialize_optimization_report(session_id)

        total_results = 0
        engine_performance = {}

        # Process each query
        for query in queries:
            # Get executions data from the query dict
            executions = query.get("executions", [])

            # Build query performance metrics
            query_performance = self._build_query_performance(query, executions)
            optimization_data["query_performance"].append(query_performance)

            # Update totals
            total_results += query_performance["total_results"]

            # Track engine performance
            self._track_engine_performance(executions, engine_performance)

        # Calculate overall metrics
        optimization_data["overall_metrics"] = self._calculate_overall_metrics(
            total_results, len(queries), engine_performance
        )

        return optimization_data

    def _initialize_optimization_report(self, session_id: str):
        """Initialize the optimization report structure."""
        return {
            "session_id": session_id,
            "query_performance": [],
            "recommendations": [],
            "overall_metrics": {
                "avg_results_per_query": 0,
                "most_effective_engines": [],
                "keyword_effectiveness": {},
            },
        }

    def _build_query_performance(self, query: dict, executions: list):
        """Build performance metrics for a single query."""
        # Handle both dict and model object
        if isinstance(query, dict):
            query_id = query.get("id", "")
            query_string = query.get("query_text", "")
            query_results = query.get("total_results", 0)
        else:
            query_id = str(query.id)
            query_string = getattr(query, "query_text", "")
            query_results = (
                sum(e.results_count for e in executions) if executions else 0
            )

        return {
            "query_id": query_id,
            "query_text": query_string,
            "total_results": query_results,
            "execution_success_rate": self._calculate_success_rate(executions),
            "cost_effectiveness": self._calculate_cost_effectiveness(
                query_results, executions
            ),
        }

    def _calculate_success_rate(self, executions: QuerySet | list) -> float:
        """
        Calculate execution success rate as a percentage.

        Accepts either a Django QuerySet or a plain list of execution objects/dicts.
        For QuerySets, uses .count() and .filter() for efficiency. For lists,
        iterates and checks each item's status attribute against COMPLETED_STATUS.

        Args:
            executions: A QuerySet of SearchExecution objects or a list of
                execution dicts/objects. Each item should have a ``status``
                attribute (or key) that can be compared to
                ``PerformanceConstants.COMPLETED_STATUS``.

        Returns:
            Success rate as a float percentage (0.0--100.0), rounded to
            ``PerformanceConstants.DECIMAL_PLACES["percentage"]`` decimal places.
            Returns 0.0 for empty inputs.
        """
        if not executions:
            return 0.0

        # Handle both QuerySet and list
        if isinstance(executions, QuerySet):
            qs: QuerySet[Any] = executions
            total_count = qs.count()
            success_count = qs.filter(
                status=PerformanceConstants.COMPLETED_STATUS
            ).count()
        elif isinstance(executions, list):
            total_count = len(executions)
            success_count = len(
                [
                    e
                    for e in executions
                    if getattr(e, "status", "") == PerformanceConstants.COMPLETED_STATUS
                ]
            )
        else:
            return 0.0

        if total_count == 0:
            return 0.0

        return round(
            success_count / total_count * PerformanceConstants.PERCENTAGE_MULTIPLIER,
            PerformanceConstants.DECIMAL_PLACES["percentage"],
        )

    def _calculate_cost_effectiveness(
        self, total_results: int, executions: list
    ) -> float:
        """Calculate cost effectiveness (results per cost unit)."""
        if not executions:
            return 0.0

        # Handle both QuerySet and list
        if hasattr(executions, "__iter__"):
            total_cost = sum(getattr(e, "estimated_cost", 0.01) for e in executions)
        else:
            total_cost = 0.01

        if total_cost <= 0:
            total_cost = 0.01

        return round(
            total_results / total_cost,
            PerformanceConstants.DECIMAL_PLACES["ratio"],
        )

    def _track_engine_performance(
        self, executions: list, engine_performance: dict
    ) -> None:
        """Track performance metrics by search engine."""
        if not executions:
            return

        for execution in executions:
            # Handle both dict and model object
            if isinstance(execution, dict):
                engine = execution.get("search_engine", "unknown")
                results_count = execution.get("results_count", 0)
            else:
                engine = getattr(execution, "search_engine", "unknown")
                results_count = getattr(execution, "results_count", 0)

            if engine not in engine_performance:
                engine_performance[engine] = {"results": 0, "count": 0}
            engine_performance[engine]["results"] += results_count
            engine_performance[engine]["count"] += 1

    def _calculate_overall_metrics(
        self, total_results: int, query_count: int, engine_performance: dict
    ):
        """Calculate overall optimization metrics."""
        metrics = {}

        # Average results per query
        if query_count > 0:
            metrics["avg_results_per_query"] = round(
                total_results / query_count,
                PerformanceConstants.DECIMAL_PLACES["ratio"],
            )
        else:
            metrics["avg_results_per_query"] = 0

        # Most effective engines
        metrics["most_effective_engines"] = self._get_top_engines(engine_performance)
        metrics["keyword_effectiveness"] = {}  # Placeholder for future implementation

        return metrics

    def _get_top_engines(self, engine_performance: dict):
        """Get top performing search engines."""
        if not engine_performance:
            return []

        # Sort by average results per execution
        sorted_engines = sorted(
            engine_performance.items(),
            key=lambda x: self._calculate_engine_average(x[1]),
            reverse=True,
        )[: SearchStrategyConstants.TOP_ENGINES_LIMIT]

        return [
            self._format_engine_result(engine, data) for engine, data in sorted_engines
        ]

    def _calculate_engine_average(self, data: dict) -> float:
        """Calculate average results per execution for an engine."""
        if data["count"] == 0:
            return 0.0
        return data["results"] / data["count"]

    def _format_engine_result(self, engine: str, data: dict):
        """Format engine performance data."""
        return {
            "engine": engine,
            "avg_results": round(
                self._calculate_engine_average(data),
                PerformanceConstants.DECIMAL_PLACES["ratio"],
            ),
        }
