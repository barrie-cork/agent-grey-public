"""
UI component tests for Agent Grey using Playwright.

These tests focus on individual UI components, forms, navigation,
and user interface elements.
"""

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import expect

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchStrategy

from .conftest import Selectors, TestData

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestNavigationComponents:
    """
    Test navigation components and routing.
    """
    
    def test_navbar_navigation(self, authenticated_page, live_server):
        """Test navigation bar functionality."""
        page = authenticated_page
        base_url = live_server.url
        
        # Should be on dashboard after authentication
        page.goto(f"{base_url}/")
        page.wait_for_selector(Selectors.NAVBAR, timeout=10000)
        
        # Verify navbar elements are present
        navbar = page.locator(Selectors.NAVBAR)
        expect(navbar).to_be_visible()
        
        # Test dashboard link
        dashboard_link = page.locator(Selectors.DASHBOARD_LINK)
        if dashboard_link.count() > 0:
            dashboard_link.click()
            page.wait_for_selector(Selectors.DASHBOARD, timeout=10000)
            expect(page.locator(Selectors.DASHBOARD)).to_be_visible()
        
        # Test user menu (if present)
        user_menu = page.locator('[data-testid="user-menu"]')
        if user_menu.count() > 0:
            user_menu.click()
            page.wait_for_selector('[data-testid="user-dropdown"]', timeout=5000)
    
    def test_breadcrumb_navigation(self, authenticated_page, live_server, test_search_session):
        """Test breadcrumb navigation."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to session detail page
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Check for breadcrumbs
        breadcrumbs = page.locator('[data-testid="breadcrumbs"]')
        if breadcrumbs.count() > 0:
            expect(breadcrumbs).to_be_visible()
            
            # Test breadcrumb links
            dashboard_crumb = page.locator('[data-testid="breadcrumb-dashboard"]')
            if dashboard_crumb.count() > 0:
                dashboard_crumb.click()
                page.wait_for_selector(Selectors.DASHBOARD, timeout=10000)
    
    def test_sidebar_navigation(self, authenticated_page, live_server, test_search_session):
        """Test sidebar navigation within session pages."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Check for sidebar
        sidebar = page.locator('[data-testid="sidebar"]')
        if sidebar.count() > 0:
            expect(sidebar).to_be_visible()
            
            # Test sidebar links
            sidebar_links = page.locator('[data-testid="sidebar-link"]')
            if sidebar_links.count() > 0:
                first_link = sidebar_links.nth(0)
                first_link.click()
                # Verify navigation occurred (URL should change)
                page.wait_for_timeout(1000)  # Brief wait for navigation


@pytest.mark.django_db(transaction=True)
class TestFormComponents:
    """
    Test form components and validation.
    """
    
    def test_search_session_form_validation(self, authenticated_page, live_server):
        """Test search session creation form validation."""
        page = authenticated_page
        
        # Navigate to session creation
        page.goto(f"{live_server.url}/")
        page.wait_for_selector(Selectors.CREATE_SESSION_BUTTON)
        page.click(Selectors.CREATE_SESSION_BUTTON)
        
        # Test empty form submission
        save_button = page.locator(Selectors.SAVE_SESSION_BUTTON)
        if save_button.count() > 0:
            save_button.click()
            
            # Check for validation errors
            error_messages = page.locator('[data-testid="form-error"]')
            if error_messages.count() > 0:
                expect(error_messages.nth(0)).to_be_visible()
        
        # Test valid form submission
        page.fill(Selectors.SESSION_TITLE, TestData.SEARCH_SESSION["title"])
        page.fill(Selectors.SESSION_DESCRIPTION, TestData.SEARCH_SESSION["description"])
        
        if save_button.count() > 0:
            save_button.click()
            # Should redirect or show success message
            page.wait_for_selector('[data-testid="session-created"]', timeout=10000)
    
    def test_pic_framework_form_validation(self, authenticated_page, live_server, test_search_session):
        """Test PIC framework form validation and functionality."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to strategy definition
        page.goto(f"{live_server.url}/session/{session.id}/strategy/")
        page.wait_for_selector(Selectors.POPULATION_TERMS)
        
        # Test character counting (if implemented)
        population_field = page.locator(Selectors.POPULATION_TERMS)
        population_field.fill("a" * 500)  # Long text
        
        char_counter = page.locator('[data-testid="char-counter"]')
        if char_counter.count() > 0:
            expect(char_counter).to_be_visible()
        
        # Test term validation
        population_field.clear()
        population_field.fill("water, groundwater, aquifer")
        
        interest_field = page.locator(Selectors.INTEREST_TERMS)
        interest_field.fill("contamination, pollution")
        
        # Test domain selection
        domain_select = page.locator(Selectors.SELECTED_DOMAINS)
        if domain_select.count() > 0:
            domain_select.select_option(["edu", "org"])
        
        # Test file type checkbox
        file_type_checkbox = page.locator(Selectors.INCLUDE_FILE_TYPES)
        if file_type_checkbox.count() > 0:
            file_type_checkbox.check()
            expect(file_type_checkbox).to_be_checked()
        
        # Save form
        save_button = page.locator(Selectors.SAVE_STRATEGY_BUTTON)
        if save_button.count() > 0:
            save_button.click()
            page.wait_for_selector('[data-testid="strategy-saved"]', timeout=10000)
    
    def test_form_autosave_functionality(self, authenticated_page, live_server, test_search_session):
        """Test form autosave functionality (if implemented)."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to strategy form
        page.goto(f"{live_server.url}/session/{session.id}/strategy/")
        
        # Fill in some data
        page.fill(Selectors.POPULATION_TERMS, "test autosave")
        
        # Wait for autosave indication
        autosave_indicator = page.locator('[data-testid="autosave-indicator"]')
        if autosave_indicator.count() > 0:
            page.wait_for_selector('[data-testid="autosave-saved"]', timeout=10000)
            expect(autosave_indicator).to_contain_text("Saved")
    
    def test_form_field_help_text(self, authenticated_page, live_server, test_search_session):
        """Test form field help text and tooltips."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to strategy form
        page.goto(f"{live_server.url}/session/{session.id}/strategy/")
        
        # Look for help icons or tooltips
        help_icons = page.locator('[data-testid="help-icon"]')
        if help_icons.count() > 0:
            # Click first help icon
            help_icons.nth(0).click()
            
            # Check for tooltip or help text
            tooltip = page.locator('[data-testid="tooltip"]')
            expect(tooltip).to_be_visible()
            
            # Click outside to close tooltip
            page.click("body")
            expect(tooltip).not_to_be_visible()


@pytest.mark.django_db(transaction=True)
class TestStatusIndicators:
    """
    Test status indicators and progress components.
    """
    
    def test_status_badge_display(self, authenticated_page, live_server, test_search_session):
        """Test status badge display and styling."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Check status badge
        status_badge = page.locator(Selectors.STATUS_BADGE)
        expect(status_badge).to_be_visible()
        
        # Verify badge contains expected text
        expect(status_badge).to_contain_text("Draft")
        
        # Check badge styling (if CSS classes are used)
        badge_classes = status_badge.get_attribute("class")
        if badge_classes:
            assert "badge" in badge_classes or "status" in badge_classes
    
    def test_progress_indicators(self, authenticated_page, live_server, test_user):
        """Test progress indicators during workflow transitions."""
        page = authenticated_page
        
        # Create session in executing state to test progress
        session = SearchSession.objects.create(
            title="Progress Test Session",
            owner=test_user,
            status="executing"
        )
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Look for progress indicators
        progress_bar = page.locator('[data-testid="progress-bar"]')
        if progress_bar.count() > 0:
            expect(progress_bar).to_be_visible()
        
        progress_spinner = page.locator('[data-testid="progress-spinner"]')
        if progress_spinner.count() > 0:
            expect(progress_spinner).to_be_visible()
        
        progress_text = page.locator('[data-testid="progress-text"]')
        if progress_text.count() > 0:
            expect(progress_text).to_be_visible()
            expect(progress_text).to_contain_text("Executing")
    
    def test_workflow_stepper_component(self, authenticated_page, live_server, test_search_session):
        """Test workflow stepper/progress component."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Check for workflow stepper
        stepper = page.locator('[data-testid="workflow-stepper"]')
        if stepper.count() > 0:
            expect(stepper).to_be_visible()
            
            # Check for step indicators
            steps = page.locator('[data-testid="workflow-step"]')
            expect(steps).to_have_count_greater_than(0)
            
            # Check current step highlighting
            current_step = page.locator('[data-testid="current-step"]')
            expect(current_step).to_be_visible()


@pytest.mark.django_db(transaction=True)
class TestDataDisplayComponents:
    """
    Test data display components like tables, cards, and lists.
    """
    
    def test_session_list_display(self, authenticated_page, live_server, test_user):
        """Test session list display on dashboard."""
        page = authenticated_page
        
        # Create multiple sessions
        for i in range(3):
            SearchSession.objects.create(
                title=f"Test Session {i+1}",
                description=f"Test description {i+1}",
                owner=test_user,
                status="draft"
            )
        
        # Navigate to dashboard
        page.goto(f"{live_server.url}/")
        page.wait_for_selector(Selectors.SESSION_LIST)
        
        # Check session list
        session_list = page.locator(Selectors.SESSION_LIST)
        expect(session_list).to_be_visible()
        
        # Check session cards/items
        session_items = page.locator('[data-testid="session-item"]')
        expect(session_items).to_have_count_greater_than_or_equal_to(3)
        
        # Test session item content
        first_session = session_items.nth(0)
        expect(first_session).to_contain_text("Test Session")
    
    def test_results_table_display(self, authenticated_page, live_server, test_user):
        """Test results table display and functionality."""
        page = authenticated_page
        
        # Create session with results
        session = SearchSession.objects.create(
            title="Results Display Test",
            owner=test_user,
            status="ready_for_review",
            total_results=5
        )
        
        # Create some mock processed results
        for i in range(5):
            ProcessedResult.objects.create(
                session=session,
                title=f"Test Result {i+1}",
                url=f"https://example{i}.edu/test",
                snippet=f"This is test result {i+1} snippet.",
                relevance_score=0.8
            )
        
        # Navigate to results page
        page.goto(f"{live_server.url}/session/{session.id}/results/")
        page.wait_for_selector(Selectors.RESULTS_TABLE)
        
        # Check table structure
        results_table = page.locator(Selectors.RESULTS_TABLE)
        expect(results_table).to_be_visible()
        
        # Check table headers
        headers = page.locator('[data-testid="table-header"]')
        if headers.count() > 0:
            expect(headers).to_have_count_greater_than(2)  # At least title, URL columns
        
        # Check result rows
        result_rows = page.locator(Selectors.RESULT_ROW)
        expect(result_rows).to_have_count(5)
        
        # Test row content
        first_row = result_rows.nth(0)
        expect(first_row).to_contain_text("Test Result 1")
        expect(first_row).to_contain_text("example0.edu")
    
    def test_results_table_sorting(self, authenticated_page, live_server, test_user):
        """Test results table sorting functionality."""
        page = authenticated_page
        
        # Create session with results (using existing session if available)
        session = SearchSession.objects.create(
            title="Sorting Test",
            owner=test_user,
            status="ready_for_review"
        )
        
        # Navigate to results
        page.goto(f"{live_server.url}/session/{session.id}/results/")
        
        # Look for sortable headers
        sortable_headers = page.locator('[data-testid="sortable-header"]')
        if sortable_headers.count() > 0:
            # Click first sortable header
            sortable_headers.nth(0).click()
            
            # Wait for sort to apply
            page.wait_for_timeout(1000)
            
            # Check for sort indicator
            sort_indicator = page.locator('[data-testid="sort-indicator"]')
            expect(sort_indicator).to_be_visible()
    
    def test_query_preview_display(self, authenticated_page, live_server, test_search_session):
        """Test query preview component display."""
        page = authenticated_page
        session = test_search_session
        
        # Create strategy for the session
        _strategy = SearchStrategy.objects.create(
            session=session,
            population_terms="water, groundwater",
            interest_terms="contamination, pollution",
            context_terms="agriculture, industrial",
            include_file_types=True,
            selected_domains=["edu", "org"]
        )
        
        # Navigate to strategy page
        page.goto(f"{live_server.url}/session/{session.id}/strategy/")
        
        # Look for query preview
        query_preview = page.locator('[data-testid="query-preview"]')
        if query_preview.count() > 0:
            expect(query_preview).to_be_visible()
            expect(query_preview).to_contain_text("water")
            expect(query_preview).to_contain_text("contamination")


@pytest.mark.django_db(transaction=True)
class TestInteractiveComponents:
    """
    Test interactive components like buttons, modals, and dropdowns.
    """
    
    def test_modal_dialogs(self, authenticated_page, live_server, test_search_session):
        """Test modal dialog functionality."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Look for buttons that trigger modals
        modal_trigger = page.locator('[data-testid="open-modal"]')
        if modal_trigger.count() > 0:
            modal_trigger.click()
            
            # Check modal appears
            modal = page.locator('[data-testid="modal"]')
            expect(modal).to_be_visible()
            
            # Test modal close
            close_button = page.locator('[data-testid="modal-close"]')
            if close_button.count() > 0:
                close_button.click()
                expect(modal).not_to_be_visible()
            else:
                # Try closing with escape key
                page.keyboard.press("Escape")
                expect(modal).not_to_be_visible()
    
    def test_dropdown_menus(self, authenticated_page, live_server):
        """Test dropdown menu functionality."""
        page = authenticated_page
        
        # Navigate to page with dropdowns
        page.goto(f"{live_server.url}/")
        
        # Look for dropdown triggers
        dropdown_trigger = page.locator('[data-testid="dropdown-trigger"]')
        if dropdown_trigger.count() > 0:
            dropdown_trigger.click()
            
            # Check dropdown opens
            dropdown_menu = page.locator('[data-testid="dropdown-menu"]')
            expect(dropdown_menu).to_be_visible()
            
            # Test dropdown item selection
            dropdown_items = page.locator('[data-testid="dropdown-item"]')
            if dropdown_items.count() > 0:
                dropdown_items.nth(0).click()
                # Dropdown should close after selection
                expect(dropdown_menu).not_to_be_visible()
    
    def test_button_states_and_loading(self, authenticated_page, live_server, test_user):
        """Test button states, loading, and disabled states."""
        page = authenticated_page
        
        # Create session ready for execution to test button states
        session = SearchSession.objects.create(
            title="Button States Test",
            owner=test_user,
            status="ready_to_execute"
        )
        
        SearchStrategy.objects.create(
            session=session,
            population_terms="test",
            interest_terms="button",
            selected_domains=["edu"]
        )
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Test execute button
        execute_button = page.locator(Selectors.EXECUTE_SEARCH_BUTTON)
        if execute_button.count() > 0:
            # Button should be enabled
            expect(execute_button).not_to_be_disabled()
            
            # Click button and check for loading state
            execute_button.click()
            
            # Look for loading indicator
            loading_indicator = page.locator('[data-testid="loading"]')
            if loading_indicator.count() > 0:
                expect(loading_indicator).to_be_visible()
            
            # Button might become disabled during execution
            page.wait_for_timeout(2000)  # Brief wait
            if execute_button.count() > 0:
                # Button might be disabled or show different text
                button_text = execute_button.inner_text()
                assert button_text in ["Executing...", "Execute Search", "Running..."]
    
    def test_tooltip_functionality(self, authenticated_page, live_server, test_search_session):
        """Test tooltip functionality on interactive elements."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to page with tooltips
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Look for elements with tooltips
        tooltip_triggers = page.locator('[data-testid="has-tooltip"]')
        if tooltip_triggers.count() > 0:
            # Hover over first element
            tooltip_triggers.nth(0).hover()
            
            # Check tooltip appears
            tooltip = page.locator('[data-testid="tooltip"]')
            expect(tooltip).to_be_visible()
            
            # Move mouse away
            page.mouse.move(0, 0)
            page.wait_for_timeout(500)  # Wait for tooltip to disappear
            expect(tooltip).not_to_be_visible()


@pytest.mark.django_db(transaction=True)
class TestResponsiveDesign:
    """
    Test responsive design and mobile compatibility.
    """
    
    def test_mobile_viewport_layout(self, browser, live_server, test_user):
        """Test layout on mobile viewport."""
        # Create mobile context
        context = browser.new_context(
            viewport={"width": 375, "height": 667},  # iPhone dimensions
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"
        )
        page = context.new_page()
        
        # Login
        self._login_user(page, test_user, live_server.url)
        
        # Navigate to dashboard
        page.goto(f"{live_server.url}/")
        page.wait_for_selector(Selectors.DASHBOARD)
        
        # Check mobile navigation
        mobile_menu = page.locator('[data-testid="mobile-menu"]')
        if mobile_menu.count() > 0:
            expect(mobile_menu).to_be_visible()
        
        # Check responsive elements
        session_list = page.locator(Selectors.SESSION_LIST)
        expect(session_list).to_be_visible()
        
        context.close()
    
    def test_tablet_viewport_layout(self, browser, live_server, test_user):
        """Test layout on tablet viewport."""
        # Create tablet context
        context = browser.new_context(
            viewport={"width": 768, "height": 1024},  # iPad dimensions
        )
        page = context.new_page()
        
        # Login
        self._login_user(page, test_user, live_server.url)
        
        # Navigate to dashboard
        page.goto(f"{live_server.url}/")
        page.wait_for_selector(Selectors.DASHBOARD)
        
        # Verify layout works on tablet
        expect(page.locator(Selectors.DASHBOARD)).to_be_visible()
        
        context.close()
    
    def _login_user(self, page, user, base_url):
        """Helper method to log in a user."""
        page.goto(f"{base_url}/accounts/login/")
        page.fill('input[name="username"]', user.username)
        page.fill('input[name="password"]', "testpass123")
        
        with page.expect_navigation():
            page.click('button[type="submit"]')


@pytest.mark.django_db(transaction=True)
class TestAccessibilityComponents:
    """
    Test accessibility features and components.
    """
    
    def test_keyboard_navigation(self, authenticated_page, live_server):
        """Test keyboard navigation through the interface."""
        page = authenticated_page
        
        # Navigate to dashboard
        page.goto(f"{live_server.url}/")
        page.wait_for_selector(Selectors.DASHBOARD)
        
        # Test tab navigation
        page.keyboard.press("Tab")
        
        # Check focus is visible
        focused_element = page.evaluate("document.activeElement")
        assert focused_element is not None
        
        # Continue tabbing through interface
        for _ in range(5):
            page.keyboard.press("Tab")
            page.wait_for_timeout(100)  # Brief pause
    
    def test_aria_labels_and_roles(self, authenticated_page, live_server, test_search_session):
        """Test ARIA labels and roles for screen readers."""
        page = authenticated_page
        session = test_search_session
        
        # Navigate to session
        page.goto(f"{live_server.url}/session/{session.id}/")
        
        # Check for ARIA labels
        buttons = page.locator("button")
        for i in range(min(3, buttons.count())):
            button = buttons.nth(i)
            aria_label = button.get_attribute("aria-label")
            # Button should have either aria-label or visible text
            if not aria_label:
                button_text = button.inner_text()
                assert button_text.strip() != "", "Button has no accessible label"
        
        # Check for role attributes
        main_content = page.locator('[role="main"]')
        if main_content.count() > 0:
            expect(main_content).to_be_visible()
    
    def test_color_contrast_and_visibility(self, authenticated_page, live_server):
        """Test basic visibility and contrast (basic checks)."""
        page = authenticated_page
        
        # Navigate to dashboard
        page.goto(f"{live_server.url}/")
        page.wait_for_selector(Selectors.DASHBOARD)
        
        # Check that key elements are visible
        expect(page.locator(Selectors.DASHBOARD)).to_be_visible()
        
        # Check status badges are visible
        status_badges = page.locator('[data-testid="status-badge"]')
        for i in range(min(3, status_badges.count())):
            expect(status_badges.nth(i)).to_be_visible()


# Helper functions for UI testing
def take_screenshot_on_failure(page, test_name):
    """Take a screenshot when a test fails."""
    try:
        page.screenshot(path=f"tests/playwright/screenshots/{test_name}-failure.png")
    except Exception:
        pass  # Screenshot failed, but don't fail the test


def wait_for_element_visible(page, selector, timeout=30000):
    """Wait for element to be visible with custom timeout."""
    return page.wait_for_selector(selector, timeout=timeout, state="visible")


def verify_element_accessibility(page, element):
    """Verify basic accessibility of an element."""
    # Check if element has accessible name (aria-label, text content, etc.)
    aria_label = element.get_attribute("aria-label")
    text_content = element.inner_text()
    
    return aria_label is not None or (text_content and text_content.strip() != "")