"""
Test cases for reporting app services.

This module tests service methods for PRISMA reporting,
export functionality, and data analysis services.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.reporting.services.export_service import ExportService
from apps.reporting.services.performance_analytics_service import (
    PerformanceAnalyticsService,
)
from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.reporting.services.prisma_reporting_service import PrismaReportingService
from apps.reporting.services.result_analysis_service import SearchResultAnalysisService
from apps.reporting.services.search_strategy_reporting_service import (
    SearchStrategyReportingService,
)
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import (
    ConflictResolution,
    ReviewerDecision,
    SimpleReviewDecision,
)
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution

User = get_user_model()


class BaseServiceTestCase(TestCase):
    """Base test case with common setup for service tests."""

    def setUp(self):
        """Create test data for services."""
        self.user = create_test_user()

        # Create session with complete workflow
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test Description",
            owner=self.user,
            status="completed",
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
        )

        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test search query",
            is_active=True,
        )

        # Create executions
        self.execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
            results_count=100,
            duration_seconds=1.5,
            started_at=timezone.now() - timedelta(hours=1),
            completed_at=timezone.now(),
        )

        # Create raw results
        self.raw_results = []
        for i in range(10):
            raw = RawSearchResult.objects.create(
                execution=self.execution,
                position=i + 1,
                title=f"Result {i}",
                link=f"https://example.com/{i}",
                snippet=f"Snippet {i}",
            )
            self.raw_results.append(raw)

        # Create processed results
        self.processed_results = []
        for i in range(10):
            processed = ProcessedResult.objects.create(
                session=self.session,
                raw_result=self.raw_results[i] if i < len(self.raw_results) else None,
                title=f"Processed Result {i}",
                url=f"https://example.com/{i}",
                snippet=f"Processed snippet {i}",
            )
            self.processed_results.append(processed)

        # Create review decisions
        self.review_decisions = []
        for i in range(7):  # Only review 7 out of 10
            decision = SimpleReviewDecision.objects.create(
                result=self.processed_results[i],
                session=self.session,
                reviewer=self.user,
                decision="include" if i < 5 else "exclude",
                exclusion_reason="not_relevant" if i >= 5 else "",
            )
            self.review_decisions.append(decision)


class PrismaReportingServiceTest(BaseServiceTestCase):
    """Test PRISMA reporting service."""

    def setUp(self):
        super().setUp()
        self.service = PrismaReportingService()

    def test_generate_prisma_flow_data(self):
        """Test PRISMA flow data generation."""
        flow_data = self.service.generate_prisma_flow_data(str(self.session.id))

        # Check PRISMA 2020 structure
        self.assertIn("identification", flow_data)
        self.assertIn("screening", flow_data)
        self.assertIn("eligibility", flow_data)
        self.assertIn("included", flow_data)

        # Check identification phase
        identification = flow_data["identification"]
        self.assertIn("total", identification)
        self.assertIn("database", identification)

        # Check screening phase
        screening = flow_data["screening"]
        self.assertIn("records_screened", screening)
        self.assertIn("duplicates_removed", screening)

        # Check included phase
        included = flow_data["included"]
        self.assertIn("studies_included", included)

    def test_get_exclusion_reasons(self):
        """Test exclusion reason analysis."""
        reasons = self.service.get_exclusion_reasons(str(self.session.id))

        # Should have reasons for excluded items
        self.assertIsInstance(reasons, dict)
        self.assertGreater(len(reasons), 0)  # Should have at least one reason

    def test_analyze_exclusion_reasons(self):
        """Test detailed exclusion analysis."""
        analysis = self.service.analyze_exclusion_reasons(str(self.session.id))

        self.assertIn("total_exclusions", analysis)
        self.assertIn("reasons", analysis)
        self.assertIn("top_reasons", analysis)
        self.assertIn("most_common_reason", analysis)

        self.assertEqual(analysis["total_exclusions"], 2)

    def test_generate_checklist_data(self):
        """Test PRISMA checklist generation."""
        checklist = self.service.generate_checklist_data(str(self.session.id))

        self.assertIn("checklist_items", checklist)
        self.assertIn("completion_summary", checklist)
        self.assertIn("session_id", checklist)

        # Check some items exist
        items = checklist["checklist_items"]
        self.assertTrue(any(item["section"] == "Title" for item in items))
        self.assertTrue(any(item["section"] == "Abstract" for item in items))

    def test_export_prisma_checklist(self):
        """Test PRISMA checklist export format."""
        export_data = self.service.export_prisma_checklist(str(self.session.id))

        self.assertIn("session_id", export_data)
        self.assertIn("checklist_items", export_data)
        self.assertIn("completion_summary", export_data)

        # Check checklist has items
        items = export_data["checklist_items"]
        self.assertGreater(len(items), 0)

    def test_service_with_no_results(self):
        """Test service handles sessions with no results."""
        empty_session = SearchSession.objects.create(
            title="Empty Session", owner=self.user
        )

        flow_data = self.service.generate_prisma_flow_data(str(empty_session.id))

        # Should return valid structure with zeros
        self.assertEqual(flow_data["identification"]["total"], 0)
        self.assertEqual(flow_data["included"]["studies_included"], 0)

    def test_service_with_pending_reviews(self):
        """Test service handles pending reviews correctly."""
        # Mark some as pending
        self.review_decisions[0].decision = "pending"
        self.review_decisions[0].save()

        flow_data = self.service.generate_prisma_flow_data(str(self.session.id))

        # Pending should not be counted as included or excluded
        self.assertEqual(flow_data["included"]["studies_included"], 4)  # Was 5


class PrismaReportingServiceWF2ExclusionTest(DisablePersonalOrgSignalMixin, TestCase):
    """
    WF2 get_exclusion_reasons must aggregate ReviewerDecision per-result.

    Regression for #198: before the fix, WF2 sessions always returned an empty
    dict because SimpleReviewDecision is empty for WF2.
    """

    def setUp(self):
        self.org = Organisation.objects.create(
            name="WF2 Excl Org", slug="wf2-excl-org-198"
        )
        self.reviewer1 = create_test_user(
            username_prefix="wf2excl_r1", email="wf2excl_r1@test.com"
        )
        self.reviewer2 = create_test_user(
            username_prefix="wf2excl_r2", email="wf2excl_r2@test.com"
        )
        OrganisationMembership.objects.create(
            organisation=self.org, user=self.reviewer1, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            organisation=self.org, user=self.reviewer2, role="REVIEWER"
        )

        self.session = SearchSession.objects.create(
            organisation=self.org,
            title="WF2 Exclusion Reasons Test",
            owner=self.reviewer1,
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            version=1,
            organisation=self.org,
            created_by=self.reviewer1,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # Result 1: unanimous EXCLUDE with "not relevant" reason
        result_excl1 = ProcessedResult.objects.create(
            session=self.session,
            title="Unanimous Exclude 1",
            url="https://example.com/excl1",
            snippet="test",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_excl1,
            reviewer=self.reviewer1,
            decision="EXCLUDE",
            exclusion_reason="not relevant",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_excl1,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            exclusion_reason="not relevant",
            screening_stage="SCREENING",
        )

        # Result 2: conflict resolved to EXCLUDE with "duplicate" reason
        result_conflict = ProcessedResult.objects.create(
            session=self.session,
            title="Conflict Resolved Exclude",
            url="https://example.com/conflict-excl",
            snippet="test",
        )
        d_r1_include = ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_conflict,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        d_r2_exclude = ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_conflict,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            exclusion_reason="duplicate",
            screening_stage="SCREENING",
        )
        conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=result_conflict,
            status=ConflictResolution.STATUS_RESOLVED,
            final_decision=d_r2_exclude,
            conflict_type="INCLUDE_EXCLUDE",
        )
        conflict.conflicting_decisions.add(d_r1_include, d_r2_exclude)

        # Result 3: unanimous INCLUDE -- must NOT appear in exclusion reasons
        result_include = ProcessedResult.objects.create(
            session=self.session,
            title="Unanimous Include",
            url="https://example.com/incl",
            snippet="test",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_include,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result_include,
            reviewer=self.reviewer2,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )

        self.service = PrismaReportingService()
        self.session_id = str(self.session.id)

    def test_wf2_exclusion_reasons_not_empty(self):
        """WF2 sessions must return a non-empty reason dict (regression for #198)."""
        reasons = self.service.get_exclusion_reasons(self.session_id)
        self.assertIsInstance(reasons, dict)
        self.assertGreater(len(reasons), 0)

    def test_wf2_unanimous_exclude_reason_counted(self):
        """Unanimous-EXCLUDE result contributes its reason once."""
        reasons = self.service.get_exclusion_reasons(self.session_id)
        # "not relevant" maps to "not_relevant" standardized key
        from apps.reporting.constants import PRISMAConstants

        expected_key = PRISMAConstants.STANDARD_EXCLUSION_REASONS["not_relevant"]
        self.assertIn(expected_key, reasons)
        self.assertEqual(reasons[expected_key], 1)

    def test_wf2_resolved_conflict_exclude_reason_counted(self):
        """Resolved-conflict EXCLUDE result contributes its reason once."""
        reasons = self.service.get_exclusion_reasons(self.session_id)
        from apps.reporting.constants import PRISMAConstants

        expected_key = PRISMAConstants.STANDARD_EXCLUSION_REASONS["duplicate"]
        self.assertIn(expected_key, reasons)
        self.assertEqual(reasons[expected_key], 1)

    def test_wf2_included_result_not_in_reasons(self):
        """Included results must not appear in the exclusion reason breakdown."""
        reasons = self.service.get_exclusion_reasons(self.session_id)
        # Total unique reason entries should be exactly 2 (not_relevant + duplicate)
        self.assertEqual(sum(reasons.values()), 2)

    def test_wf2_coded_reason_resolves_to_canonical_label(self):
        """WF2 reasons stored as choice CODES (e.g. 'not_grey_lit', the form the
        screening UI submits) must resolve to the same canonical label WF1 uses,
        not fall through to a title-cased code. Regression for the #198 CodeRabbit
        finding: passing 'not_grey_lit' to the prose mapper produced 'Not_Grey_Lit'."""
        from apps.reporting.constants import PRISMAConstants

        result = ProcessedResult.objects.create(
            session=self.session,
            title="Coded Reason Exclude",
            url="https://example.com/coded",
            snippet="test",
        )
        for reviewer in (self.reviewer1, self.reviewer2):
            ReviewerDecision.objects.create(
                organisation=self.org,
                result=result,
                reviewer=reviewer,
                decision="EXCLUDE",
                exclusion_reason="not_grey_lit",  # choice code, not prose
                screening_stage="SCREENING",
            )

        reasons = self.service.get_exclusion_reasons(self.session_id)
        expected_label = PRISMAConstants.STANDARD_EXCLUSION_REASONS["not_grey_lit"]
        self.assertIn(expected_label, reasons)
        self.assertEqual(reasons[expected_label], 1)
        self.assertNotIn("Not_Grey_Lit", reasons)


class ExportServiceTest(BaseServiceTestCase):
    """Test export service functionality."""

    def setUp(self):
        super().setUp()
        self.service = ExportService()

    def test_export_to_csv(self):
        """Test CSV export with studies data."""
        data = {
            "studies": [
                {"title": "Result 1", "url": "http://example.com/1"},
                {"title": "Result 2", "url": "http://example.com/2"},
            ]
        }

        result = self.service.export_to_csv(data, export_type="studies")

        # Check CSV content
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 3)  # Header + 2 rows
        self.assertIn("title", lines[0])
        self.assertIn("url", lines[0])
        self.assertIn("Result 1", lines[1])


class PerformanceAnalyticsServiceTest(BaseServiceTestCase):
    """Test performance analytics service."""

    def setUp(self):
        super().setUp()
        self.service = PerformanceAnalyticsService()

    def test_calculate_search_performance_metrics(self):
        """Test search performance metrics calculation."""
        metrics = self.service.calculate_search_performance_metrics(
            str(self.session.id)
        )

        # Check metric structure matches actual service output
        self.assertIn("total_executions", metrics)
        self.assertIn("successful_executions", metrics)
        self.assertIn("success_rate", metrics)
        self.assertIn("total_processed", metrics)
        self.assertIn("include_count", metrics)
        self.assertIn("exclude_count", metrics)
        self.assertIn("precision", metrics)
        self.assertIn("recommendations", metrics)

        # Check values
        self.assertEqual(metrics["total_executions"], 1)
        self.assertEqual(metrics["successful_executions"], 1)
        self.assertEqual(metrics["success_rate"], 100.0)

    def test_generate_execution_timeline(self):
        """Test execution timeline generation."""
        # Create more executions at different times
        for i in range(3):
            SearchExecution.objects.create(
                query=self.query,
                status="completed",
                results_count=50,
                started_at=timezone.now() - timedelta(hours=i + 2),
                completed_at=timezone.now() - timedelta(hours=i + 1),
            )

        timeline = self.service.generate_execution_timeline(str(self.session.id))

        # Check timeline structure
        self.assertIn("executions", timeline)
        self.assertIn("summary", timeline)

        # Check executions ordered by time
        executions = timeline["executions"]
        self.assertEqual(len(executions), 4)  # Original + 3 new

        # Check summary
        summary = timeline["summary"]
        self.assertIn("total_duration", summary)
        self.assertIn("queries_per_hour", summary)


class SearchResultAnalysisServiceTest(BaseServiceTestCase):
    """Test search result analysis service."""

    def setUp(self):
        super().setUp()
        self.service = SearchResultAnalysisService()

    def test_calculate_result_statistics(self):
        """Test result statistics calculation."""
        stats = self.service.calculate_result_statistics(str(self.session.id))

        # Check statistics structure matches actual service output
        self.assertIn("total_results", stats)
        self.assertIn("results_included", stats)
        self.assertIn("results_excluded", stats)
        self.assertIn("results_pending", stats)
        self.assertIn("duplicates_removed", stats)
        self.assertIn("completion_percentage", stats)
        self.assertIn("included_count", stats)
        self.assertIn("excluded_count", stats)
        self.assertIn("pending_count", stats)
        self.assertIn("review_progress", stats)

        # Check total results
        self.assertEqual(stats["total_results"], 10)

    def test_analyze_quality_distribution(self):
        """Test quality distribution analysis."""
        distribution = self.service.analyze_quality_distribution(str(self.session.id))

        # Check distribution structure matches actual service output
        self.assertIn("document_type_distribution", distribution)
        self.assertIn("quality_summary", distribution)
        self.assertIn("inclusion_rate", distribution)
        self.assertIn("pdf_inclusion_rate", distribution)
        self.assertIn("average_score", distribution)


class SearchStrategyReportingServiceTest(BaseServiceTestCase):
    """Test search strategy reporting service."""

    def setUp(self):
        super().setUp()
        self.service = SearchStrategyReportingService()

    def test_analyze_search_strategy(self):
        """Test search strategy analysis."""
        analysis = self.service.analyze_search_strategy(str(self.session.id))

        # Check analysis structure matches analyzer output
        self.assertIn("overview", analysis)
        self.assertIn("framework", analysis)
        self.assertIn("queries", analysis)
        self.assertIn("execution_summary", analysis)
        self.assertIn("insights", analysis)

        # Check insights
        insights = analysis["insights"]
        self.assertIn("total_queries", insights)
        self.assertIn("coverage", insights)
        self.assertIn("effectiveness", insights)

    def test_calculate_query_effectiveness(self):
        """Test query effectiveness calculation."""
        effectiveness = self.service.calculate_query_effectiveness(str(self.session.id))

        # Check effectiveness metrics match analyzer output
        self.assertIn("overall_performance", effectiveness)
        self.assertIn("query_metrics", effectiveness)
        self.assertIn("recommendations", effectiveness)

        # Check query_metrics is a list
        self.assertIsInstance(effectiveness["query_metrics"], list)
        self.assertIsInstance(effectiveness["recommendations"], list)
