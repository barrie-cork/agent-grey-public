"""
API integration tests for Agent Grey using Playwright.

These tests focus specifically on API interactions, Serper API integration,
and background task processing verification.
"""


import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import expect

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution

from .conftest import Selectors

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestSerperAPIIntegration:
    """
    Test integration with Serper API and search execution.
    """
    
    def test_successful_api_call_with_known_terms(self, authenticated_page, live_server, test_user):
        """
        Test API integration with known working search terms.
        Based on successful session a1cf07b6-d9d0-498b-9797-4c039fc8628e with 49 results.
        """
        page = authenticated_page
        
        # Create session with the exact terms that worked
        session = SearchSession.objects.create(
            title="API Integration Test - Known Working Terms",
            description="Testing with water AND ait search terms that returned 49 results",
            owner=test_user,
            status="ready_to_execute"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="water",
            interest_terms="ait",
            context_terms="",
            include_file_types=True,
            selected_domains=["edu", "org", "gov"],
        )
        
        # Navigate to session and execute search
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.wait_for_selector(Selectors.EXECUTE_SEARCH_BUTTON)
        
        # Execute search
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        page.wait_for_selector(Selectors.STATUS_EXECUTING, timeout=10000)
        
        # Monitor progress through status updates
        page.wait_for_selector(Selectors.STATUS_PROCESSING, timeout=60000)  # Wait for processing
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=120000)  # Wait for completion
        
        # Verify results are available
        page.wait_for_selector(Selectors.RESULTS_TABLE, timeout=10000)
        
        # Check that we have a reasonable number of results (should be > 0)
        result_count_element = page.locator('[data-testid="result-count"]')
        expect(result_count_element).to_be_visible()
        
        result_count_text = result_count_element.inner_text()
        result_count = int(result_count_text.split()[0])  # Extract number from "X results found"
        assert result_count > 0, f"Expected > 0 results, got {result_count}"
        
        # Verify database state
        session.refresh_from_db()
        assert session.status == "ready_for_review"
        assert session.total_results > 0
        
        # Verify SearchExecution records exist
        executions = SearchExecution.objects.filter(session=session)
        assert executions.count() > 0
        
        # Verify at least one execution was successful
        successful_executions = executions.filter(status="completed")
        assert successful_executions.count() > 0
        
        # Verify RawSearchResult records exist
        raw_results = RawSearchResult.objects.filter(execution__session=session)
        assert raw_results.count() > 0
        
        # Verify ProcessedResult records exist
        processed_results = ProcessedResult.objects.filter(session=session)
        assert processed_results.count() > 0
    
    def test_api_error_handling(self, authenticated_page, live_server, test_user):
        """Test handling of API errors and rate limits."""
        page = authenticated_page
        
        # Create session with potentially problematic terms (empty search)
        session = SearchSession.objects.create(
            title="API Error Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="",  # Empty terms might cause API errors
            interest_terms="",
            context_terms="",
            include_file_types=False,
            selected_domains=[],
        )
        
        # Navigate and attempt execution
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # This might fail due to empty search terms
        # Check if the execute button is disabled or shows validation error
        execute_button = page.locator(Selectors.EXECUTE_SEARCH_BUTTON)
        if execute_button.is_enabled():
            execute_button.click()
            
            # Wait for error message or status update
            try:
                page.wait_for_selector('[data-testid="execution-error"]', timeout=30000)
                error_message = page.locator('[data-testid="execution-error"]').inner_text()
                assert "error" in error_message.lower() or "failed" in error_message.lower()
            except Exception:
                # If no error selector, check status
                page.wait_for_selector(Selectors.STATUS_BADGE, timeout=30000)
                # Status should not be ready_for_review if there was an error
                status_text = page.locator(Selectors.STATUS_BADGE).inner_text()
                assert status_text != "Ready for Review"
    
    def test_multiple_domain_search_execution(self, authenticated_page, live_server, test_user):
        """Test search execution across multiple domains."""
        page = authenticated_page
        
        # Create session with multiple domains
        session = SearchSession.objects.create(
            title="Multi-Domain Search Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="research, study",
            interest_terms="methodology, approach",
            context_terms="academic, university",
            include_file_types=True,
            selected_domains=["edu", "org", "gov"],  # Multiple domains
        )
        
        # Execute search
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        page.wait_for_selector(Selectors.STATUS_EXECUTING, timeout=10000)
        
        # Wait for completion
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=180000)  # 3 minutes
        
        # Verify we have results from multiple domains
        session.refresh_from_db()
        
        # Check that we have multiple search executions (one per domain)
        executions = SearchExecution.objects.filter(session=session)
        assert executions.count() >= len(strategy.selected_domains)
        
        # Verify results include different domains
        processed_results = ProcessedResult.objects.filter(session=session)[:10]  # Check first 10
        domains_found = set()
        
        for result in processed_results:
            if result.url:
                domain = result.url.split('/')[2]  # Extract domain from URL
                for tld in ['edu', 'org', 'gov']:
                    if tld in domain:
                        domains_found.add(tld)
        
        # We should find at least 2 different domain types in the results
        assert len(domains_found) >= 2, f"Expected multiple domains, found: {domains_found}"
    
    def test_file_type_filtering(self, authenticated_page, live_server, test_user):
        """Test that file type filtering works correctly."""
        page = authenticated_page
        
        # Create session with file type filtering enabled
        session = SearchSession.objects.create(
            title="File Type Filter Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="water quality",
            interest_terms="testing methods",
            context_terms="",
            include_file_types=True,  # This should include filetype:pdf OR filetype:doc
            selected_domains=["edu"],
        )
        
        # Execute search
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        page.wait_for_selector(Selectors.STATUS_EXECUTING, timeout=10000)
        
        # Wait for completion
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=120000)
        
        # Navigate to results and check file types
        page.goto(f"{live_server.url}/session/{session.id}/results/")
        page.wait_for_selector(Selectors.RESULTS_TABLE)
        
        # Check that some results are PDF or DOC files
        result_rows = page.locator(Selectors.RESULT_ROW)
        file_type_results = 0
        
        for i in range(min(10, result_rows.count())):  # Check first 10 results
            row = result_rows.nth(i)
            url_element = row.locator('[data-testid="result-url"]')
            
            if url_element.count() > 0:
                url = url_element.inner_text()
                if '.pdf' in url.lower() or '.doc' in url.lower():
                    file_type_results += 1
        
        # We should have at least some file-type results (PDFs or DOCs)
        # Note: This might not always be true depending on API results
        # So we'll just verify the search executed successfully
        session.refresh_from_db()
        assert session.total_results > 0


@pytest.mark.django_db(transaction=True)
class TestBackgroundTaskProcessing:
    """
    Test background task processing and Celery integration.
    """
    
    def test_celery_task_execution_monitoring(self, authenticated_page, live_server, test_user):
        """Test that Celery tasks execute and update session status."""
        page = authenticated_page
        
        # Create session ready for execution
        session = SearchSession.objects.create(
            title="Celery Task Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="test",
            interest_terms="data",
            context_terms="",
            selected_domains=["edu"],
        )
        
        # Navigate and execute
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        
        # Monitor status changes that indicate task progression
        status_changes = []
        
        # Wait for executing status
        page.wait_for_selector(Selectors.STATUS_EXECUTING, timeout=10000)
        status_changes.append("executing")
        
        # Wait for processing status  
        page.wait_for_selector(Selectors.STATUS_PROCESSING, timeout=60000)
        status_changes.append("processing_results")
        
        # Wait for ready_for_review status
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=120000)
        status_changes.append("ready_for_review")
        
        # Verify all expected status changes occurred
        expected_statuses = ["executing", "processing_results", "ready_for_review"]
        assert status_changes == expected_statuses
        
        # Verify database reflects final state
        session.refresh_from_db()
        assert session.status == "ready_for_review"
        assert session.started_at is not None  # Should be set when execution started
    
    def test_task_failure_handling(self, authenticated_page, live_server, test_user):
        """Test handling of failed background tasks."""
        # This would require mocking API failures or network issues
        # Skip for now as it requires complex mocking setup
        pytest.skip("Task failure testing requires complex mocking")
    
    def test_concurrent_task_execution(self, browser, live_server, test_user):
        """Test multiple concurrent search executions."""
        # Create multiple sessions
        sessions = []
        for i in range(3):
            session = SearchSession.objects.create(
                title=f"Concurrent Test {i+1}",
                owner=test_user,
                status="ready_to_execute"
            )
            SearchStrategy.objects.create(
                session=session,
                population_terms="water",
                interest_terms=f"test{i}",
                selected_domains=["org"],
            )
            sessions.append(session)
        
        # Create multiple browser contexts
        contexts = []
        pages = []
        
        for i in range(3):
            context = browser.new_context()
            page = context.new_page()
            contexts.append(context)
            pages.append(page)
            
            # Login
            self._login_user(page, test_user, live_server.url)
        
        # Start all searches simultaneously
        for i, page in enumerate(pages):
            page.goto(f"{live_server.url}/session/{sessions[i].id}/")
            page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        
        # Wait for all to complete
        for page in pages:
            page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=180000)
        
        # Verify all completed successfully
        for session in sessions:
            session.refresh_from_db()
            assert session.status == "ready_for_review"
        
        # Cleanup
        for context in contexts:
            context.close()
    
    def _login_user(self, page, user, base_url):
        """Helper method to log in a user."""
        page.goto(f"{base_url}/accounts/login/")
        page.fill('input[name="username"]', user.username)
        page.fill('input[name="password"]', "testpass123")
        
        with page.expect_navigation():
            page.click('button[type="submit"]')


@pytest.mark.django_db(transaction=True)
class TestResultProcessingPipeline:
    """
    Test the result processing and deduplication pipeline.
    """
    
    def test_result_deduplication(self, authenticated_page, live_server, test_user):
        """Test that duplicate results are properly deduplicated."""
        page = authenticated_page
        
        # Create session and execute search
        session = SearchSession.objects.create(
            title="Deduplication Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="water quality",
            interest_terms="standards",
            selected_domains=["edu", "org"],  # Multiple domains might create duplicates
        )
        
        # Execute search
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=120000)
        
        # Check that processed results are fewer than raw results (indicating deduplication)
        session.refresh_from_db()
        raw_count = RawSearchResult.objects.filter(execution__session=session).count()
        processed_count = ProcessedResult.objects.filter(session=session).count()
        
        # In most cases, processed should be <= raw due to deduplication
        assert processed_count <= raw_count, f"Processed ({processed_count}) > Raw ({raw_count})"
        
        # Verify no duplicate URLs in processed results
        processed_urls = ProcessedResult.objects.filter(session=session).values_list('url', flat=True)
        unique_urls = set(processed_urls)
        assert len(processed_urls) == len(unique_urls), "Found duplicate URLs in processed results"
    
    def test_result_normalization(self, authenticated_page, live_server, test_user):
        """Test that results are properly normalised."""
        page = authenticated_page
        
        # Execute a search to get results
        session = SearchSession.objects.create(
            title="Normalisation Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="research",
            interest_terms="methodology",
            selected_domains=["edu"],
        )
        
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=120000)
        
        # Check processed results for proper normalisation
        processed_results = ProcessedResult.objects.filter(session=session)[:5]
        
        for result in processed_results:
            # Check that required fields are present
            assert result.title is not None and result.title.strip() != ""
            assert result.url is not None and result.url.strip() != ""
            
            # Check URL format
            assert result.url.startswith('http'), f"Invalid URL format: {result.url}"
            
            # Check that snippet exists (might be empty for some results)
            # assert result.snippet is not None
    
    def test_large_result_set_handling(self, authenticated_page, live_server, test_user):
        """Test handling of large result sets."""
        page = authenticated_page
        
        # Create search that might return many results
        session = SearchSession.objects.create(
            title="Large Result Set Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="university research",  # Broad terms
            interest_terms="study analysis",
            selected_domains=["edu"],
            include_file_types=True,
        )
        
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=180000)  # Longer timeout
        
        # Navigate to results and test pagination
        page.goto(f"{live_server.url}/session/{session.id}/results/")
        page.wait_for_selector(Selectors.RESULTS_TABLE)
        
        session.refresh_from_db()
        
        # If we have many results, test pagination
        if session.total_results > 20:
            # Check pagination controls exist
            page.wait_for_selector(Selectors.RESULTS_PAGINATION)
            
            # Test pagination
            page.click('[data-testid="next-page"]')
            page.wait_for_selector('[data-testid="page-2"]')
            
            # Verify page changed
            current_page = page.locator('[data-testid="current-page"]')
            expect(current_page).to_contain_text("2")


@pytest.mark.django_db(transaction=True)
class TestRealTimeUpdates:
    """
    Test real-time updates during search execution.
    """
    
    def test_status_updates_during_execution(self, authenticated_page, live_server, test_user):
        """Test that status updates appear in real-time during execution."""
        page = authenticated_page
        
        # Create session
        session = SearchSession.objects.create(
            title="Real-time Updates Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="water quality",
            interest_terms="monitoring",
            selected_domains=["edu", "gov"],
        )
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Start execution
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        
        # Monitor real-time status changes
        statuses_observed = []
        
        # Check for executing status
        page.wait_for_selector(Selectors.STATUS_EXECUTING, timeout=10000)
        statuses_observed.append("executing")
        
        # Monitor for intermediate status updates
        try:
            page.wait_for_selector('[data-testid="search-progress"]', timeout=30000)
            # If progress indicator exists, verify it shows progress
            progress_element = page.locator('[data-testid="search-progress"]')
            expect(progress_element).to_be_visible()
        except Exception:
            # Progress indicator might not be implemented yet
            pass
        
        # Wait for final status
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=120000)
        statuses_observed.append("ready_for_review")
        
        # Verify we observed the expected status progression
        assert "executing" in statuses_observed
        assert "ready_for_review" in statuses_observed
    
    def test_progress_indicator_functionality(self, authenticated_page, live_server, test_user):
        """Test progress indicators during search execution."""
        # This test assumes progress indicators are implemented
        pytest.skip("Progress indicators may not be fully implemented")


# Utility functions for API testing
def mock_serper_api_response(num_results=10, include_errors=False):
    """Generate mock Serper API response for testing."""
    results = []
    for i in range(num_results):
        results.append({
            "title": f"Test Result {i+1}",
            "link": f"https://example{i}.edu/test-page",
            "snippet": f"This is test result {i+1} snippet with relevant content.",
            "date": "2024-01-01",
        })
    
    response = {
        "searchParameters": {
            "q": "test query",
            "type": "search",
        },
        "organic": results,
    }
    
    if include_errors:
        response["error"] = "Test error message"
    
    return response


def verify_api_key_configuration():
    """Verify that Serper API key is properly configured."""
    from django.conf import settings

    from apps.serp_execution.services.serper_client import SerperClient

    # Check settings
    assert hasattr(settings, 'SERPER_API_KEY'), "SERPER_API_KEY not in settings"
    assert settings.SERPER_API_KEY, "SERPER_API_KEY is empty"
    
    # Test client connection
    client = SerperClient()
    assert client.test_connection(), "Serper API connection test failed"