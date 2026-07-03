"""
Playwright test configuration and fixtures for feedback system testing.
"""

import os
import sys

import django
import pytest
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from playwright.sync_api import Page, expect

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grey_lit_project.settings.test')
django.setup()

from apps.core.tests.utils import create_test_user
from apps.feedback.models import UserFeedback

User = get_user_model()

# Standard test password used by create_test_user
TEST_PASSWORD = 'testpass123'


class PlaywrightTestCase(TransactionTestCase):
    """
    Base test case for Playwright tests with Django integration.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.live_server_url = 'http://localhost:8000'

    def setUp(self):
        super().setUp()
        # Clear any existing feedback
        UserFeedback.objects.all().delete()

        # Create test users
        self.test_user = create_test_user()
        self.staff_user = create_test_user(username_prefix="staff", is_staff=True)


@pytest.fixture
def django_setup():
    """Setup Django for Playwright tests."""
    return PlaywrightTestCase()


@pytest.fixture
def test_user():
    """Create a test user."""
    return create_test_user()


@pytest.fixture
def staff_user():
    """Create a staff user."""
    return create_test_user(username_prefix="staff", is_staff=True)


@pytest.fixture
def authenticated_page(page: Page, test_user):
    """Create a page with authenticated user session."""
    # Login the user
    page.goto('http://localhost:8000/accounts/login/')
    page.fill('#id_username', test_user.username)
    page.fill('#id_password', TEST_PASSWORD)
    page.click('button[type="submit"]')

    # Wait for redirect after login
    page.wait_for_url('**/dashboard/**', timeout=5000)
    return page


@pytest.fixture
def staff_page(page: Page, staff_user):
    """Create a page with staff user session."""
    # Login the staff user
    page.goto('http://localhost:8000/accounts/login/')
    page.fill('#id_username', staff_user.username)
    page.fill('#id_password', TEST_PASSWORD)
    page.click('button[type="submit"]')

    # Wait for redirect after login
    page.wait_for_url('**/dashboard/**', timeout=5000)
    return page


def wait_for_feedback_button(page: Page):
    """Helper function to wait for feedback button to appear."""
    page.wait_for_selector('#feedbackBtn', state='visible', timeout=10000)


def open_feedback_modal(page: Page):
    """Helper function to open the feedback modal."""
    wait_for_feedback_button(page)
    page.click('#feedbackBtn')
    page.wait_for_selector('#feedbackModal', state='visible', timeout=5000)


def fill_feedback_form(page: Page, feedback_type='bug', message='Test feedback message that is long enough to pass validation requirements.', **kwargs):
    """Helper function to fill the feedback form."""
    # Fill required fields
    page.select_option('#feedbackType', feedback_type)
    page.fill('#feedbackMessage', message)

    # Fill optional fields
    if 'subject' in kwargs:
        page.fill('#feedbackSubject', kwargs['subject'])

    if 'rating' in kwargs:
        page.click(f'input[name="rating"][value="{kwargs["rating"]}"]')

    if 'email' in kwargs:
        page.fill('#feedbackEmail', kwargs['email'])


def submit_feedback_form(page: Page):
    """Helper function to submit the feedback form."""
    page.click('#submitFeedbackBtn')


def expect_success_message(page: Page):
    """Helper function to check for success message."""
    page.wait_for_selector('.alert-success', state='visible', timeout=10000)
    expect(page.locator('.alert-success')).to_contain_text('Thank you')


def expect_error_message(page: Page, error_text=None):
    """Helper function to check for error message."""
    page.wait_for_selector('.alert-danger', state='visible', timeout=5000)
    if error_text:
        expect(page.locator('.alert-danger')).to_contain_text(error_text)


@pytest.fixture
def feedback_helpers():
    """Provide helper functions for feedback testing."""
    return {
        'wait_for_feedback_button': wait_for_feedback_button,
        'open_feedback_modal': open_feedback_modal,
        'fill_feedback_form': fill_feedback_form,
        'submit_feedback_form': submit_feedback_form,
        'expect_success_message': expect_success_message,
        'expect_error_message': expect_error_message,
    }


# Test fixtures for search workflow
@pytest.fixture
def test_search_session(test_user):
    """Create a test search session."""
    from apps.review_manager.models import SearchSession
    return SearchSession.objects.create(
        title="Test Search Session",
        description="A test session for E2E testing",
        owner=test_user,
        status="draft"
    )


class Selectors:
    """CSS selectors for workflow testing."""

    # Dashboard
    DASHBOARD = '[data-testid="dashboard"]'
    CREATE_SESSION_BUTTON = '[data-testid="create-session"]'
    SESSION_LIST = '[data-testid="session-list"]'

    # Session form
    SESSION_TITLE = '#id_title'
    SESSION_DESCRIPTION = '#id_description'
    SAVE_SESSION_BUTTON = '[data-testid="save-session"]'

    # Status badges
    STATUS_BADGE = '[data-testid="session-status-badge"]'
    STATUS_DRAFT = '[data-testid="status-draft"]'
    STATUS_DEFINING = '[data-testid="status-defining"]'
    STATUS_READY = '[data-testid="status-ready"]'
    STATUS_EXECUTING = '[data-testid="status-executing"]'
    STATUS_PROCESSING = '[data-testid="status-processing"]'
    STATUS_REVIEW_READY = '[data-testid="status-ready-for-review"]'
    STATUS_UNDER_REVIEW = '[data-testid="status-under-review"]'
    STATUS_COMPLETED = '[data-testid="status-completed"]'
    STATUS_ARCHIVED = '[data-testid="status-archived"]'

    # Search strategy
    POPULATION_TERMS = '#id_population_terms'
    INTEREST_TERMS = '#id_interest_terms'
    CONTEXT_TERMS = '#id_context_terms'
    INCLUDE_FILE_TYPES = '#id_include_file_types'
    SELECTED_DOMAINS = '#id_selected_domains'
    EXCLUDE_DOMAINS = '#id_exclude_domains'
    SAVE_STRATEGY_BUTTON = '[data-testid="save-strategy"]'

    # Search execution
    EXECUTE_SEARCH_BUTTON = '[data-testid="execute-search"]'

    # Results
    RESULTS_TABLE = '[data-testid="results-table"]'
    RESULT_ROW = '[data-testid="result-row"]'
    INCLUDE_BUTTON = '[data-testid="include-button"]'
    EXCLUDE_BUTTON = '[data-testid="exclude-button"]'
    RESULTS_PAGINATION = '[data-testid="pagination"]'

    # Workflow actions
    MARK_COMPLETED_BUTTON = '[data-testid="complete-review-btn"]'
    ARCHIVE_SESSION_BUTTON = '[data-testid="archive-session-btn"]'

    # Reporting
    GENERATE_REPORT_BUTTON = '[data-testid="generate-report"]'
    DOWNLOAD_REPORT_BUTTON = '[data-testid="download-report"]'


class TestData:
    """Test data for workflow testing."""

    SEARCH_SESSION = {
        "title": "E2E Test Session - Grey Literature Review",
        "description": "End-to-end testing of the complete workflow from session creation to reporting"
    }

    PIC_STRATEGY = {
        "population_terms": "water",
        "interest_terms": "quality, treatment",
        "context_terms": "urban, cities",
        "selected_domains": ["edu", "org", "gov"],
        "exclude_domains": "example.com, test.com"
    }
