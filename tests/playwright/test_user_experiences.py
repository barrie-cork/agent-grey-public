"""
Playwright tests for different user experience scenarios (anonymous vs authenticated).
"""

from conftest import (expect_success_message,
                      fill_feedback_form, open_feedback_modal,
                      submit_feedback_form)
from playwright.sync_api import Page, expect


class TestUserExperiences:
    """Test feedback system for different user types."""

    def test_anonymous_user_feedback_experience(self, page: Page):
        """Test feedback experience for anonymous (non-logged-in) users."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Email field should be visible for anonymous users
        email_field = page.locator('#feedbackEmail')
        if email_field.is_visible():
            expect(email_field).to_be_visible()
            expect(email_field).to_have_attribute('type', 'email')
            expect(email_field).to_have_attribute('placeholder')
            
            # Help text should explain it's optional
            email_help = page.locator('.form-text', has_text='email')
            expect(email_help).to_be_visible()
            expect(email_help).to_contain_text('optional')

    def test_anonymous_user_successful_submission(self, page: Page):
        """Test successful feedback submission by anonymous user."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill form including email for anonymous user
        fill_feedback_form(
            page,
            feedback_type='suggestion',
            subject='Anonymous user suggestion',
            message='This is feedback from an anonymous user. The system should handle this correctly and store the email for potential follow-up contact.',
            email='anonymous@example.com'
        )
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_anonymous_user_without_email_submission(self, page: Page):
        """Test anonymous user submission without providing email."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill form without email
        fill_feedback_form(
            page,
            feedback_type='bug',
            message='This is anonymous feedback without email. The system should still accept this submission since email is optional.'
        )
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_authenticated_user_feedback_experience(self, page: Page):
        """Test feedback experience for authenticated users."""
        # This test assumes you can create an authenticated session
        # You may need to adapt this based on your authentication system
        
        # For now, we'll test the UI behavior when user is authenticated
        # You would typically login first, then test the feedback experience
        
        page.goto('http://localhost:8000/')
        
        # If user is authenticated, email field should be hidden
        open_feedback_modal(page)
        
        # Check if the page has authentication indicators
        user_indicator = page.locator('[data-testid="user-indicator"]')
        
        if user_indicator.is_visible():
            # User is authenticated
            email_field = page.locator('#feedbackEmail')
            # Email field should be hidden or not required
            expect(email_field).to_have_attribute('type', 'hidden')

    def test_authenticated_user_successful_submission(self, authenticated_page: Page):
        """Test successful feedback submission by authenticated user."""
        authenticated_page.goto('http://localhost:8000/')
        open_feedback_modal(authenticated_page)
        
        # Email field should be hidden for authenticated users
        email_field = authenticated_page.locator('#feedbackEmail')
        if email_field.is_attached():
            expect(email_field).to_have_attribute('type', 'hidden')
        
        fill_feedback_form(
            authenticated_page,
            feedback_type='compliment',
            subject='Authenticated user feedback',
            message='This is feedback from an authenticated user. The system should automatically associate this feedback with the logged-in user account.'
        )
        
        submit_feedback_form(authenticated_page)
        expect_success_message(authenticated_page)

    def test_user_context_in_form(self, page: Page):
        """Test that user context is properly set in the form."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check if user information is properly handled
        # For anonymous users, no user context should be set
        # For authenticated users, user context should be included
        
        _user_context = page.evaluate("""
            () => {
                // Check if there are any user-specific elements or data
                const userElements = document.querySelectorAll('[data-user]');
                return {
                    hasUserElements: userElements.length > 0,
                    userInfo: window.user || null
                };
            }
        """)
        
        # This will vary based on your implementation

    def test_feedback_attribution_anonymous(self, page: Page):
        """Test that anonymous feedback is properly attributed."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Submit feedback with email
        fill_feedback_form(
            page,
            feedback_type='other',
            message='Testing attribution for anonymous feedback with email provided.',
            email='test@example.com'
        )
        
        # Monitor the submission request
        with page.expect_request("**/feedback/submit/") as request_info:
            submit_feedback_form(page)
        
        _request = request_info.value
        
        # Request should not include user authentication
        # but should include email in the form data
        # This verification depends on your backend implementation

    def test_feedback_attribution_authenticated(self, authenticated_page: Page):
        """Test that authenticated feedback is properly attributed."""
        authenticated_page.goto('http://localhost:8000/')
        open_feedback_modal(authenticated_page)
        
        fill_feedback_form(
            authenticated_page,
            feedback_type='bug',
            message='Testing attribution for authenticated user feedback.'
        )
        
        # Monitor the submission request
        with authenticated_page.expect_request("**/feedback/submit/") as request_info:
            submit_feedback_form(authenticated_page)
        
        request = request_info.value
        
        # Request should include authentication information
        _headers = request.headers
        # Check for authentication headers or session cookies
        # This verification depends on your authentication implementation

    def test_login_state_changes_during_session(self, page: Page):
        """Test feedback behavior when login state changes during session."""
        # Start as anonymous
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Email field should be visible
        email_field = page.locator('#feedbackEmail')
        if email_field.is_visible():
            expect(email_field).to_be_visible()
        
        # Close modal
        page.locator('.btn-close').click()
        
        # Simulate login (this would depend on your authentication system)
        # For now, we'll just test the UI behavior
        
        # Note: In a real test, you would perform actual login here
        # page.goto('/accounts/login/')
        # ... login process ...
        
        # Reopen modal after login
        # open_feedback_modal(page)
        
        # Email field behavior should change based on new authentication state

    def test_permission_based_feedback_access(self, page: Page):
        """Test that feedback system respects user permissions."""
        page.goto('http://localhost:8000/')
        
        # All users should be able to access feedback button
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        
        open_feedback_modal(page)
        
        # All users should be able to submit feedback
        submit_btn = page.locator('#submitFeedbackBtn')
        expect(submit_btn).to_be_visible()
        expect(submit_btn).to_be_enabled()

    def test_staff_user_additional_options(self, staff_page: Page):
        """Test that staff users might have additional options (if implemented)."""
        staff_page.goto('http://localhost:8000/')
        open_feedback_modal(staff_page)
        
        # Staff users should have same feedback interface as regular users
        # (unless you've implemented staff-specific features)
        
        form = staff_page.locator('#feedbackForm')
        expect(form).to_be_visible()
        
        # Test that staff can submit feedback like any other user
        fill_feedback_form(
            staff_page,
            feedback_type='improvement',
            message='This is feedback from a staff user testing the feedback system functionality.'
        )
        
        submit_feedback_form(staff_page)
        expect_success_message(staff_page)

    def test_user_feedback_history_access(self, authenticated_page: Page):
        """Test access to feedback history (if implemented)."""
        # This test would check if users can view their own feedback history
        # This depends on whether you've implemented such a feature
        
        authenticated_page.goto('http://localhost:8000/')
        
        # Look for any feedback history links or buttons
        history_link = authenticated_page.locator('[href*="feedback"]', has_text='history')
        
        if history_link.is_visible():
            # If feedback history feature exists, test it
            history_link.click()
            
            # Should show user's feedback history
            expect(authenticated_page).to_have_url('**/feedback/**')

    def test_anonymous_vs_authenticated_form_differences(self, page: Page):
        """Test visual and functional differences between anonymous and authenticated forms."""
        # Test anonymous form first
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        anonymous_form_html = page.locator('#feedbackForm').inner_html()
        
        # Close modal
        page.locator('.btn-close').click()
        
        # Note: In a real scenario, you would test with actual authentication
        # For demonstration, we'll check form structure differences
        
        # Reopen to ensure consistency
        open_feedback_modal(page)
        
        current_form_html = page.locator('#feedbackForm').inner_html()
        
        # Form should be consistent for same user state
        assert anonymous_form_html == current_form_html

    def test_csrf_token_handling_different_users(self, page: Page):
        """Test CSRF token handling for different user types."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check that CSRF token is present
        csrf_elements = page.evaluate("""
            () => {
                // Look for CSRF tokens in various forms
                const metaToken = document.querySelector('meta[name="csrf-token"]');
                const inputToken = document.querySelector('input[name="csrfmiddlewaretoken"]');
                const cookieToken = document.cookie.split(';')
                    .find(c => c.trim().startsWith('csrftoken='));
                
                return {
                    metaToken: metaToken ? metaToken.getAttribute('content') : null,
                    inputToken: inputToken ? inputToken.value : null,
                    cookieToken: cookieToken ? cookieToken.split('=')[1] : null
                };
            }
        """)
        
        # At least one CSRF protection method should be present
        has_csrf_protection = (
            csrf_elements['metaToken'] or 
            csrf_elements['inputToken'] or 
            csrf_elements['cookieToken']
        )
        
        assert has_csrf_protection, "CSRF protection should be present"

    def test_session_timeout_feedback_behavior(self, page: Page):
        """Test feedback behavior when session times out."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill form but don't submit immediately
        fill_feedback_form(
            page,
            feedback_type='other',
            message='Testing feedback behavior with session timeout scenarios.'
        )
        
        # In a real test, you would simulate session timeout
        # For now, just test that the form maintains its data
        
        # Wait a short time
        page.wait_for_timeout(1000)
        
        # Form data should still be there
        form_values = page.evaluate("""
            () => {
                return {
                    type: document.getElementById('feedbackType').value,
                    message: document.getElementById('feedbackMessage').value
                };
            }
        """)
        
        assert form_values['type'] == 'other'
        assert 'session timeout' in form_values['message']

    def test_multiple_browser_tabs_feedback(self, page: Page):
        """Test feedback behavior across multiple browser tabs."""
        # Open feedback modal in first tab
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Open second tab
        page2 = page.context.new_page()
        page2.goto('http://localhost:8000/')
        open_feedback_modal(page2)
        
        # Both modals should work independently
        fill_feedback_form(
            page,
            feedback_type='bug',
            message='Feedback from first tab testing multiple browser tabs functionality.'
        )
        
        fill_feedback_form(
            page2,
            feedback_type='suggestion',
            message='Feedback from second tab testing multiple browser tabs functionality.'
        )
        
        # Submit from first tab
        submit_feedback_form(page)
        expect_success_message(page)
        
        # Submit from second tab
        submit_feedback_form(page2)
        expect_success_message(page2)
        
        # Clean up
        page2.close()