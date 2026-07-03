"""
Comprehensive end-to-end tests for the Agent Grey 9-state search workflow.

Tests the complete workflow from session creation through report generation,
including all state transitions and user interactions.
"""


import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import expect

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchStrategy

from .conftest import Selectors, TestData

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestSearchWorkflowE2E:
    """
    End-to-end tests for the complete 9-state search workflow.
    
    Tests all state transitions:
    draft → defining_search → ready_to_execute → executing → 
    processing_results → ready_for_review → under_review → completed → archived
    """
    
    def test_complete_search_workflow(self, authenticated_page, live_server, test_user):
        """
        Test the complete workflow from session creation to completion.
        
        This is the main integration test that verifies all components work together.
        """
        page = authenticated_page
        base_url = live_server.url
        
        # Step 1: Navigate to dashboard and create new session (draft state)
        page.goto(f"{base_url}/")
        page.wait_for_selector(Selectors.DASHBOARD, timeout=10000)
        
        # Create new search session
        page.click(Selectors.CREATE_SESSION_BUTTON)
        page.wait_for_selector(Selectors.SESSION_TITLE)
        
        # Fill in session details
        page.fill(Selectors.SESSION_TITLE, TestData.SEARCH_SESSION["title"])
        page.fill(Selectors.SESSION_DESCRIPTION, TestData.SEARCH_SESSION["description"])
        
        # Save session
        page.click(Selectors.SAVE_SESSION_BUTTON)
        page.wait_for_selector(Selectors.STATUS_DRAFT, timeout=10000)
        
        # Verify session is in draft state
        status_element = page.locator(Selectors.STATUS_BADGE)
        expect(status_element).to_contain_text("Draft")
        
        # Get session ID from URL
        current_url = page.url
        session_id = current_url.split("/")[-2]  # Extract UUID from URL
        
        # Step 2: Define search strategy (draft → defining_search)
        page.click('[data-testid="define-search"]')
        page.wait_for_selector(Selectors.POPULATION_TERMS)
        
        # Fill in PIC framework terms
        page.fill(Selectors.POPULATION_TERMS, TestData.PIC_STRATEGY["population_terms"])
        page.fill(Selectors.INTEREST_TERMS, TestData.PIC_STRATEGY["interest_terms"])
        page.fill(Selectors.CONTEXT_TERMS, TestData.PIC_STRATEGY["context_terms"])
        
        # Configure domains
        page.check(Selectors.INCLUDE_FILE_TYPES)
        
        # Select domains (multi-select)
        for domain in TestData.PIC_STRATEGY["selected_domains"]:
            page.locator(Selectors.SELECTED_DOMAINS).select_option(domain)
        
        # Add exclude domains
        page.fill(Selectors.EXCLUDE_DOMAINS, TestData.PIC_STRATEGY["exclude_domains"])
        
        # Save strategy
        page.click(Selectors.SAVE_STRATEGY_BUTTON)
        page.wait_for_selector(Selectors.STATUS_DEFINING, timeout=10000)
        
        # Verify status changed to defining_search
        expect(page.locator(Selectors.STATUS_BADGE)).to_contain_text("Defining Search")
        
        # Step 3: Validate and prepare for execution (defining_search → ready_to_execute)
        page.click('[data-testid="validate-strategy"]')
        page.wait_for_selector('[data-testid="validation-complete"]', timeout=10000)
        page.wait_for_selector(Selectors.STATUS_READY, timeout=10000)
        
        # Verify status changed to ready_to_execute
        expect(page.locator(Selectors.STATUS_BADGE)).to_contain_text("Ready to Execute")
        
        # Step 4: Execute search (ready_to_execute → executing → processing_results → ready_for_review)
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        page.wait_for_selector(Selectors.STATUS_EXECUTING, timeout=10000)
        
        # Wait for automatic progression through executing → processing_results → ready_for_review
        # This involves actual API calls, so we need to wait longer
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=120000)  # 2 minutes max
        
        # Verify final status is ready_for_review
        expect(page.locator(Selectors.STATUS_BADGE)).to_contain_text("Ready for Review")
        
        # Verify results are available
        page.wait_for_selector(Selectors.RESULTS_TABLE, timeout=10000)
        
        # Check that we have results (should be > 0 based on successful session a1cf07b6)
        result_rows = page.locator(Selectors.RESULT_ROW)
        expect(result_rows).to_have_count_greater_than(0)
        
        # Step 5: Review results (ready_for_review → under_review)
        page.click('[data-testid="start-review"]')
        page.wait_for_selector(Selectors.STATUS_UNDER_REVIEW, timeout=10000)
        
        # Verify status changed to under_review
        expect(page.locator(Selectors.STATUS_BADGE)).to_contain_text("Under Review")
        
        # Review some results - include and exclude
        result_rows = page.locator(Selectors.RESULT_ROW)
        first_result = result_rows.nth(0)
        second_result = result_rows.nth(1)
        
        # Include first result
        first_result.locator(Selectors.INCLUDE_BUTTON).click()
        page.wait_for_selector('[data-testid="result-included"]', timeout=5000)
        
        # Exclude second result
        second_result.locator(Selectors.EXCLUDE_BUTTON).click()
        page.wait_for_selector('[data-testid="result-excluded"]', timeout=5000)
        
        # Step 6: Complete review (under_review → completed)
        page.click(Selectors.MARK_COMPLETED_BUTTON)

        # Handle confirmation dialog if present
        page.on("dialog", lambda dialog: dialog.accept())

        page.wait_for_selector(Selectors.STATUS_COMPLETED, timeout=10000)

        # Verify status changed to completed
        expect(page.locator(Selectors.STATUS_BADGE)).to_contain_text("Completed")

        # Verify completed_at timestamp is set
        session = SearchSession.objects.get(id=session_id)
        assert session.status == "completed"
        assert session.completed_at is not None, "completed_at timestamp should be set"

        # Step 7: Generate and download report
        page.click(Selectors.GENERATE_REPORT_BUTTON)
        page.wait_for_selector(Selectors.DOWNLOAD_REPORT_BUTTON, timeout=30000)

        # Verify report is available
        expect(page.locator(Selectors.DOWNLOAD_REPORT_BUTTON)).to_be_visible()

        # Step 8: Archive session (completed → archived)
        # Find and click archive button
        page.wait_for_selector(Selectors.ARCHIVE_SESSION_BUTTON, timeout=10000)
        page.click(Selectors.ARCHIVE_SESSION_BUTTON)

        # Handle confirmation dialog
        page.on("dialog", lambda dialog: dialog.accept())

        # Wait for redirect to dashboard after archival
        page.wait_for_url("**/dashboard/**", timeout=10000)

        # Verify final database state
        session.refresh_from_db()
        assert session.status == "archived", f"Expected archived status, got {session.status}"
        assert session.total_results > 0
        assert session.reviewed_results >= 2  # We reviewed at least 2 results

        # Verify archived session is not visible in main dashboard
        page.goto(f"{base_url}/")
        page.wait_for_selector(Selectors.DASHBOARD, timeout=10000)

        # Session should not appear in active sessions list
        # (This assumes active sessions list doesn't show archived sessions)
        session_links = page.locator(f'a[href*="/sessions/{session_id}/"]')
        expect(session_links).to_have_count(0)
    
    def test_draft_to_defining_search_transition(self, authenticated_page, live_server, test_user):
        """Test the transition from draft to defining_search state."""
        page = authenticated_page
        
        # Create session in draft state
        session = SearchSession.objects.create(
            title="Draft Test Session",
            description="Testing draft to defining transition",
            owner=test_user,
            status="draft"
        )
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.wait_for_selector(Selectors.STATUS_DRAFT)
        
        # Start defining search
        page.click('[data-testid="define-search"]')
        page.wait_for_selector(Selectors.STATUS_DEFINING)
        
        # Verify status change
        expect(page.locator(Selectors.STATUS_BADGE)).to_contain_text("Defining Search")
        
        # Verify database state
        session.refresh_from_db()
        assert session.status == "defining_search"
    
    def test_pic_framework_validation(self, authenticated_page, live_server, test_search_session):
        """Test PIC framework validation and query generation."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to strategy definition
        page.goto(f"{live_server.url}/session/{session.id}/strategy/")
        
        # Test empty form validation
        page.click(Selectors.SAVE_STRATEGY_BUTTON)
        page.wait_for_selector('[data-testid="validation-error"]', timeout=5000)
        
        # Fill in minimal required fields
        page.fill(Selectors.POPULATION_TERMS, "water")
        page.fill(Selectors.INTEREST_TERMS, "quality")
        
        # Save and verify success
        page.click(Selectors.SAVE_STRATEGY_BUTTON)
        page.wait_for_selector('[data-testid="strategy-saved"]', timeout=5000)
        
        # Verify query preview is generated
        page.wait_for_selector('[data-testid="query-preview"]', timeout=5000)
        query_preview = page.locator('[data-testid="query-preview"]')
        expect(query_preview).to_contain_text("water")
        expect(query_preview).to_contain_text("quality")
    
    def test_search_execution_with_real_api(self, authenticated_page, live_server, test_user):
        """
        Test search execution with real API call.
        Uses the known working search terms 'water AND ait'.
        """
        page = authenticated_page
        
        # Create session with strategy that we know works
        session = SearchSession.objects.create(
            title="API Test Session",
            description="Testing real API integration",
            owner=test_user,
            status="defining_search"
        )
        
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="water",
            interest_terms="ait",  # This combination is known to work
            context_terms="",
            include_file_types=True,
            selected_domains=["edu", "org"],
        )
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Validate strategy
        page.click('[data-testid="validate-strategy"]')
        page.wait_for_selector(Selectors.STATUS_READY, timeout=10000)
        
        # Execute search
        page.click(Selectors.EXECUTE_SEARCH_BUTTON)
        page.wait_for_selector(Selectors.STATUS_EXECUTING, timeout=10000)
        
        # Wait for completion (this makes real API calls)
        page.wait_for_selector(Selectors.STATUS_REVIEW_READY, timeout=180000)  # 3 minutes max
        
        # Verify we got results
        page.wait_for_selector(Selectors.RESULTS_TABLE, timeout=10000)
        result_rows = page.locator(Selectors.RESULT_ROW)
        expect(result_rows).to_have_count_greater_than(0)
        
        # Verify database state
        session.refresh_from_db()
        assert session.status == "ready_for_review"
        assert session.total_results > 0
    
    def test_results_pagination_and_filtering(self, authenticated_page, live_server, test_user):
        """Test results pagination and filtering functionality."""
        page = authenticated_page
        
        # Create a session with many results (using the working session as template)
        session = SearchSession.objects.create(
            title="Pagination Test Session",
            owner=test_user,
            status="ready_for_review",
            total_results=50  # Simulate having many results
        )
        
        # Navigate to results page
        page.goto(f"{live_server.url}/session/{session.id}/results/")
        page.wait_for_selector(Selectors.RESULTS_TABLE)
        
        # Test pagination (if more than 20 results)
        if session.total_results > 20:
            page.wait_for_selector(Selectors.RESULTS_PAGINATION)
            
            # Click next page
            page.click('[data-testid="next-page"]')
            page.wait_for_selector('[data-testid="page-2"]')
            
            # Verify page change
            expect(page.locator('[data-testid="current-page"]')).to_contain_text("2")
        
        # Test search/filtering
        search_input = page.locator('[data-testid="results-search"]')
        if search_input.count() > 0:
            search_input.fill("water")
            page.keyboard.press("Enter")
            page.wait_for_selector('[data-testid="filtered-results"]', timeout=5000)
    
    def test_error_handling_invalid_api_key(self, authenticated_page, live_server, test_user, monkeypatch):
        """Test error handling when API key is invalid."""
        # This test would require mocking the API key to be invalid
        # Skip for now as it requires environment manipulation
        pytest.skip("API key error testing requires environment manipulation")
    
    def test_session_persistence_across_browser_sessions(self, browser, live_server, test_user):
        """Test that session state persists across browser restarts."""
        # Create session
        session = SearchSession.objects.create(
            title="Persistence Test",
            owner=test_user,
            status="defining_search"
        )
        
        # First browser session
        context1 = browser.new_context()
        page1 = context1.new_page()
        
        # Login and verify session exists
        self._login_user(page1, test_user, live_server.url)
        page1.goto(f"{live_server.url}/session/{session.id}/")
        page1.wait_for_selector(Selectors.STATUS_DEFINING)
        
        # Close browser session
        context1.close()
        
        # Second browser session
        context2 = browser.new_context()
        page2 = context2.new_page()
        
        # Login again and verify session still exists
        self._login_user(page2, test_user, live_server.url)
        page2.goto(f"{live_server.url}/session/{session.id}/")
        page2.wait_for_selector(Selectors.STATUS_DEFINING)
        
        # Verify status is still correct
        expect(page2.locator(Selectors.STATUS_BADGE)).to_contain_text("Defining Search")
        
        context2.close()
    
    def _login_user(self, page, user, base_url):
        """Helper method to log in a user."""
        page.goto(f"{base_url}/accounts/login/")
        page.fill('input[name="username"]', user.username)
        page.fill('input[name="password"]', "testpass123")
        
        with page.expect_navigation():
            page.click('button[type="submit"]')
        
        page.wait_for_selector(Selectors.DASHBOARD, timeout=10000)


@pytest.mark.django_db(transaction=True)
class TestSearchWorkflowStateTransitions:
    """
    Test specific state transitions and validation rules.
    """
    
    def test_invalid_state_transitions(self, authenticated_page, live_server, test_user):
        """Test that invalid state transitions are prevented."""
        page = authenticated_page
        
        # Create session in completed state
        session = SearchSession.objects.create(
            title="Invalid Transition Test",
            owner=test_user,
            status="completed"
        )
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Try to go back to defining_search (should be prevented)
        define_button = page.locator('[data-testid="define-search"]')
        if define_button.count() > 0:
            define_button.click()
            page.wait_for_selector('[data-testid="transition-error"]', timeout=5000)
    
    def test_automatic_status_updates(self, authenticated_page, live_server, test_user):
        """Test that status updates are reflected in the UI automatically."""
        page = authenticated_page
        
        # Create session in executing state
        session = SearchSession.objects.create(
            title="Auto Update Test",
            owner=test_user,
            status="executing"
        )
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        page.wait_for_selector(Selectors.STATUS_EXECUTING)
        
        # Simulate status change in database (as would happen via Celery)
        session.status = "processing_results"
        session.save()
        
        # Page should update automatically (via SSE or polling)
        page.wait_for_selector(Selectors.STATUS_PROCESSING, timeout=30000)
        expect(page.locator(Selectors.STATUS_BADGE)).to_contain_text("Processing Results")


@pytest.mark.django_db(transaction=True) 
class TestSearchWorkflowAccessControl:
    """
    Test access control and permission handling.
    """
    
    def test_unauthorized_access_to_session(self, browser, live_server, test_user):
        """Test that users cannot access sessions they don't own."""
        # Create another user
        from apps.core.tests.utils import create_test_user
        other_user = create_test_user(username_prefix="other")
        
        # Create session owned by other user
        session = SearchSession.objects.create(
            title="Private Session",
            owner=other_user,
            status="draft"
        )
        
        # Login as test_user
        context = browser.new_context()
        page = context.new_page()
        
        page.goto(f"{live_server.url}/accounts/login/")
        page.fill('input[name="username"]', test_user.username)
        page.fill('input[name="password"]', "testpass123")
        
        with page.expect_navigation():
            page.click('button[type="submit"]')
        
        # Try to access other user's session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Should be redirected or get 403/404 error
        page.wait_for_selector('[data-testid="access-denied"]', timeout=10000)
        
        context.close()
    
    def test_anonymous_user_redirect(self, browser, live_server, test_search_session):
        """Test that anonymous users are redirected to login."""
        context = browser.new_context()
        page = context.new_page()
        
        # Try to access session without authentication
        page.goto(f"{live_server.url}/session/{test_search_session.id}/")
        
        # Should be redirected to login page
        page.wait_for_url(f"{live_server.url}/accounts/login/*", timeout=10000)
        
        context.close()


@pytest.mark.django_db(transaction=True)
class TestSearchWorkflowPerformance:
    """
    Test performance aspects of the search workflow.
    """
    
    def test_large_results_handling(self, authenticated_page, live_server, test_user):
        """Test handling of large result sets."""
        pytest.skip("Performance test - implement when needed")
    
    def test_concurrent_users(self, browser, live_server):
        """Test multiple concurrent users performing searches."""
        pytest.skip("Concurrency test - implement when needed")


# Utility functions for complex test scenarios
def create_test_session_with_results(user, title="Test Session", num_results=10):
    """Helper function to create a session with mock results."""
    session = SearchSession.objects.create(
        title=title,
        owner=user,
        status="ready_for_review",
        total_results=num_results
    )
    return session


def wait_for_background_tasks(page, timeout=60):
    """Wait for background Celery tasks to complete."""
    # This would monitor the task status via API or database
    # Implementation depends on how task status is exposed
    pass