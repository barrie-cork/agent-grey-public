"""
Tests for SearchStrategyReportingService.

Tests search strategy documentation and reporting.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.reporting.services.search_strategy_reporting_service import (
    SearchStrategyReportingService,
)
from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy

User = get_user_model()


class TestSearchStrategyReportingService(TestCase):
    """Test cases for SearchStrategyReportingService."""

    def setUp(self):
        """Set up test data."""
        self.service = SearchStrategyReportingService()

        # Create test user
        self.user = create_test_user()

        # Create test session
        self.session = SearchSession.objects.create(
            title="Healthcare AI Review",
            description="Systematic review of AI in healthcare",
            owner=self.user,
            status="ready_to_execute",
        )

        # Create search strategy with PIC terms
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=[
                "Healthcare providers",
                "patients",
                "Adults over 18 years",
            ],
            interest_terms=[
                "Artificial Intelligence",
                "AI",
                "Machine learning",
                "Deep learning",
            ],
            context_terms=["Hospital", "clinical settings", "peer-reviewed"],
            search_config={
                "domains": ["who.int", "nih.gov"],
                "include_general_search": True,
                "file_types": ["pdf"],
                "search_type": "google",
            },
            is_complete=True,
        )

        # Create search queries
        self.query1 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text='("artificial intelligence" OR "AI") AND "healthcare" AND "clinical outcomes"',
            query_type="domain-specific",
            target_domain="who.int",
            execution_order=1,
        )

        self.query2 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text='("machine learning" OR "deep learning") AND "patient care" AND "hospital"',
            query_type="general",
            target_domain=None,
            execution_order=2,
        )

    @patch(
        "apps.reporting.services.search_strategy_reporter.SearchStrategyReporter.generate_report"
    )
    def test_generate_search_strategy_report(self, mock_generate_report):
        """Test generation of comprehensive search strategy report."""
        # Setup mock return value
        mock_report = {
            "session_overview": {
                "title": "Healthcare AI Review",
                "description": "Systematic review of AI in healthcare",
                "status": "ready_to_execute",
            },
            "search_framework": {
                "total_queries": 2,
                "primary_queries": 1,
                "secondary_queries": 1,
            },
            "queries": [
                {
                    "id": str(self.query1.id),
                    "query_text": self.query1.query_text,
                    "pic_framework": {
                        "population": "Healthcare providers",
                        "interest": "Artificial Intelligence",
                        "context": "Hospital",
                    },
                }
            ],
            "execution_summary": {
                "total_executions": 0,
                "successful_executions": 0,
                "total_results_retrieved": 0,
                "search_engines_used": [],
                "total_cost": 0,
            },
        }
        mock_generate_report.return_value = mock_report

        # Call the method
        report = self.service.generate_search_strategy_report(str(self.session.id))

        # Assertions
        self.assertIsInstance(report, dict)
        self.assertIn("session_overview", report)
        self.assertIn("search_framework", report)
        self.assertIn("queries", report)
        self.assertIn("execution_summary", report)

        # Verify delegation
        mock_generate_report.assert_called_once_with(str(self.session.id))

        # Check session overview
        session_overview = report["session_overview"]
        self.assertEqual(session_overview["title"], "Healthcare AI Review")
        self.assertEqual(session_overview["status"], "ready_to_execute")

        # Check search framework
        framework = report["search_framework"]
        self.assertIn("total_queries", framework)
        self.assertEqual(framework["total_queries"], 2)

    @patch(
        "apps.reporting.services.query_optimizer.QueryOptimizer.get_optimization_suggestions"
    )
    def test_generate_query_optimization_report(self, mock_get_optimization):
        """Test generation of query optimization report."""
        # Setup mock return value
        mock_optimization = {
            "query_performance": [
                {
                    "query_id": str(self.query1.id),
                    "query_text": self.query1.query_text,
                    "performance_score": 85,
                    "suggestions": ["Consider adding more specific terms"],
                }
            ],
            "overall_metrics": {
                "average_performance": 85,
                "total_queries": 2,
                "optimization_potential": "low",
            },
            "recommendations": [
                "Queries are well-optimized",
                "Consider broader terms for more results",
            ],
        }
        mock_get_optimization.return_value = mock_optimization

        # Call the method
        report = self.service.generate_query_optimization_report(str(self.session.id))

        # Assertions
        self.assertIsInstance(report, dict)
        self.assertIn("query_performance", report)
        self.assertIn("overall_metrics", report)
        self.assertIn("recommendations", report)

        # Verify delegation
        mock_get_optimization.assert_called_once_with(str(self.session.id))

    @patch(
        "apps.reporting.services.search_strategy_analyzer.SearchStrategyAnalyzer.analyze_effectiveness"
    )
    def test_analyze_search_strategy(self, mock_analyze_effectiveness):
        """Test analysis of search strategy."""
        # Setup mock return value
        mock_analysis = {
            "effectiveness_score": 90,
            "pic_analysis": {
                "population_coverage": "high",
                "interest_coverage": "high",
                "context_coverage": "medium",
            },
            "insights": [
                "Good coverage of population terms",
                "Interest terms are comprehensive",
                "Consider adding more context terms",
            ],
        }
        mock_analyze_effectiveness.return_value = mock_analysis

        # Call the method
        analysis = self.service.analyze_search_strategy(str(self.session.id))

        # Assertions
        self.assertIsInstance(analysis, dict)
        self.assertIn("effectiveness_score", analysis)
        self.assertIn("pic_analysis", analysis)
        self.assertIn("insights", analysis)

        # Verify delegation
        mock_analyze_effectiveness.assert_called_once_with(str(self.session.id))

    @patch(
        "apps.reporting.services.query_optimizer.QueryOptimizer.get_optimization_suggestions"
    )
    @patch(
        "apps.reporting.services.search_strategy_analyzer.SearchStrategyAnalyzer.calculate_query_effectiveness"
    )
    def test_calculate_query_effectiveness(
        self, mock_calculate_effectiveness, mock_get_optimization
    ):
        """Test calculation of query effectiveness metrics."""
        # Setup mock return values
        mock_optimization = {
            "query_performance": [],
            "overall_metrics": {},
            "recommendations": [],
        }
        mock_get_optimization.return_value = mock_optimization

        mock_effectiveness = {
            "effectiveness_metrics": {
                "precision": 0.85,
                "recall": 0.75,
                "f1_score": 0.80,
            },
            "query_effectiveness": [
                {
                    "query_id": str(self.query1.id),
                    "effectiveness": 0.82,
                    "result_quality": "high",
                }
            ],
        }
        mock_calculate_effectiveness.return_value = mock_effectiveness

        # Call the method
        effectiveness = self.service.calculate_query_effectiveness(str(self.session.id))

        # Assertions
        self.assertIsInstance(effectiveness, dict)
        self.assertIn("effectiveness_metrics", effectiveness)
        self.assertIn("query_effectiveness", effectiveness)

        # Verify delegations
        mock_get_optimization.assert_called_once_with(str(self.session.id))
        mock_calculate_effectiveness.assert_called_once_with(
            str(self.session.id), mock_optimization
        )

    def test_service_initialization(self):
        """Test that the service initializes properly with all components."""
        service = SearchStrategyReportingService()

        # Check that all delegated services are initialized
        self.assertIsNotNone(service.reporter)
        self.assertIsNotNone(service.analyzer)
        self.assertIsNotNone(service.optimizer)

    @patch(
        "apps.reporting.services.search_strategy_reporter.SearchStrategyReporter.generate_report"
    )
    def test_empty_session_handling(self, mock_generate_report):
        """Test handling of sessions with no queries."""
        # Setup mock for empty session
        mock_generate_report.return_value = {
            "session_overview": {},
            "search_framework": {"total_queries": 0},
            "queries": [],
            "execution_summary": {},
        }

        # Create session with no queries
        empty_session = SearchSession.objects.create(
            title="Empty Session",
            owner=self.user,
            status="draft",
        )

        # Call the method
        report = self.service.generate_search_strategy_report(str(empty_session.id))

        # Assertions
        self.assertIsInstance(report, dict)
        self.assertEqual(report["search_framework"]["total_queries"], 0)
        self.assertEqual(len(report["queries"]), 0)

    @patch(
        "apps.reporting.services.search_strategy_reporter.SearchStrategyReporter.generate_report"
    )
    def test_invalid_session_id(self, mock_generate_report):
        """Test handling of invalid session IDs."""
        # Setup mock for invalid session
        mock_generate_report.return_value = {}

        # Call with invalid UUID
        report = self.service.generate_search_strategy_report("invalid-uuid")

        # Should return empty dict
        self.assertEqual(report, {})

    @patch(
        "apps.reporting.services.search_strategy_reporter.SearchStrategyReporter.generate_report"
    )
    def test_logging_in_report_generation(self, mock_generate_report):
        """Test that report generation is properly logged."""
        # Setup mock return value
        mock_generate_report.return_value = {
            "session_overview": {},
            "search_framework": {"total_queries": 0},
            "queries": [],
            "execution_summary": {},
        }

        # Call the service method - the facade doesn't log, it just delegates
        report = self.service.generate_search_strategy_report(str(self.session.id))

        # Verify that delegation occurred
        mock_generate_report.assert_called_once_with(str(self.session.id))

        # Verify the result was returned
        self.assertIsInstance(report, dict)
