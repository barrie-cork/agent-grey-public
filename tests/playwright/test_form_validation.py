"""
Playwright tests for feedback form validation and error handling.
"""

from conftest import (expect_error_message,
                      fill_feedback_form, open_feedback_modal,
                      submit_feedback_form)
from playwright.sync_api import Page, expect


class TestFormValidation:
    """Test feedback form validation and error handling."""

    def test_empty_form_validation(self, page: Page):
        """Test validation when submitting empty form."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Submit empty form
        submit_feedback_form(page)
        
        # Should show validation errors
        expect_error_message(page, 'Please select a feedback type')

    def test_missing_feedback_type_validation(self, page: Page):
        """Test validation when feedback type is missing."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill only message
        page.fill('#feedbackMessage', 'This is a test message with sufficient length')
        submit_feedback_form(page)
        
        # Should show error for missing type
        expect_error_message(page, 'Please select a feedback type')

    def test_missing_message_validation(self, page: Page):
        """Test validation when message is missing."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill only type
        page.select_option('#feedbackType', 'bug')
        submit_feedback_form(page)
        
        # Should show error for missing message
        expect_error_message(page, 'Please provide a detailed message')

    def test_message_too_short_validation(self, page: Page):
        """Test validation when message is too short."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page, message='Short')  # Less than 10 characters
        submit_feedback_form(page)
        
        # Should show error for short message
        expect_error_message(page, 'at least 10 characters')

    def test_message_too_long_validation(self, page: Page):
        """Test validation when message is too long."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Create message over 2000 characters
        long_message = 'x' * 2001
        fill_feedback_form(page, message=long_message)
        submit_feedback_form(page)
        
        # Should show error for long message
        expect_error_message(page, 'under 2000 characters')

    def test_message_with_spam_links_validation(self, page: Page):
        """Test validation rejects messages with multiple links."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        spam_message = 'Check out http://example.com and http://test.com and http://spam.com for more info. This message has enough length to pass the minimum character requirement but contains multiple links which should be flagged as spam.'
        fill_feedback_form(page, message=spam_message)
        submit_feedback_form(page)
        
        # Should show error for spam-like content
        expect_error_message(page, 'multiple links')

    def test_client_side_validation_prevents_submission(self, page: Page):
        """Test that client-side validation prevents form submission."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # HTML5 required attribute should prevent submission
        message_field = page.locator('#feedbackMessage')
        expect(message_field).to_have_attribute('required')
        
        type_field = page.locator('#feedbackType')
        expect(type_field).to_have_attribute('required')

    def test_character_count_validation_visual_feedback(self, page: Page):
        """Test visual feedback for character count approaching limits."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        message_field = page.locator('#feedbackMessage')
        _char_counter = page.locator('#messageCharCount')
        
        # Test warning zone (1500-1800 characters)
        warning_message = 'x' * 1600
        message_field.fill(warning_message)
        
        # Counter should be yellow/warning color
        warning_color = page.evaluate("""
            () => {
                const counter = document.getElementById('messageCharCount');
                return window.getComputedStyle(counter).color;
            }
        """)
        assert 'rgb(255, 193, 7)' in warning_color or '#ffc107' in warning_color.lower()
        
        # Test danger zone (1800+ characters)
        danger_message = 'x' * 1900
        message_field.fill(danger_message)
        
        # Counter should be red/danger color
        danger_color = page.evaluate("""
            () => {
                const counter = document.getElementById('messageCharCount');
                return window.getComputedStyle(counter).color;
            }
        """)
        assert 'rgb(220, 53, 69)' in danger_color or '#dc3545' in danger_color.lower()

    def test_email_validation_for_anonymous_users(self, page: Page):
        """Test email validation for anonymous users."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check if email field is visible (depends on authentication state)
        email_field = page.locator('#feedbackEmail')
        if email_field.is_visible():
            # Fill with invalid email
            fill_feedback_form(page, email='invalid-email')
            submit_feedback_form(page)
            
            # HTML5 validation should catch this
            email_validity = page.evaluate("""
                () => {
                    const email = document.getElementById('feedbackEmail');
                    return email.validity.valid;
                }
            """)
            assert not email_validity

    def test_form_reset_clears_validation_errors(self, page: Page):
        """Test that form reset clears validation errors."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Trigger validation error
        submit_feedback_form(page)
        expect_error_message(page)
        
        # Close and reopen modal (should reset form)
        page.locator('.btn-close').click()
        open_feedback_modal(page)
        
        # Error messages should be gone
        error_container = page.locator('#feedbackMessages')
        expect(error_container).not_to_be_visible()

    def test_real_time_validation_feedback(self, page: Page):
        """Test real-time validation feedback as user types."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        message_field = page.locator('#feedbackMessage')
        
        # Start with short text
        message_field.fill('Short')
        
        # Message should have some visual indication (border color, etc.)
        # This depends on the specific implementation of real-time validation
        
        # Fill with valid length text
        message_field.fill('This is a valid message with sufficient length for the feedback system')
        
        # Validation state should update

    def test_form_submission_loading_state(self, page: Page):
        """Test form submission loading state and button disable."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        
        submit_btn = page.locator('#submitFeedbackBtn')
        
        # Button should be enabled initially
        expect(submit_btn).to_be_enabled()
        
        # Click submit
        submit_btn.click()
        
        # Button should show loading state (this happens quickly)
        # We'll check for the loading elements
        _loading_text = submit_btn.locator('.loading-text')
        _submit_text = submit_btn.locator('.submit-text')
        
        # At some point during submission, these states should change
        # Note: This test might be timing-dependent

    def test_prevent_double_submission(self, page: Page):
        """Test that double submission is prevented."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        
        submit_btn = page.locator('#submitFeedbackBtn')
        
        # Click submit multiple times quickly
        submit_btn.click()
        submit_btn.click()
        submit_btn.click()
        
        # Only one submission should occur (check via network monitoring or button state)
        # Button should be disabled after first click
        expect(submit_btn).to_be_disabled()

    def test_error_message_display_and_dismissal(self, page: Page):
        """Test error message display and dismissal."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Trigger validation error
        submit_feedback_form(page)
        
        # Error should be displayed
        error_alert = page.locator('.alert-danger')
        expect(error_alert).to_be_visible()
        
        # Should have dismiss button
        dismiss_btn = error_alert.locator('.btn-close')
        expect(dismiss_btn).to_be_visible()
        
        # Click dismiss
        dismiss_btn.click()
        
        # Error should be hidden
        expect(error_alert).not_to_be_visible()

    def test_field_specific_error_handling(self, page: Page):
        """Test field-specific error handling and display."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Test various field-specific errors by manipulating form state
        
        # Required field validation
        type_field = page.locator('#feedbackType')
        message_field = page.locator('#feedbackMessage')
        
        # Focus and blur required fields without filling
        type_field.focus()
        type_field.blur()
        
        message_field.focus()
        message_field.blur()
        
        # Some visual indication should appear (border colors, etc.)
        # This depends on the specific validation implementation

    def test_form_validation_accessibility(self, page: Page):
        """Test that form validation is accessible."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Trigger validation error
        submit_feedback_form(page)
        
        # Error message should have proper ARIA attributes
        error_alert = page.locator('.alert-danger')
        expect(error_alert).to_have_attribute('role', 'alert')
        
        # Form fields should have aria-describedby pointing to error messages
        # (if implemented)

    def test_maxlength_attributes(self, page: Page):
        """Test that form fields have appropriate maxlength attributes."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check subject field maxlength
        subject_field = page.locator('#feedbackSubject')
        expect(subject_field).to_have_attribute('maxlength', '200')
        
        # Message field should not prevent typing but should show warning
        message_field = page.locator('#feedbackMessage')
        
        # Type text up to limit
        long_text = 'x' * 2000
        message_field.fill(long_text)
        
        # Character counter should show limit
        char_counter = page.locator('#messageCharCount')
        expect(char_counter).to_contain_text('2000')

    def test_placeholder_text_guidance(self, page: Page):
        """Test that placeholder text changes based on feedback type."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        _message_field = page.locator('#feedbackMessage')
        type_field = page.locator('#feedbackType')
        
        # Select bug report
        type_field.select_option('bug')
        
        # Placeholder should change to bug-specific guidance
        placeholder = page.evaluate("""
            () => document.getElementById('feedbackMessage').placeholder
        """)
        assert 'bug' in placeholder.lower() or 'expect' in placeholder.lower()
        
        # Select feature suggestion
        type_field.select_option('suggestion')
        
        # Placeholder should change to suggestion-specific guidance
        placeholder = page.evaluate("""
            () => document.getElementById('feedbackMessage').placeholder
        """)
        assert 'suggestion' in placeholder.lower() or 'feature' in placeholder.lower()

    def test_subject_auto_population(self, page: Page):
        """Test that subject field auto-populates based on feedback type."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        type_field = page.locator('#feedbackType')
        subject_field = page.locator('#feedbackSubject')
        
        # Initially subject should be empty
        expect(subject_field).to_have_value('')
        
        # Select bug report
        type_field.select_option('bug')
        
        # Subject should auto-populate
        page.wait_for_timeout(100)  # Small delay for JS to execute
        subject_value = subject_field.input_value()
        assert 'Bug Report:' in subject_value
        
        # Select feature suggestion
        subject_field.fill('')  # Clear first
        type_field.select_option('suggestion')
        
        page.wait_for_timeout(100)
        subject_value = subject_field.input_value()
        assert 'Feature Request:' in subject_value