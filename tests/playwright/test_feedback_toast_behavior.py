"""
Playwright tests for feedback system toast behavior.

Tests ensure that the success toast doesn't appear on page load
and only shows after successful feedback submission.
"""

import pytest
from playwright.async_api import Page, expect


class TestFeedbackToastBehavior:
    """Test suite for feedback toast behavior."""

    @pytest.fixture
    async def page_with_user(self, page: Page):
        """Setup a page with authenticated user."""
        # Navigate to login page and authenticate
        await page.goto("http://localhost:8000/accounts/login/")
        await page.fill("input[name='username']", "testuser")
        await page.fill("input[name='password']", "testpass123")
        await page.click("button[type='submit']")
        await expect(page).to_have_url("/")
        return page

    async def test_toast_not_visible_on_page_load(self, page: Page):
        """Test that feedback toast is not visible when page loads."""
        # Navigate to homepage
        await page.goto("http://localhost:8000/")

        # Wait for page to fully load
        await page.wait_for_load_state("networkidle")

        # Check that feedback toast is not visible
        toast = page.locator("#feedbackToast")
        await expect(toast).not_to_be_visible()

        # Also check that the toast doesn't have the 'show' class
        await expect(toast).not_to_have_class("show")

        # Verify toast element exists but is hidden
        await expect(toast).to_be_attached()

    async def test_toast_not_visible_on_multiple_page_loads(self, page: Page):
        """Test toast doesn't show on multiple different page loads."""
        pages_to_test = [
            "http://localhost:8000/",
            "http://localhost:8000/accounts/login/",
            "http://localhost:8000/review-manager/",
        ]

        for url in pages_to_test:
            # Navigate to page
            await page.goto(url)
            await page.wait_for_load_state("networkidle")

            # Check toast is not visible
            toast = page.locator("#feedbackToast")

            # Only check if toast exists (some pages might not have it)
            if await toast.count() > 0:
                await expect(toast).not_to_be_visible()
                await expect(toast).not_to_have_class("show")

    async def test_feedback_button_exists_and_functional(self, page: Page):
        """Test that feedback button exists and can be clicked without showing toast."""
        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")

        # Check feedback button exists
        feedback_btn = page.locator("#feedbackBtn")
        await expect(feedback_btn).to_be_visible()

        # Click feedback button to open modal
        await feedback_btn.click()

        # Wait for modal to appear
        modal = page.locator("#feedbackModal")
        await expect(modal).to_be_visible()

        # Toast should still not be visible
        toast = page.locator("#feedbackToast")
        await expect(toast).not_to_be_visible()

        # Close modal
        close_btn = page.locator("#feedbackModal .btn-close")
        await close_btn.click()

        # Wait for modal to disappear
        await expect(modal).not_to_be_visible()

        # Toast should still not be visible
        await expect(toast).not_to_be_visible()

    async def test_toast_shows_after_successful_submission(self, page_with_user: Page):
        """Test that toast shows only after successful feedback submission."""
        page = page_with_user
        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")

        # Initially toast should not be visible
        toast = page.locator("#feedbackToast")
        await expect(toast).not_to_be_visible()

        # Open feedback modal
        feedback_btn = page.locator("#feedbackBtn")
        await feedback_btn.click()

        # Wait for modal
        modal = page.locator("#feedbackModal")
        await expect(modal).to_be_visible()

        # Fill out feedback form
        await page.select_option("#feedbackType", "suggestion")
        await page.fill(
            "#feedbackMessage",
            "This is a test feedback message with enough characters to pass validation."
        )

        # Submit form
        submit_btn = page.locator("#submitFeedbackBtn")
        await submit_btn.click()

        # Wait for submission to complete and modal to close
        await expect(modal).not_to_be_visible(timeout=10000)

        # Now toast should be visible
        await expect(toast).to_be_visible(timeout=5000)

        # Toast should have success styling
        toast_header = page.locator("#feedbackToast .toast-header")
        success_icon = toast_header.locator(".bi-check-circle-fill.text-success")
        await expect(success_icon).to_be_visible()

        # Toast should contain success message
        toast_body = page.locator("#feedbackToast .toast-body")
        await expect(toast_body).to_contain_text("Thank you for your feedback")

    async def test_toast_accessibility_attributes(self, page: Page):
        """Test that toast has proper accessibility attributes when shown."""
        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")

        # Initially toast should not have aria-live attributes
        toast = page.locator("#feedbackToast")
        await expect(toast).not_to_have_attribute("aria-live")
        await expect(toast).not_to_have_attribute("aria-atomic")

        # Test that accessibility attributes are only added when showing
        # (This would require a successful form submission to fully test)

    async def test_toast_css_display_property(self, page: Page):
        """Test that toast has correct CSS display property on load."""
        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")

        # Toast should have display: none style
        toast = page.locator("#feedbackToast")
        display_style = await toast.evaluate("element => window.getComputedStyle(element).display")
        assert display_style == "none", f"Expected display: none, got display: {display_style}"

    async def test_toast_behavior_across_browsers(self, page: Page):
        """Test toast behavior is consistent across different browsers."""
        # This test will be run automatically across different browser projects
        # as configured in playwright.config.js

        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")

        # Get browser name for logging
        browser_name = page.context.browser.browser_type.name

        # Toast should not be visible regardless of browser
        toast = page.locator("#feedbackToast")
        await expect(toast).not_to_be_visible()

        # Verify JavaScript initialization worked
        feedback_system_exists = await page.evaluate("""
            typeof window.FeedbackSystem !== 'undefined' &&
            typeof window.FeedbackSystem.initializeToast === 'function'
        """)

        assert feedback_system_exists, f"FeedbackSystem not properly initialized in {browser_name}"

    async def test_no_console_errors_on_load(self, page: Page):
        """Test that there are no JavaScript console errors related to toast on page load."""
        console_messages = []
        page.on("console", lambda msg: console_messages.append(msg))

        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")

        # Wait a moment for any delayed errors
        await page.wait_for_timeout(1000)

        # Check for any error messages related to feedback or toast
        error_messages = [msg for msg in console_messages if msg.type == "error"]
        feedback_related_errors = [
            msg for msg in error_messages
            if any(keyword in msg.text.lower() for keyword in ["feedback", "toast", "bootstrap"])
        ]

        assert len(feedback_related_errors) == 0, (
            f"Console errors found: {[msg.text for msg in feedback_related_errors]}"
        )

    async def test_toast_manual_trigger_via_javascript(self, page: Page):
        """Test that toast can be manually triggered via JavaScript and works correctly."""
        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")

        # Initially toast should not be visible
        toast = page.locator("#feedbackToast")
        await expect(toast).not_to_be_visible()

        # Manually trigger toast via JavaScript
        await page.evaluate("window.FeedbackSystem.showToast('Test message')")

        # Toast should now be visible
        await expect(toast).to_be_visible(timeout=2000)

        # Toast should contain our test message
        toast_body = page.locator("#feedbackToast .toast-body")
        await expect(toast_body).to_have_text("Test message")

        # Wait for toast to auto-hide (default 5 seconds)
        await expect(toast).not_to_be_visible(timeout=6000)
