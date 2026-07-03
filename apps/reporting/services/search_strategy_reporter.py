"""
Search strategy basic report generation.
Business capability: Generate basic search strategy reports.
"""

from apps.core.logging import ServiceLoggerMixin

from ..dependencies import get_review_manager, get_search_strategy, get_serp_execution


class SearchStrategyReporter(ServiceLoggerMixin):
    """Handles basic search strategy report generation."""

    def __init__(self):
        """Initialize service with dependencies."""
        self.review_manager = get_review_manager()
        self.search_strategy = get_search_strategy()
        self.serp_execution = get_serp_execution()

    def generate_report(self, session_id: str):
        """
        Generate comprehensive search strategy documentation.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with search strategy report data
        """
        session_data = self.review_manager.get_session(session_id)
        if not session_data:
            return {}

        # Use interface methods instead of direct model references
        queries = self.search_strategy.get_search_queries(session_id)
        execution_stats = self.serp_execution.get_execution_statistics(session_id)

        report_data = {
            "session_overview": {
                "title": session_data.get("title", ""),
                "description": session_data.get("description", ""),
                "created_date": session_data.get("created_at", ""),
                "status": session_data.get("status", ""),
            },
            "search_framework": {
                "total_queries": len(queries),
                "primary_queries": sum(
                    1 for q in queries if q.get("is_primary", False)
                ),
                "secondary_queries": sum(
                    1 for q in queries if not q.get("is_primary", False)
                ),
            },
            "queries": [],
            "execution_summary": {
                "total_executions": execution_stats.get("total_executions", 0),
                "successful_executions": execution_stats.get(
                    "successful_executions", 0
                ),
                "total_results_retrieved": execution_stats.get("total_results", 0),
                "search_engines_used": execution_stats.get("search_engines", []),
                "total_cost": execution_stats.get("total_cost", 0),
            },
        }

        # Detailed query information
        for query in queries:
            query_data = {
                "id": query.get("id", ""),
                "pic_framework": {
                    "population": query.get("population", ""),
                    "interest": query.get("interest", ""),
                    "context": query.get("context", ""),
                },
                "query_text": query.get("query_text", ""),
                "parameters": {
                    "search_engines": query.get("search_engines", []),
                    "include_keywords": query.get("include_keywords", []),
                    "exclude_keywords": query.get("exclude_keywords", []),
                    "date_range": {
                        "from": query.get("date_from"),
                        "to": query.get("date_to"),
                    },
                    "languages": query.get("languages", []),
                    "document_types": query.get("document_types", []),
                    "max_results": query.get("max_results", 0),
                },
                "execution_results": {
                    "executions_count": query.get("executions_count", 0),
                    "total_results": query.get("total_results", 0),
                    "avg_results_per_execution": query.get(
                        "avg_results_per_execution", 0
                    ),
                    "success_rate": query.get("success_rate", 0),
                },
            }

            report_data["queries"].append(query_data)

        return report_data
