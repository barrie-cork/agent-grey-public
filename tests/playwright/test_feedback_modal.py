"""
Playwright tests for feedback modal and form elements.
"""

from conftest import (open_feedback_modal)
from playwright.sync_api import Page, expect


class TestFeedbackModal:
    """Test the feedback modal functionality and form elements."""

    def test_modal_opens_correctly(self, page: Page):
        """Test that modal opens with correct structure and elements."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        
        # Check modal structure
        expect(modal).to_be_visible()
        expect(modal.locator('.modal-header')).to_be_visible()
        expect(modal.locator('.modal-body')).to_be_visible()
        expect(modal.locator('.modal-footer')).to_be_visible()
        
        # Check modal title
        expect(modal.locator('.modal-title')).to_contain_text('Share Your Feedback')
        expect(modal.locator('.modal-title i.bi-chat-dots')).to_be_visible()

    def test_modal_close_button_works(self, page: Page):
        """Test that modal can be closed using close button."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()
        
        # Click close button
        close_btn = modal.locator('.btn-close')
        close_btn.click()
        
        # Modal should be hidden
        expect(modal).not_to_be_visible()

    def test_modal_cancel_button_works(self, page: Page):
        """Test that modal can be closed using cancel button."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()
        
        # Click cancel button
        cancel_btn = modal.locator('button', has_text='Cancel')
        cancel_btn.click()
        
        # Modal should be hidden
        expect(modal).not_to_be_visible()

    def test_modal_escape_key_closes(self, page: Page):
        """Test that modal can be closed using Escape key."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()
        
        # Press Escape key
        page.keyboard.press('Escape')
        
        # Modal should be hidden
        expect(modal).not_to_be_visible()

    def test_feedback_form_elements_present(self, page: Page):
        """Test that all form elements are present in the modal."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        form = page.locator('#feedbackForm')
        
        # Check required form elements
        expect(form.locator('#feedbackType')).to_be_visible()
        expect(form.locator('#feedbackSubject')).to_be_visible()
        expect(form.locator('#feedbackMessage')).to_be_visible()
        expect(form.locator('input[name="rating"]')).to_have_count(5)  # 5 star ratings
        expect(form.locator('#submitFeedbackBtn')).to_be_visible()
        
        # Check hidden fields
        expect(form.locator('#feedbackPagePath')).to_be_attached()
        expect(form.locator('#feedbackPageTitle')).to_be_attached()

    def test_feedback_type_options(self, page: Page):
        """Test that feedback type dropdown has correct options."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        type_select = page.locator('#feedbackType')
        
        # Check that all expected options are present
        expected_options = [
            ('', 'Please select...'),
            ('bug', '🐛 Bug Report - Something isn\'t working'),
            ('suggestion', '💡 Feature Suggestion - I have an idea'),
            ('improvement', '⚡ Improvement - This could be better'),
            ('compliment', '👏 Compliment - I love this!'),
            ('other', '💬 Other - General feedback')
        ]
        
        for value, text in expected_options:
            option = type_select.locator(f'option[value="{value}"]')
            expect(option).to_be_attached()
            expect(option).to_contain_text(text.split(' - ')[0])

    def test_star_rating_interaction(self, page: Page):
        """Test star rating system interaction."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Test clicking different star ratings
        for rating in range(1, 6):
            star_input = page.locator(f'#star{rating}')
            star_label = page.locator(f'label[for="star{rating}"]')
            
            # Star should be visible and clickable
            expect(star_label).to_be_visible()
            star_label.click()
            
            # Input should be checked
            expect(star_input).to_be_checked()
            
            # Rating text should update
            rating_text = page.locator('.rating-text small')
            expect(rating_text).not_to_contain_text('Click stars to rate')

    def test_star_rating_hover_effects(self, page: Page):
        """Test star rating hover effects."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Hover over 3rd star
        star_label = page.locator('label[for="star3"]')
        star_label.hover()
        
        # Check that stars have hover styling
        hover_color = page.evaluate("""
            () => {
                const label = document.querySelector('label[for="star3"]');
                return window.getComputedStyle(label).color;
            }
        """)
        
        # Should show golden color on hover
        assert 'rgb(255, 193, 7)' in hover_color or '#ffc107' in hover_color.lower()

    def test_character_counter_updates(self, page: Page):
        """Test that character counter updates as user types."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        message_field = page.locator('#feedbackMessage')
        char_counter = page.locator('#messageCharCount')
        
        # Initially should be 0
        expect(char_counter).to_contain_text('0')
        
        # Type some text
        test_message = 'This is a test message'
        message_field.fill(test_message)
        
        # Counter should update
        expect(char_counter).to_contain_text(str(len(test_message)))

    def test_character_counter_color_changes(self, page: Page):
        """Test that character counter changes color near limits."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        message_field = page.locator('#feedbackMessage')
        _char_counter = page.locator('#messageCharCount')
        
        # Fill with text approaching limit
        long_message = 'x' * 1600  # Between 1500-1800 (warning zone)
        message_field.fill(long_message)
        
        # Counter should change color to yellow/warning
        counter_color = page.evaluate("""
            () => {
                const counter = document.getElementById('messageCharCount');
                return window.getComputedStyle(counter).color;
            }
        """)
        
        # Should be yellow warning color
        assert 'rgb(255, 193, 7)' in counter_color or '#ffc107' in counter_color.lower()

    def test_page_context_auto_populated(self, page: Page):
        """Test that page context is automatically populated."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check hidden fields are populated
        page_path = page.locator('#feedbackPagePath').input_value()
        page_title = page.locator('#feedbackPageTitle').input_value()
        
        assert page_path == '/'
        assert page_title is not None
        assert len(page_title) > 0
        
        # Check display shows current page
        page_display = page.locator('#currentPageDisplay')
        expect(page_display).not_to_contain_text('Loading...')

    def test_form_fields_labels_and_help_text(self, page: Page):
        """Test that form fields have proper labels and help text."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check form labels
        expect(page.locator('label[for="feedbackType"]')).to_contain_text('What type of feedback')
        expect(page.locator('label[for="feedbackSubject"]')).to_contain_text('Subject')
        expect(page.locator('label[for="feedbackMessage"]')).to_contain_text('Your Feedback')
        
        # Check help text
        expect(page.locator('.form-text')).to_be_visible()
        expect(page.locator('.form-text', has_text='categorize')).to_be_visible()
        expect(page.locator('.form-text', has_text='characters')).to_be_visible()

    def test_required_field_indicators(self, page: Page):
        """Test that required fields are properly marked."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check for required field indicators (red asterisks)
        required_indicators = page.locator('.text-danger', has_text='*')
        expect(required_indicators).to_have_count(2)  # Type and Message are required

    def test_modal_styling_and_layout(self, page: Page):
        """Test modal styling and layout."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        
        # Check modal has correct classes
        expect(modal).to_have_class('modal')
        expect(modal.locator('.modal-dialog')).to_have_class('modal-lg')
        
        # Check header styling
        _modal_header = modal.locator('.modal-header')
        header_bg = page.evaluate("""
            () => {
                const header = document.querySelector('#feedbackModal .modal-header');
                return window.getComputedStyle(header).background;
            }
        """)
        
        # Should have gradient background
        assert 'gradient' in header_bg.lower() or 'linear' in header_bg.lower()

    def test_submit_button_states(self, page: Page):
        """Test submit button different states."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        submit_btn = page.locator('#submitFeedbackBtn')
        
        # Initially should show "Send Feedback"
        expect(submit_btn.locator('.submit-text')).to_contain_text('Send Feedback')
        expect(submit_btn.locator('.submit-text i.bi-send')).to_be_visible()
        
        # Loading text should be hidden
        expect(submit_btn.locator('.loading-text')).to_have_class('d-none')

    def test_modal_backdrop_click_behavior(self, page: Page):
        """Test modal backdrop click behavior (should not close due to static backdrop)."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()
        
        # Click on backdrop (outside modal content)
        modal_backdrop = page.locator('.modal-backdrop')
        if modal_backdrop.count() > 0:
            modal_backdrop.click()
            
            # Modal should still be visible (static backdrop)
            expect(modal).to_be_visible()

    def test_form_field_focus_management(self, page: Page):
        """Test that form fields can be focused and navigated properly."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # First field should be focusable
        type_field = page.locator('#feedbackType')
        type_field.focus()
        expect(type_field).to_be_focused()
        
        # Tab through fields
        page.keyboard.press('Tab')
        subject_field = page.locator('#feedbackSubject')
        expect(subject_field).to_be_focused()
        
        page.keyboard.press('Tab')
        message_field = page.locator('#feedbackMessage')
        expect(message_field).to_be_focused()

    def test_modal_responsive_on_mobile(self, page: Page):
        """Test modal responsiveness on mobile devices."""
        # Set mobile viewport
        page.set_viewport_size({'width': 375, 'height': 667})
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        _modal_dialog = modal.locator('.modal-dialog')
        
        # Modal should be visible and properly sized
        expect(modal).to_be_visible()
        
        # Check that modal doesn't overflow viewport
        modal_width = page.evaluate("""
            () => {
                const dialog = document.querySelector('#feedbackModal .modal-dialog');
                return dialog.offsetWidth;
            }
        """)
        
        # Should be less than viewport width with some margin
        assert modal_width < 375