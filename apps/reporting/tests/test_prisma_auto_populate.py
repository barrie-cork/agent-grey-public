"""
Tests for PRISMA auto-population and full two-column flow data generation.

Covers:
- auto_populate_other_methods() with domain-specific vs general queries
- generate_full_prisma_flow_data() structure and user-override precedence
- _gather_identification_data() backward compatibility after cleanup
"""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.tests.utils import create_test_user
from apps.reporting.services.prisma_reporting_service import PrismaReportingService
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import BrowsingVisit
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution


class AutoPopulateOtherMethodsTest(TestCase):
    """Test auto_populate_other_methods() with different query types."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Auto-populate Test",
            owner=self.user,
            status="completed",
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
        )
        self.service = PrismaReportingService()

    def _create_query_and_execution(
        self, *, target_domain=None, results_count=10, query_type="general"
    ):
        """Helper to create a SearchQuery + completed SearchExecution."""
        if target_domain:
            query_type = "domain-specific"
        query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type=query_type,
            target_domain=target_domain,
            execution_order=1,
            is_active=True,
        )
        SearchExecution.objects.create(
            query=query,
            initiated_by=self.user,
            status="completed",
            results_count=results_count,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        return query

    def test_domain_specific_queries_count_as_organisations(self):
        """Queries with target_domain should count towards organisations."""
        self._create_query_and_execution(target_domain="nice.org.uk", results_count=15)
        result = self.service.auto_populate_other_methods(str(self.session.id))

        self.assertEqual(result["organisations"], 15)
        self.assertEqual(result["websites"], 0)

    def test_general_queries_count_as_websites(self):
        """Queries without target_domain should count towards websites."""
        self._create_query_and_execution(results_count=20)
        result = self.service.auto_populate_other_methods(str(self.session.id))

        self.assertEqual(result["websites"], 20)
        self.assertEqual(result["organisations"], 0)

    def test_mixed_query_types(self):
        """Domain-specific and general queries split correctly."""
        self._create_query_and_execution(target_domain="who.int", results_count=10)
        self._create_query_and_execution(results_count=25)

        result = self.service.auto_populate_other_methods(str(self.session.id))

        self.assertEqual(result["organisations"], 10)
        self.assertEqual(result["websites"], 25)

    def test_capture_provenance_counts(self):
        """De-personalised vs personalised visit counts (R5)."""
        for i, incognito in enumerate([True, True, False]):
            BrowsingVisit.objects.create(
                session=self.session,
                user=self.user,
                url=f"https://example{i}.com/",
                captured_incognito=incognito,
            )
        result = self.service.auto_populate_other_methods(str(self.session.id))

        self.assertEqual(result["reports_sought"], 3)
        self.assertEqual(result["de_personalised_visits"], 2)
        self.assertEqual(result["personalised_visits"], 1)

    def test_flow_data_exposes_capture_provenance(self):
        """generate_full_prisma_flow_data surfaces provenance regardless of overrides."""
        BrowsingVisit.objects.create(
            session=self.session,
            user=self.user,
            url="https://a.com/",
            captured_incognito=True,
        )
        BrowsingVisit.objects.create(
            session=self.session,
            user=self.user,
            url="https://b.com/",
            captured_incognito=False,
        )
        flow = self.service.generate_full_prisma_flow_data(str(self.session.id))

        self.assertEqual(
            flow["capture_provenance"],
            {"total": 2, "de_personalised": 1, "personalised": 1},
        )

    def test_manually_added_results_counted(self):
        """Manually added ProcessedResults counted as other_sources."""
        ProcessedResult.objects.create(
            session=self.session,
            title="Manual Result",
            url="https://example.com/manual",
            snippet="Manually added",
            is_manually_added=True,
            processing_status="success",
        )
        result = self.service.auto_populate_other_methods(str(self.session.id))

        self.assertEqual(result["other_sources"], 1)

    def test_browsing_visits_populate_retrieval_stats(self):
        """reports_sought and reports_not_retrieved come from BrowsingVisit."""
        from apps.review_results.models import BrowsingVisit

        for i in range(5):
            BrowsingVisit.objects.create(
                session=self.session,
                user=self.user,
                url=f"https://example{i}.com/page",
                title=f"Page {i}",
                access_successful=i < 3,  # 3 successful, 2 failed
                visit_source="auto",
            )

        result = self.service.auto_populate_other_methods(str(self.session.id))

        self.assertEqual(result["reports_sought"], 5)
        self.assertEqual(result["reports_not_retrieved"], 2)
        self.assertEqual(result["reports_assessed"], 3)

    def test_reuses_exclusion_reasons(self):
        """Should delegate to get_exclusion_reasons()."""
        with patch.object(
            self.service,
            "get_exclusion_reasons",
            return_value={"Not relevant": 3, "Duplicate": 2},
        ) as mock_exclusion:
            result = self.service.auto_populate_other_methods(str(self.session.id))

            mock_exclusion.assert_called_once_with(str(self.session.id))
            self.assertEqual(
                result["exclusion_reasons"], {"Not relevant": 3, "Duplicate": 2}
            )
            self.assertEqual(result["reports_excluded"], 5)

    def test_citation_searching_defaults_to_zero(self):
        """citation_searching should default to 0."""
        result = self.service.auto_populate_other_methods(str(self.session.id))
        self.assertEqual(result["citation_searching"], 0)

    def test_only_completed_executions_counted(self):
        """Failed executions should not be included in counts."""
        query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            execution_order=1,
            is_active=True,
        )
        SearchExecution.objects.create(
            query=query,
            initiated_by=self.user,
            status="failed",
            results_count=50,
            started_at=timezone.now(),
        )
        result = self.service.auto_populate_other_methods(str(self.session.id))

        self.assertEqual(result["websites"], 0)
        self.assertEqual(result["organisations"], 0)


class GenerateFullPrismaFlowDataTest(TestCase):
    """Test generate_full_prisma_flow_data() returns correct two-column structure."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Full Flow Test",
            owner=self.user,
            status="completed",
        )
        self.service = PrismaReportingService()

    def test_returns_empty_for_missing_session(self):
        """Should return empty dict for non-existent session."""
        result = self.service.generate_full_prisma_flow_data(
            "00000000-0000-0000-0000-000000000000"
        )
        self.assertEqual(result, {})

    def test_top_level_structure(self):
        """Result should have database_flow, other_methods_flow, included, session_metadata."""
        result = self.service.generate_full_prisma_flow_data(str(self.session.id))

        self.assertIn("database_flow", result)
        self.assertIn("other_methods_flow", result)
        self.assertIn("included", result)
        self.assertIn("session_metadata", result)

    def test_database_flow_structure(self):
        """database_flow should have identification, screening, retrieval, eligibility."""
        result = self.service.generate_full_prisma_flow_data(str(self.session.id))
        db_flow = result["database_flow"]

        self.assertIn("identification", db_flow)
        self.assertIn("screening", db_flow)
        self.assertIn("retrieval", db_flow)
        self.assertIn("eligibility", db_flow)

        # Check identification sub-keys
        self.assertIn("databases_registers", db_flow["identification"])
        self.assertIn("duplicates_removed", db_flow["identification"])

    def test_other_methods_flow_structure(self):
        """other_methods_flow should have identification, retrieval, eligibility."""
        result = self.service.generate_full_prisma_flow_data(str(self.session.id))
        om_flow = result["other_methods_flow"]

        self.assertIn("identification", om_flow)
        self.assertIn("retrieval", om_flow)
        self.assertIn("eligibility", om_flow)

        # Check identification sub-keys
        self.assertIn("websites", om_flow["identification"])
        self.assertIn("organisations", om_flow["identification"])
        self.assertIn("citation_searching", om_flow["identification"])

    def test_user_override_takes_precedence(self):
        """When prisma_other_methods is populated, it should be used instead of auto-population."""
        override_data = {
            "websites": 99,
            "organisations": 88,
            "citation_searching": 77,
            "reports_sought": 66,
            "reports_not_retrieved": 55,
            "reports_assessed": 44,
            "reports_excluded": 33,
            "exclusion_reasons": {"Custom Reason": 33},
        }
        self.session.prisma_other_methods = override_data
        self.session.save()

        result = self.service.generate_full_prisma_flow_data(str(self.session.id))
        om_flow = result["other_methods_flow"]

        self.assertEqual(om_flow["identification"]["websites"], 99)
        self.assertEqual(om_flow["identification"]["organisations"], 88)
        self.assertEqual(om_flow["identification"]["citation_searching"], 77)
        self.assertEqual(om_flow["retrieval"]["reports_sought"], 66)
        self.assertEqual(
            om_flow["eligibility"]["exclusion_reasons"], {"Custom Reason": 33}
        )
        self.assertTrue(result["session_metadata"]["has_user_overrides"])

    def test_auto_populates_when_no_user_override(self):
        """When prisma_other_methods is empty, auto-populate should be called."""
        self.assertEqual(self.session.prisma_other_methods, {})

        with patch.object(
            self.service,
            "auto_populate_other_methods",
            return_value={
                "websites": 10,
                "organisations": 5,
                "other_sources": 0,
                "citation_searching": 0,
                "reports_sought": 0,
                "reports_not_retrieved": 0,
                "reports_assessed": 0,
                "reports_excluded": 0,
                "exclusion_reasons": {},
            },
        ) as mock_auto:
            result = self.service.generate_full_prisma_flow_data(str(self.session.id))

            mock_auto.assert_called_once_with(str(self.session.id))
            self.assertEqual(
                result["other_methods_flow"]["identification"]["websites"], 10
            )
            self.assertFalse(result["session_metadata"]["has_user_overrides"])

    def test_session_metadata(self):
        """session_metadata should contain session info."""
        result = self.service.generate_full_prisma_flow_data(str(self.session.id))
        metadata = result["session_metadata"]

        self.assertEqual(metadata["session_id"], str(self.session.id))
        self.assertEqual(metadata["title"], "Full Flow Test")
        self.assertIn("created_date", metadata)
        self.assertIn("has_user_overrides", metadata)


class GatherIdentificationBackwardCompatibilityTest(TestCase):
    """Test _gather_identification_data() still returns expected keys after cleanup."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Backward Compat Test",
            owner=self.user,
            status="completed",
        )
        self.service = PrismaReportingService()

    @patch("apps.reporting.services.prisma_reporting_service.get_session_queries_data")
    @patch(
        "apps.reporting.services.prisma_reporting_service.get_session_executions_data"
    )
    @patch("apps.reporting.services.prisma_reporting_service.get_raw_results_count")
    @patch(
        "apps.reporting.services.search_source_service.get_search_source_breakdown",
        return_value=[],
    )
    def test_returns_all_expected_keys(
        self, _mock_source, mock_raw, mock_exec, mock_queries
    ):
        """All keys expected by _build_flow_data_structure should be present."""
        mock_queries.return_value = {"queries": []}
        mock_exec.return_value = {"executions": []}
        mock_raw.return_value = 100

        result = self.service._gather_identification_data(str(self.session.id))

        expected_keys = {
            "database",
            "other_sources",
            "total",
            "websites",
            "organizations",
            "citation_searching",
            "queries_data",
            "executions_data",
            "search_source_breakdown",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    @patch("apps.reporting.services.prisma_reporting_service.get_session_queries_data")
    @patch(
        "apps.reporting.services.prisma_reporting_service.get_session_executions_data"
    )
    @patch("apps.reporting.services.prisma_reporting_service.get_raw_results_count")
    @patch(
        "apps.reporting.services.search_source_service.get_search_source_breakdown",
        return_value=[],
    )
    def test_no_fake_percentages(self, _mock_source, mock_raw, mock_exec, mock_queries):
        """With no executions, websites/organizations should be 0 (not fake percentages)."""
        mock_queries.return_value = {"queries": []}
        mock_exec.return_value = {"executions": []}
        mock_raw.return_value = 100

        result = self.service._gather_identification_data(str(self.session.id))

        # Previously these would be fake percentages like 60, 25, 15
        self.assertEqual(result["websites"], 0)
        self.assertEqual(result["organizations"], 0)
        self.assertEqual(result["citation_searching"], 0)
        # database total should still be correct
        self.assertEqual(result["database"], 100)
