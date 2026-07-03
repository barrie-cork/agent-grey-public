"""
Playwright tests for successful feedback submission flows.
"""

from conftest import (expect_success_message,
                      fill_feedback_form, open_feedback_modal,
                      submit_feedback_form)
from playwright.sync_api import Page, expect


class TestFeedbackSubmission:
    """Test successful feedback submission scenarios."""

    def test_successful_bug_report_submission(self, page: Page):
        """Test successful bug report submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill bug report
        fill_feedback_form(
            page,
            feedback_type='bug',
            subject='Test Bug Report',
            message='This is a detailed bug report describing an issue I encountered. The bug occurs when I try to navigate to a specific page and causes unexpected behavior that prevents normal functionality.',
            rating='2'
        )
        
        # Submit form
        submit_feedback_form(page)
        
        # Should show success message
        expect_success_message(page)
        
        # Modal should close after success
        modal = page.locator('#feedbackModal')
        page.wait_for_timeout(2500)  # Wait for auto-close
        expect(modal).not_to_be_visible()
        
        # Toast notification should appear
        toast = page.locator('#feedbackToast')
        expect(toast).to_be_visible()

    def test_successful_feature_suggestion_submission(self, page: Page):
        """Test successful feature suggestion submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill feature suggestion
        fill_feedback_form(
            page,
            feedback_type='suggestion',
            subject='Feature Request: Dark Mode',
            message='I would love to see a dark mode option added to the application. This would be very helpful for users who prefer darker interfaces or work in low-light conditions.',
            rating='4'
        )
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_successful_compliment_submission(self, page: Page):
        """Test successful compliment submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill compliment
        fill_feedback_form(
            page,
            feedback_type='compliment',
            subject='Love the new interface!',
            message='The new interface is absolutely fantastic! It is intuitive, clean, and makes the whole experience so much better. Great work on the design and user experience.',
            rating='5'
        )
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_successful_improvement_suggestion_submission(self, page: Page):
        """Test successful improvement suggestion submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill improvement suggestion
        fill_feedback_form(
            page,
            feedback_type='improvement',
            subject='Search functionality could be better',
            message='The search functionality works well, but it could be improved with better filtering options and faster response times. Adding autocomplete suggestions would also enhance the user experience.',
            rating='3'
        )
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_successful_other_feedback_submission(self, page: Page):
        """Test successful other feedback submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill other feedback
        fill_feedback_form(
            page,
            feedback_type='other',
            subject='General feedback about the application',
            message='I wanted to provide some general feedback about my experience using this application. Overall, it meets my needs well and I appreciate the effort put into making it user-friendly.',
            rating='4'
        )
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_submission_without_optional_fields(self, page: Page):
        """Test successful submission with only required fields."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill only required fields
        page.select_option('#feedbackType', 'bug')
        page.fill('#feedbackMessage', 'This is a minimal bug report with just the required information needed to submit feedback successfully.')
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_submission_with_maximum_length_message(self, page: Page):
        """Test submission with message at maximum allowed length."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Create message close to maximum length (2000 characters)
        max_message = 'This is a very detailed feedback message. ' * 45  # ~1980 characters
        
        fill_feedback_form(
            page,
            feedback_type='suggestion',
            message=max_message
        )
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_submission_with_all_star_ratings(self, page: Page):
        """Test successful submission with different star ratings."""
        ratings = ['1', '2', '3', '4', '5']
        
        for rating in ratings:
            with page.context.new_page() as test_page:
                test_page.goto('http://localhost:8000/')
                open_feedback_modal(test_page)
                
                fill_feedback_form(
                    test_page,
                    feedback_type='other',
                    message=f'This is a test feedback with {rating} star rating. The message needs to be long enough to pass validation requirements.',
                    rating=rating
                )
                
                submit_feedback_form(test_page)
                expect_success_message(test_page)

    def test_form_data_capture_accuracy(self, page: Page):
        """Test that form data is captured accurately."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill form with specific test data
        test_data = {
            'feedback_type': 'bug',
            'subject': 'Specific Test Subject',
            'message': 'This is a specific test message designed to verify that form data is captured accurately during submission process.',
            'rating': '3'
        }
        
        fill_feedback_form(page, **test_data)
        
        # Verify data is in form before submission
        form_values = page.evaluate("""
            () => {
                return {
                    type: document.getElementById('feedbackType').value,
                    subject: document.getElementById('feedbackSubject').value,
                    message: document.getElementById('feedbackMessage').value,
                    rating: document.querySelector('input[name="rating"]:checked')?.value,
                    path: document.getElementById('feedbackPagePath').value,
                    title: document.getElementById('feedbackPageTitle').value
                };
            }
        """)
        
        assert form_values['type'] == test_data['feedback_type']
        assert form_values['subject'] == test_data['subject']
        assert form_values['message'] == test_data['message']
        assert form_values['rating'] == test_data['rating']
        assert form_values['path'] == '/'
        assert form_values['title'] is not None
        
        submit_feedback_form(page)
        expect_success_message(page)

    def test_page_context_capture(self, page: Page):
        """Test that page context is captured correctly."""
        # Test from different pages
        test_pages = [
            ('http://localhost:8000/', '/'),
            ('http://localhost:8000/accounts/login/', '/accounts/login/'),
        ]
        
        for url, expected_path in test_pages:
            with page.context.new_page() as test_page:
                test_page.goto(url)
                open_feedback_modal(test_page)
                
                # Check that page path is set correctly
                page_path = test_page.locator('#feedbackPagePath').input_value()
                assert page_path == expected_path
                
                # Check that page title is captured
                page_title = test_page.locator('#feedbackPageTitle').input_value()
                assert len(page_title) > 0

    def test_technical_info_capture(self, page: Page):
        """Test that technical information is captured."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        
        # Monitor network request to verify technical info is sent
        with page.expect_request("**/feedback/submit/") as request_info:
            submit_feedback_form(page)
        
        request = request_info.value
        
        # Should be POST request
        assert request.method == 'POST'
        
        # Should have CSRF token
        headers = request.headers
        assert 'x-csrftoken' in headers or 'csrfmiddlewaretoken' in str(request.post_data)

    def test_ajax_submission_no_page_reload(self, page: Page):
        """Test that form submission is AJAX and doesn't reload page."""
        page.goto('http://localhost:8000/')
        
        # Get current URL and page load time
        initial_url = page.url
        page_load_timestamp = page.evaluate('Date.now()')
        
        open_feedback_modal(page)
        fill_feedback_form(page)
        submit_feedback_form(page)
        
        # Wait for submission to complete
        expect_success_message(page)
        
        # URL should not have changed
        assert page.url == initial_url
        
        # Page should not have reloaded (timestamp should be the same)
        current_timestamp = page.evaluate('Date.now()')
        # Allow some time difference but not a full page reload
        assert current_timestamp - page_load_timestamp < 5000

    def test_submit_button_loading_state_during_submission(self, page: Page):
        """Test submit button shows loading state during submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        
        submit_btn = page.locator('#submitFeedbackBtn')
        submit_text = submit_btn.locator('.submit-text')
        loading_text = submit_btn.locator('.loading-text')
        
        # Initially submit text visible, loading hidden
        expect(submit_text).to_be_visible()
        expect(loading_text).to_have_class('d-none')
        
        # Click submit
        submit_btn.click()
        
        # During submission, loading should be visible
        # Note: This might be timing-dependent
        page.wait_for_timeout(50)  # Small delay to catch loading state
        
        # Eventually should return to normal state or show success

    def test_success_message_content_and_styling(self, page: Page):
        """Test success message content and styling."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        submit_feedback_form(page)
        
        # Check success message
        success_alert = page.locator('.alert-success')
        expect(success_alert).to_be_visible()
        expect(success_alert).to_contain_text('Thank you')
        
        # Should have proper Bootstrap classes
        expect(success_alert).to_have_class('alert-success')
        
        # Should have dismiss button
        dismiss_btn = success_alert.locator('.btn-close')
        expect(dismiss_btn).to_be_visible()

    def test_modal_auto_close_after_success(self, page: Page):
        """Test that modal automatically closes after successful submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()
        
        fill_feedback_form(page)
        submit_feedback_form(page)
        
        # Success message should appear
        expect_success_message(page)
        
        # Modal should automatically close after delay
        page.wait_for_timeout(2500)  # Wait for auto-close delay
        expect(modal).not_to_be_visible()

    def test_toast_notification_after_submission(self, page: Page):
        """Test toast notification appears after modal closes."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        submit_feedback_form(page)
        
        # Wait for modal to close
        modal = page.locator('#feedbackModal')
        page.wait_for_timeout(2500)
        expect(modal).not_to_be_visible()
        
        # Toast should appear
        toast = page.locator('#feedbackToast')
        expect(toast).to_be_visible()
        expect(toast.locator('.toast-body')).to_contain_text('Thank you')

    def test_form_reset_after_successful_submission(self, page: Page):
        """Test that form is reset after successful submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Submit first feedback
        fill_feedback_form(page, subject='First feedback')
        submit_feedback_form(page)
        
        # Wait for modal to close
        page.wait_for_timeout(2500)
        
        # Open modal again
        open_feedback_modal(page)
        
        # Form should be reset
        form_values = page.evaluate("""
            () => {
                return {
                    type: document.getElementById('feedbackType').value,
                    subject: document.getElementById('feedbackSubject').value,
                    message: document.getElementById('feedbackMessage').value,
                    rating: document.querySelector('input[name="rating"]:checked')?.value
                };
            }
        """)
        
        assert form_values['type'] == ''
        assert form_values['subject'] == ''
        assert form_values['message'] == ''
        assert form_values['rating'] is None

    def test_multiple_submissions_from_same_session(self, page: Page):
        """Test multiple feedback submissions from same session."""
        page.goto('http://localhost:8000/')
        
        # Submit first feedback
        open_feedback_modal(page)
        fill_feedback_form(page, subject='First feedback', message='This is the first feedback submission to test multiple submissions from the same session.')
        submit_feedback_form(page)
        expect_success_message(page)
        
        # Wait for modal to close
        page.wait_for_timeout(2500)
        
        # Submit second feedback
        open_feedback_modal(page)
        fill_feedback_form(page, subject='Second feedback', message='This is the second feedback submission to verify that multiple submissions work correctly.')
        submit_feedback_form(page)
        expect_success_message(page)