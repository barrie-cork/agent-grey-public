"""
Search strategy reporting service for reporting slice.
Business capability: Search strategy documentation and reporting.

This is a facade class that maintains backward compatibility while delegating
to specialized single-responsibility services.
"""

from apps.core.logging import ServiceLoggerMixin

from .query_optimizer import QueryOptimizer
from .search_strategy_analyzer import SearchStrategyAnalyzer

# Import the specialized services
from .search_strategy_reporter import SearchStrategyReporter


class SearchStrategyReportingService(ServiceLoggerMixin):
    """
    Facade service for generating comprehensive search strategy reports.

    This class maintains backward compatibility while delegating to
    specialized services for better separation of concerns.
    """

    def __init__(self):
        """Initialize facade with specialized services."""
        self.reporter = SearchStrategyReporter()
        self.analyzer = SearchStrategyAnalyzer()
        self.optimizer = QueryOptimizer()

    def generate_search_strategy_report(self, session_id: str):
        """
        Generate comprehensive search strategy documentation.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with search strategy report data
        """
        # Delegate to the reporter
        return self.reporter.generate_report(session_id)

    def generate_query_optimization_report(self, session_id: str):
        """
        Generate report on query optimization and effectiveness.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with query optimization analysis
        """
        # Delegate to the optimizer
        return self.optimizer.get_optimization_suggestions(session_id)

    def analyze_search_strategy(self, session_id: str):
        """
        Analyze the search strategy for reporting purposes.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with search strategy analysis
        """
        # Delegate to the analyzer
        return self.analyzer.analyze_effectiveness(session_id)

    def calculate_query_effectiveness(self, session_id: str):
        """
        Calculate effectiveness metrics for search queries.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with effectiveness metrics
        """
        # First get optimization report from optimizer
        optimization_report = self.optimizer.get_optimization_suggestions(session_id)

        # Then use analyzer to calculate effectiveness
        return self.analyzer.calculate_query_effectiveness(
            session_id, optimization_report
        )
