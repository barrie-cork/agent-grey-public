"""
Search strategy analysis service.
Business capability: Analyze search strategy effectiveness and coverage.
"""

from apps.core.logging import ServiceLoggerMixin

from .search_strategy_reporter import SearchStrategyReporter

# Constants for result thresholds
MIN_OPTIMAL_RESULTS = 50
MAX_OPTIMAL_RESULTS = 200


class SearchStrategyAnalyzer(ServiceLoggerMixin):
    """Handles search strategy analysis and effectiveness calculations."""

    def __init__(self):
        """Initialize analyzer with reporter dependency."""
        self.reporter = SearchStrategyReporter()

    def analyze_effectiveness(self, session_id: str):
        """
        Analyze the search strategy for reporting purposes.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with search strategy analysis
        """
        # Get comprehensive search strategy report
        report_data = self.reporter.generate_report(session_id)

        # Add PIC analysis data from database
        pic_analysis = self._get_pic_analysis_data(session_id)

        # Add analysis insights
        analysis = {
            "overview": report_data.get("session_overview", {}),
            "framework": report_data.get("search_framework", {}),
            "queries": report_data.get("queries", []),
            "execution_summary": report_data.get("execution_summary", {}),
            "pic_analysis": pic_analysis,  # Add PIC analysis for templates
            "insights": {
                "total_queries": len(report_data.get("queries", [])),
                "coverage": self._calculate_coverage(report_data),
                "effectiveness": self._calculate_overall_effectiveness(report_data),
            },
        }

        return analysis

    def calculate_query_effectiveness(self, session_id: str, optimization_report: dict):
        """
        Calculate effectiveness metrics for search queries.

        Args:
            session_id: UUID of the SearchSession
            optimization_report: Query optimization report data

        Returns:
            Dictionary with effectiveness metrics
        """
        effectiveness = {
            "overall_performance": optimization_report.get("overall_metrics", {}),
            "query_metrics": [],
            "recommendations": [],
        }

        # Process individual query performance
        for query_perf in optimization_report.get("query_performance", []):
            effectiveness["query_metrics"].append(
                {
                    "query_text": query_perf.get("query_text", ""),
                    "results_count": query_perf.get("total_results", 0),
                    "success_rate": query_perf.get("execution_success_rate", 0),
                    "cost_effectiveness": query_perf.get("cost_effectiveness", 0),
                }
            )

        # Generate recommendations based on performance
        effectiveness["recommendations"] = self._generate_recommendations(
            optimization_report
        )

        return effectiveness

    def _calculate_coverage(self, report_data: dict):
        """Calculate search coverage metrics."""
        queries = report_data.get("queries", [])

        coverage = {
            "total_sources": len(
                set(
                    engine
                    for query in queries
                    for engine in query.get("parameters", {}).get("search_engines", [])
                )
            ),
            "date_coverage": self._calculate_date_coverage(queries),
            "language_coverage": len(
                set(
                    lang
                    for query in queries
                    for lang in query.get("parameters", {}).get("languages", [])
                )
            ),
        }

        return coverage

    def _calculate_date_coverage(self, queries: list) -> str:
        """Calculate date range coverage across queries."""
        if not queries:
            return "No date range specified"

        date_ranges = []
        for query in queries:
            params = query.get("parameters", {})
            date_range = params.get("date_range", {})
            if date_range.get("from") or date_range.get("to"):
                date_ranges.append(date_range)

        if not date_ranges:
            return "No date restrictions"

        # Simple date range summary
        return f"{len(date_ranges)} queries with date restrictions"

    def _calculate_overall_effectiveness(self, report_data: dict) -> float:
        """Calculate overall search effectiveness percentage."""
        summary = report_data.get("execution_summary", {})
        total_exec = summary.get("total_executions", 0)
        successful_exec = summary.get("successful_executions", 0)

        if total_exec == 0:
            return 0.0

        return round((successful_exec / total_exec) * 100, 1)

    def _generate_recommendations(self, optimization_report: dict):
        """Generate recommendations based on performance metrics."""
        recommendations = []

        # Check overall performance
        overall_metrics = optimization_report.get("overall_metrics", {})
        avg_results = overall_metrics.get("avg_results_per_query", 0)

        if avg_results < MIN_OPTIMAL_RESULTS:
            recommendations.append(
                "Consider broadening search terms to capture more results"
            )
        elif avg_results > MAX_OPTIMAL_RESULTS:
            recommendations.append(
                "Consider refining search terms to improve precision"
            )

        # Check engine effectiveness
        top_engines = overall_metrics.get("most_effective_engines", [])
        if top_engines:
            best_engine = top_engines[0].get("engine", "")
            recommendations.append(f"Focus on {best_engine} for best results coverage")

        # Check query performance
        query_performance = optimization_report.get("query_performance", [])
        low_performing = [
            q for q in query_performance if q.get("total_results", 0) < 10
        ]

        if low_performing:
            recommendations.append(
                f"{len(low_performing)} queries returned few results - consider revision"
            )

        return (
            recommendations
            if recommendations
            else ["Search strategy is well-optimized"]
        )

    def _get_pic_analysis_data(self, session_id: str):
        """
        Get PIC analysis data from SearchStrategy model.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with PIC terms and counts
        """
        # Import here to avoid circular imports
        from apps.search_strategy.models import SearchStrategy

        try:
            strategy = SearchStrategy.objects.get(session__id=session_id)

            return {
                "population_terms": strategy.population_terms or [],
                "population_count": len(strategy.population_terms or []),
                "interest_terms": strategy.interest_terms or [],
                "interest_count": len(strategy.interest_terms or []),
                "context_terms": strategy.context_terms or [],
                "context_count": len(strategy.context_terms or []),
            }
        except SearchStrategy.DoesNotExist:
            # Return empty structure if no strategy exists
            return {
                "population_terms": [],
                "population_count": 0,
                "interest_terms": [],
                "interest_count": 0,
                "context_terms": [],
                "context_count": 0,
            }
