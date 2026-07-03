"""
Test suite for Issue #100: Results filtering transparency and user visibility.

This test suite validates the complete resolution of the filtering problem
where users were losing visibility into result processing and filtering decisions.

Key test scenarios:
1. Filtering statistics calculation and accuracy
2. API response includes filtering transparency data
3. Template rendering of filtering information
4. Real-time updates of filtering stats
5. Accounting check validation (100 raw → 50 filtered → final count)
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.results_manager.models import ProcessedResult, ProcessingSession
from apps.results_manager.views import get_filtering_statistics
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class FilteringTransparencyTestCase(TestCase):
    """Base test case with common setup for Issue #100 tests."""

    def setUp(self):
        """Set up test data including the specific scenario from Issue #100."""
        self.user = create_test_user()
        self.client = Client()
        self.client.force_login(self.user)

        # Create search session matching Issue #100 scenario
        self.session = SearchSession.objects.create(
            title="Issue #100 Test Session - Progress Testing",
            description="Reproduce the 100→50→59 result scenario",
            owner=self.user,
            status="processing_results",
        )

        # Create processing session
        self.processing_session = ProcessingSession.objects.create(
            search_session=self.session,
            status="in_progress",
            total_raw_results=100,  # Issue #100 scenario: started with 100
        )

        # Create search strategy first
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["healthcare workers"],
            interest_terms=["telemedicine"],
            context_terms=["rural areas"],
        )

        # Create search query and execution to simulate raw results
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="healthcare workers telemedicine rural areas",
            query_type="domain-specific",
            target_domain="who.int",
            execution_order=1,
        )

        self.execution = SearchExecution.objects.create(
            query=self.query,
            search_engine="serper",
            status="completed",
        )

    def create_raw_results(self, count=100):
        """Create raw search results for testing."""
        raw_results = []
        for i in range(count):
            raw_result = RawSearchResult.objects.create(
                execution=self.execution,
                title=f"Test Result {i + 1}: Healthcare in Rural Areas",
                link=f"https://example-{i}.com/article-{i}",
                snippet=f"This is test result {i + 1} about healthcare in rural areas.",
                position=i + 1,
                has_pdf=(i % 3 == 0),  # Every 3rd result is a PDF
                language_code="en",
            )
            raw_results.append(raw_result)
        return raw_results

    def create_processed_results_scenario_100(self):
        """Create the specific Issue #100 scenario: 100→50→59 results."""
        # Create 100 raw results
        raw_results = self.create_raw_results(100)

        processed_results = []

        # Scenario: 50 successful, 30 filtered (duplicates), 20 errors
        # This simulates the Issue #100 problem where results were lost

        # 50 successful results (available for review)
        for i in range(50):
            result = ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw_results[i],
                title=f"Processed Result {i + 1}",
                url=f"https://normalized-{i}.com/article",
                snippet=f"Processed snippet {i + 1}",
                document_type="pdf" if i % 3 == 0 else "webpage",
                language="en",
                processing_status="success",
            )
            processed_results.append(result)

        # 30 filtered results (duplicates - Issue #100 transparency fix)
        for i in range(50, 80):
            # Use valid document type based on original detection
            doc_type = "pdf" if raw_results[i].has_pdf else "webpage"
            result = ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw_results[i],
                title=raw_results[i].title,  # Keep original title
                url=f"https://normalized-{i % 25}.com/article",  # No prefix needed
                snippet=f"Filtered snippet {i + 1}",
                document_type=doc_type,  # Use valid document type
                language="en",
                processing_status="filtered",
                processing_error_category="duplicate_result",
                processing_error_message=f"Duplicate URL detected: {raw_results[i].link}",
            )
            processed_results.append(result)

        # 20 error results (processing failures - Issue #100 transparency fix)
        error_categories = [
            "url_normalization_failed",
            "document_type_detection_failed",
            "missing_required_field",
            "unknown_error",
        ]
        for i in range(80, 100):
            category = error_categories[i % len(error_categories)]
            # Use valid document type even for errors
            doc_type = "pdf" if raw_results[i].has_pdf else "webpage"
            result = ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw_results[i],
                title=raw_results[i].title,  # Keep original title
                url=f"https://failed-{i}.com/article",  # No prefix needed
                snippet=f"Error snippet {i + 1}",
                document_type=doc_type,  # Use valid document type
                language="en",
                processing_status="error",
                processing_error_category=category,
                processing_error_message=f"Processing failed: {category}",
            )
            processed_results.append(result)

        return processed_results


class TestFilteringStatisticsCalculation(FilteringTransparencyTestCase):
    """Test the filtering statistics calculation function."""

    def test_get_filtering_statistics_issue_100_scenario(self):
        """Test filtering statistics for the exact Issue #100 scenario."""
        # Create the Issue #100 scenario
        self.create_processed_results_scenario_100()

        # Get filtering statistics
        stats = get_filtering_statistics(self.session.id)

        # Verify raw results count
        self.assertEqual(stats["raw_results_retrieved"], 100)
        self.assertEqual(stats["total_processed_records"], 100)

        # Verify status breakdown
        expected_status_counts = {
            "success": 50,
            "filtered": 30,
            "error": 20,
        }
        self.assertEqual(stats["results_by_status"], expected_status_counts)

        # Verify percentages
        self.assertEqual(stats["success_rate_percent"], 50.0)
        self.assertEqual(stats["filter_rate_percent"], 30.0)
        self.assertEqual(stats["error_rate_percent"], 20.0)

        # Verify accounting check
        accounting = stats["accounting_check"]
        self.assertEqual(accounting["raw_count"], 100)
        self.assertEqual(accounting["processed_count"], 100)
        self.assertEqual(accounting["difference"], 0)
        self.assertTrue(accounting["is_complete"])

        # Verify filter reasons
        self.assertIn("duplicate_result", stats["filter_reasons"])
        self.assertEqual(stats["filter_reasons"]["duplicate_result"], 30)

        # Verify error categories
        self.assertEqual(len(stats["error_categories"]), 4)
        self.assertIn("url_normalization_failed", stats["error_categories"])

    def test_empty_session_statistics(self):
        """Test filtering statistics for session with no results."""
        stats = get_filtering_statistics(self.session.id)

        self.assertEqual(stats["raw_results_retrieved"], 0)
        self.assertEqual(stats["total_processed_records"], 0)
        self.assertEqual(stats["results_by_status"]["success"], 0)
        self.assertEqual(stats["results_by_status"]["filtered"], 0)
        self.assertEqual(stats["results_by_status"]["error"], 0)
        self.assertTrue(stats["accounting_check"]["is_complete"])

    def test_partial_processing_statistics(self):
        """Test statistics when processing is incomplete."""
        # Create 50 raw results but only 30 processed
        raw_results = self.create_raw_results(50)

        # Only create 30 processed results (20 missing)
        for i in range(30):
            ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw_results[i],
                title=f"Partial Result {i + 1}",
                url=f"https://partial-{i}.com/",
                processing_status="success",
            )

        stats = get_filtering_statistics(self.session.id)

        self.assertEqual(stats["raw_results_retrieved"], 50)
        self.assertEqual(stats["total_processed_records"], 30)
        self.assertEqual(stats["accounting_check"]["difference"], 20)
        self.assertFalse(stats["accounting_check"]["is_complete"])


class TestProcessingStatusAPI(FilteringTransparencyTestCase):
    """Test the processing status API includes filtering transparency."""

    def test_api_includes_filtering_stats(self):
        """Test that API response includes filtering statistics."""
        # Create Issue #100 scenario
        self.create_processed_results_scenario_100()

        # Call the API
        url = reverse("results_manager:processing_status_api", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        data = response.json()

        # Verify filtering stats are included
        self.assertIn("filtering_stats", data)
        filtering_stats = data["filtering_stats"]

        # Verify key transparency metrics are present
        self.assertEqual(filtering_stats["raw_results_retrieved"], 100)
        self.assertEqual(filtering_stats["total_processed_records"], 100)
        self.assertIn("results_by_status", filtering_stats)
        self.assertIn("accounting_check", filtering_stats)
        self.assertIn("filter_reasons", filtering_stats)
        self.assertIn("error_categories", filtering_stats)

        # Verify the exact Issue #100 numbers
        self.assertEqual(filtering_stats["results_by_status"]["success"], 50)
        self.assertEqual(filtering_stats["results_by_status"]["filtered"], 30)
        self.assertEqual(filtering_stats["results_by_status"]["error"], 20)

    def test_api_real_time_updates(self):
        """Test that filtering stats update in real-time as processing progresses."""
        # Initially no results
        url = reverse("results_manager:processing_status_api", args=[self.session.id])
        response = self.client.get(url)
        initial_data = response.json()

        self.assertEqual(initial_data["filtering_stats"]["total_processed_records"], 0)

        # Add some processed results
        raw_results = self.create_raw_results(10)
        for i in range(5):
            ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw_results[i],
                title=f"Progressive Result {i + 1}",
                url=f"https://progressive-{i}.com/",
                processing_status="success",
            )

        # Check updated stats
        response = self.client.get(url)
        updated_data = response.json()

        self.assertEqual(updated_data["filtering_stats"]["total_processed_records"], 5)
        self.assertEqual(
            updated_data["filtering_stats"]["results_by_status"]["success"], 5
        )


class TestProcessingStatusTemplate(FilteringTransparencyTestCase):
    """Test the processing status template displays filtering transparency."""

    def test_template_renders_filtering_stats(self):
        """Test that template renders filtering statistics correctly."""
        # Create Issue #100 scenario
        self.create_processed_results_scenario_100()

        # Load the template
        url = reverse("results_manager:processing_status", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check that filtering stats are in context
        self.assertIn("filtering_stats", response.context)
        filtering_stats = response.context["filtering_stats"]
        self.assertEqual(filtering_stats["raw_results_retrieved"], 100)

        # Check that HTML contains the transparency section
        html_content = response.content.decode()
        self.assertIn("Result Processing Transparency", html_content)
        self.assertIn("Issue #100 Fix", html_content)
        self.assertIn("Retrieved from API", html_content)
        self.assertIn("Successfully Processed", html_content)
        self.assertIn("Filtered Out", html_content)
        self.assertIn("Processing Errors", html_content)

        # Check specific numbers are displayed
        self.assertIn("100", html_content)  # Raw results
        self.assertIn("50", html_content)  # Successful
        self.assertIn("30", html_content)  # Filtered
        self.assertIn("20", html_content)  # Errors

    def test_template_handles_no_filtering_stats(self):
        """Test template gracefully handles missing filtering stats."""
        # Don't create any processed results

        url = reverse("results_manager:processing_status", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Should still render without errors
        html_content = response.content.decode()
        self.assertIn("Processing Search Results", html_content)

    def test_accounting_check_alerts(self):
        """Test that accounting check alerts work correctly."""
        # Create scenario with missing results (incomplete accounting)
        raw_results = self.create_raw_results(100)

        # Only process 80 results (20 missing = incomplete accounting)
        for i in range(80):
            ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw_results[i],
                title=f"Incomplete Result {i + 1}",
                url=f"https://incomplete-{i}.com/",
                processing_status="success",
            )

        url = reverse("results_manager:processing_status", args=[self.session.id])
        response = self.client.get(url)

        html_content = response.content.decode()

        # Should show warning alert
        self.assertIn("alert-warning", html_content)
        self.assertIn("20 results may be unaccounted for", html_content)


class TestFilteringTransparencyIntegration(FilteringTransparencyTestCase):
    """Integration tests for complete filtering transparency workflow."""

    def test_complete_issue_100_workflow(self):
        """Test the complete workflow that resolves Issue #100."""
        # create_processed_results_scenario_100 internally creates 100 raw results
        self.create_processed_results_scenario_100()

        # 3. Verify API provides complete transparency
        api_url = reverse(
            "results_manager:processing_status_api", args=[self.session.id]
        )
        api_response = self.client.get(api_url)
        api_data = api_response.json()

        # 4. Verify template shows transparency
        template_url = reverse(
            "results_manager:processing_status", args=[self.session.id]
        )
        template_response = self.client.get(template_url)

        # 5. Validate complete accounting (the key Issue #100 fix)
        filtering_stats = api_data["filtering_stats"]

        # All raw results must be accounted for
        self.assertTrue(filtering_stats["accounting_check"]["is_complete"])
        self.assertEqual(
            filtering_stats["raw_results_retrieved"],
            filtering_stats["total_processed_records"],
        )

        # User can see exactly what happened to each result
        total_accounted = (
            filtering_stats["results_by_status"]["success"]
            + filtering_stats["results_by_status"]["filtered"]
            + filtering_stats["results_by_status"]["error"]
        )
        self.assertEqual(total_accounted, 100)

        # Template provides clear explanations
        html_content = template_response.content.decode()
        self.assertIn("All retrieved results have been accounted for", html_content)
        self.assertIn("Duplicate URLs detected", html_content)
        self.assertIn("ensuring complete transparency", html_content)

    def test_progressive_disclosure_interaction(self):
        """Test that the collapsible details work correctly."""
        self.create_processed_results_scenario_100()

        url = reverse("results_manager:processing_status", args=[self.session.id])
        response = self.client.get(url)
        html_content = response.content.decode()

        # Check for collapsible elements (custom JS toggle, not Bootstrap)
        self.assertIn("filteringDetails", html_content)
        self.assertIn("Show Details", html_content)

        # Check detailed breakdown sections
        self.assertIn("Filtering Breakdown", html_content)

    def test_error_handling_empty_session(self):
        """Test that API handles sessions with no processing session."""
        # Create a new session with no processing session
        empty_session = SearchSession.objects.create(
            title="Empty Session",
            owner=self.user,
            status="processing_results",
        )

        url = reverse("results_manager:processing_status_api", args=[empty_session.id])
        response = self.client.get(url)

        # Should return pending status when no processing session exists
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "pending")


class TestFilteringStatsPerformance(FilteringTransparencyTestCase):
    """Test performance aspects of filtering statistics."""

    def test_stats_calculation_performance_large_dataset(self):
        """Test that statistics calculation performs well with large datasets."""
        # Create a large dataset (1000 results)
        raw_results = self.create_raw_results(1000)

        # Create processed results with various statuses
        statuses = ["success", "filtered", "error"]
        for i, raw_result in enumerate(raw_results):
            status = statuses[i % 3]
            ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw_result,
                title=f"Large Dataset Result {i + 1}",
                url=f"https://large-{i}.com/",
                processing_status=status,
                processing_error_category="duplicate_result"
                if status == "filtered"
                else "",
            )

        # Measure statistics calculation performance
        import time

        start_time = time.time()
        stats = get_filtering_statistics(self.session.id)
        end_time = time.time()

        # Should complete quickly (under 1 second for 1000 results)
        calculation_time = end_time - start_time
        self.assertLess(
            calculation_time,
            1.0,
            f"Statistics calculation took {calculation_time:.2f}s for 1000 results",
        )

        # Verify accuracy despite size
        self.assertEqual(stats["total_processed_records"], 1000)
        self.assertEqual(stats["raw_results_retrieved"], 1000)

    def test_api_response_time(self):
        """Test API response time with filtering stats included."""
        self.create_processed_results_scenario_100()

        url = reverse("results_manager:processing_status_api", args=[self.session.id])

        import time

        start_time = time.time()
        response = self.client.get(url)
        end_time = time.time()

        response_time = end_time - start_time

        self.assertEqual(response.status_code, 200)
        self.assertLess(response_time, 0.5, f"API response took {response_time:.2f}s")

        # Verify filtering stats are included
        data = response.json()
        self.assertIn("filtering_stats", data)
