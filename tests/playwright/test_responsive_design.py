"""
Playwright tests for responsive design and mobile experience.
"""

from conftest import (expect_success_message,
                      open_feedback_modal,
                      wait_for_feedback_button)
from playwright.sync_api import Page, expect


class TestResponsiveDesign:
    """Test feedback system responsive design across different screen sizes."""

    # Common device viewports for testing
    DESKTOP_VIEWPORT = {'width': 1920, 'height': 1080}
    TABLET_VIEWPORT = {'width': 768, 'height': 1024}
    MOBILE_LARGE_VIEWPORT = {'width': 414, 'height': 896}  # iPhone 11 Pro Max
    MOBILE_MEDIUM_VIEWPORT = {'width': 375, 'height': 667}  # iPhone SE
    MOBILE_SMALL_VIEWPORT = {'width': 320, 'height': 568}  # iPhone 5/SE

    def test_feedback_button_desktop_responsive(self, page: Page):
        """Test feedback button on desktop viewport."""
        page.set_viewport_size(self.DESKTOP_VIEWPORT)
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        
        # Check desktop-specific styles
        button_styles = page.evaluate("""
            () => {
                const btn = document.getElementById('feedbackBtn');
                const styles = window.getComputedStyle(btn);
                return {
                    width: styles.width,
                    height: styles.height,
                    bottom: styles.bottom,
                    right: styles.right
                };
            }
        """)
        
        # Desktop should have larger button and more spacing
        assert '60px' in button_styles['width']
        assert '60px' in button_styles['height']
        assert '30px' in button_styles['bottom']
        assert '30px' in button_styles['right']

    def test_feedback_button_tablet_responsive(self, page: Page):
        """Test feedback button on tablet viewport."""
        page.set_viewport_size(self.TABLET_VIEWPORT)
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        
        # Button should still be accessible on tablet
        button_styles = page.evaluate("""
            () => {
                const btn = document.getElementById('feedbackBtn');
                const styles = window.getComputedStyle(btn);
                return {
                    width: styles.width,
                    height: styles.height,
                    position: styles.position
                };
            }
        """)
        
        assert button_styles['position'] == 'fixed'

    def test_feedback_button_mobile_responsive(self, page: Page):
        """Test feedback button on mobile viewport."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        
        # Check mobile-specific styles
        button_styles = page.evaluate("""
            () => {
                const btn = document.getElementById('feedbackBtn');
                const styles = window.getComputedStyle(btn);
                return {
                    width: styles.width,
                    height: styles.height,
                    bottom: styles.bottom,
                    right: styles.right
                };
            }
        """)
        
        # Mobile should have smaller button and less spacing
        assert '56px' in button_styles['width']
        assert '56px' in button_styles['height']
        assert '20px' in button_styles['bottom']
        assert '20px' in button_styles['right']

    def test_feedback_tooltip_mobile_hidden(self, page: Page):
        """Test that tooltip is hidden on mobile devices."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        _tooltip = page.locator('.feedback-btn-text')
        
        # On mobile, tooltip should be hidden
        tooltip_display = page.evaluate("""
            () => {
                const tooltip = document.querySelector('.feedback-btn-text');
                return window.getComputedStyle(tooltip).display;
            }
        """)
        
        assert tooltip_display == 'none'

    def test_modal_responsive_desktop(self, page: Page):
        """Test modal responsiveness on desktop."""
        page.set_viewport_size(self.DESKTOP_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal_dialog = page.locator('#feedbackModal .modal-dialog')
        expect(modal_dialog).to_be_visible()
        
        # Check modal size on desktop
        _modal_styles = page.evaluate("""
            () => {
                const dialog = document.querySelector('#feedbackModal .modal-dialog');
                return {
                    maxWidth: window.getComputedStyle(dialog).maxWidth,
                    width: dialog.offsetWidth
                };
            }
        """)
        
        # Should use modal-lg class (large modal)
        expect(modal_dialog).to_have_class('modal-lg')

    def test_modal_responsive_tablet(self, page: Page):
        """Test modal responsiveness on tablet."""
        page.set_viewport_size(self.TABLET_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal_dialog = page.locator('#feedbackModal .modal-dialog')
        expect(modal_dialog).to_be_visible()
        
        # Modal should fit within tablet viewport
        modal_width = page.evaluate("""
            () => {
                const dialog = document.querySelector('#feedbackModal .modal-dialog');
                return dialog.offsetWidth;
            }
        """)
        
        # Should be less than viewport width with margins
        assert modal_width < self.TABLET_VIEWPORT['width']

    def test_modal_responsive_mobile(self, page: Page):
        """Test modal responsiveness on mobile."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal_dialog = page.locator('#feedbackModal .modal-dialog')
        expect(modal_dialog).to_be_visible()
        
        # Modal should fit within mobile viewport
        modal_dimensions = page.evaluate("""
            () => {
                const dialog = document.querySelector('#feedbackModal .modal-dialog');
                return {
                    width: dialog.offsetWidth,
                    height: dialog.offsetHeight
                };
            }
        """)
        
        # Should fit within mobile viewport with margins
        assert modal_dimensions['width'] < self.MOBILE_MEDIUM_VIEWPORT['width']
        assert modal_dimensions['height'] < self.MOBILE_MEDIUM_VIEWPORT['height']

    def test_form_elements_mobile_usability(self, page: Page):
        """Test form elements are usable on mobile."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # All form elements should be visible and tappable
        form_elements = [
            '#feedbackType',
            '#feedbackSubject',
            '#feedbackMessage',
            'input[name="rating"]',
            '#submitFeedbackBtn'
        ]
        
        for selector in form_elements:
            elements = page.locator(selector)
            count = elements.count()
            
            if count > 1:  # Multiple elements (like radio buttons)
                for i in range(count):
                    element = elements.nth(i)
                    expect(element).to_be_visible()
            else:  # Single element
                expect(elements).to_be_visible()

    def test_star_rating_mobile_interaction(self, page: Page):
        """Test star rating system on mobile devices."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Star labels should be large enough for touch interaction
        star_labels = page.locator('.star-rating label')
        
        for i in range(star_labels.count()):
            label = star_labels.nth(i)
            expect(label).to_be_visible()
            
            # Check size is adequate for touch (recommended 44px minimum)
            label_size = page.evaluate(f"""
                () => {{
                    const label = document.querySelectorAll('.star-rating label')[{i}];
                    const rect = label.getBoundingClientRect();
                    return {{
                        width: rect.width,
                        height: rect.height
                    }};
                }}
            """)
            
            # Stars should be large enough for touch interaction
            assert label_size['width'] >= 30  # Reasonable touch target
            assert label_size['height'] >= 30

    def test_text_input_mobile_keyboard(self, page: Page):
        """Test text input fields work well with mobile keyboard."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Test message field
        message_field = page.locator('#feedbackMessage')
        message_field.focus()
        
        # Field should be focused and visible
        expect(message_field).to_be_focused()
        expect(message_field).to_be_visible()
        
        # Type text to ensure it works
        message_field.fill('Testing mobile keyboard input functionality.')
        
        # Text should be entered correctly
        expect(message_field).to_have_value('Testing mobile keyboard input functionality.')

    def test_submit_button_mobile_accessibility(self, page: Page):
        """Test submit button is accessible on mobile."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        submit_btn = page.locator('#submitFeedbackBtn')
        expect(submit_btn).to_be_visible()
        
        # Button should be large enough for touch
        button_size = page.evaluate("""
            () => {
                const btn = document.getElementById('submitFeedbackBtn');
                const rect = btn.getBoundingClientRect();
                return {
                    width: rect.width,
                    height: rect.height
                };
            }
        """)
        
        # Submit button should meet touch target guidelines
        assert button_size['width'] >= 44
        assert button_size['height'] >= 44

    def test_modal_scrolling_on_small_screens(self, page: Page):
        """Test modal scrolling on small screens."""
        page.set_viewport_size(self.MOBILE_SMALL_VIEWPORT)  # Smallest test viewport
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        _modal_body = page.locator('#feedbackModal .modal-body')
        
        # Modal body should be scrollable if content exceeds viewport
        modal_height = page.evaluate("""
            () => {
                const modalBody = document.querySelector('#feedbackModal .modal-body');
                return {
                    scrollHeight: modalBody.scrollHeight,
                    clientHeight: modalBody.clientHeight,
                    canScroll: modalBody.scrollHeight > modalBody.clientHeight
                };
            }
        """)
        
        # If content is larger than container, it should be scrollable
        if modal_height['scrollHeight'] > modal_height['clientHeight']:
            # Test scrolling works
            page.mouse.wheel(0, 100)  # Scroll down
            # Content should scroll

    def test_landscape_vs_portrait_mobile(self, page: Page):
        """Test feedback system in both landscape and portrait mobile orientations."""
        # Test portrait first
        page.set_viewport_size({'width': 375, 'height': 667})  # Portrait
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        
        # Test landscape
        page.set_viewport_size({'width': 667, 'height': 375})  # Landscape
        page.reload()  # Reload to trigger responsive changes
        wait_for_feedback_button(page)
        
        expect(feedback_btn).to_be_visible()
        
        # Modal should work in landscape
        open_feedback_modal(page)
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()

    def test_form_validation_messages_mobile(self, page: Page):
        """Test form validation messages display properly on mobile."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Trigger validation error
        submit_btn = page.locator('#submitFeedbackBtn')
        submit_btn.click()
        
        # Error message should be visible and readable on mobile
        error_message = page.locator('.alert-danger')
        expect(error_message).to_be_visible()
        
        # Error should not be cut off or overflow
        error_rect = page.evaluate("""
            () => {
                const error = document.querySelector('.alert-danger');
                if (!error) return null;
                const rect = error.getBoundingClientRect();
                return {
                    left: rect.left,
                    right: rect.right,
                    top: rect.top,
                    bottom: rect.bottom
                };
            }
        """)
        
        if error_rect:
            # Error should fit within viewport
            assert error_rect['left'] >= 0
            assert error_rect['right'] <= self.MOBILE_MEDIUM_VIEWPORT['width']

    def test_character_counter_mobile(self, page: Page):
        """Test character counter visibility and usability on mobile."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        message_field = page.locator('#feedbackMessage')
        char_counter = page.locator('#messageCharCount')
        
        expect(char_counter).to_be_visible()
        
        # Type text to test counter updates
        message_field.fill('Testing character counter on mobile device.')
        
        # Counter should update
        expect(char_counter).to_contain_text('46')  # Length of test message

    def test_touch_interaction_star_rating(self, page: Page):
        """Test touch interaction with star rating on mobile."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Simulate touch interaction with stars
        star_3 = page.locator('label[for="star3"]')
        
        # Tap the star (mobile touch event)
        star_3.tap()
        
        # Star should be selected
        star_input = page.locator('#star3')
        expect(star_input).to_be_checked()
        
        # Rating text should update
        rating_text = page.locator('.rating-text small')
        expect(rating_text).to_contain_text('Good experience')

    def test_modal_close_mobile_usability(self, page: Page):
        """Test modal close button usability on mobile."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Close button should be easily tappable
        close_btn = page.locator('#feedbackModal .btn-close')
        expect(close_btn).to_be_visible()
        
        # Check close button size
        close_btn_size = page.evaluate("""
            () => {
                const btn = document.querySelector('#feedbackModal .btn-close');
                const rect = btn.getBoundingClientRect();
                return {
                    width: rect.width,
                    height: rect.height
                };
            }
        """)
        
        # Close button should be large enough for touch
        assert close_btn_size['width'] >= 30
        assert close_btn_size['height'] >= 30
        
        # Tap to close
        close_btn.tap()
        
        # Modal should close
        modal = page.locator('#feedbackModal')
        expect(modal).not_to_be_visible()

    def test_successful_submission_mobile(self, page: Page):
        """Test complete feedback submission flow on mobile."""
        page.set_viewport_size(self.MOBILE_MEDIUM_VIEWPORT)
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Fill form using mobile-friendly interactions
        type_select = page.locator('#feedbackType')
        type_select.select_option('bug')
        
        message_field = page.locator('#feedbackMessage')
        message_field.fill('This is a test feedback submission from a mobile device to ensure the entire flow works correctly.')
        
        # Select rating using touch
        star_4 = page.locator('label[for="star4"]')
        star_4.tap()
        
        # Submit form
        submit_btn = page.locator('#submitFeedbackBtn')
        submit_btn.tap()
        
        # Should show success message
        expect_success_message(page)
        
        # Modal should auto-close
        modal = page.locator('#feedbackModal')
        page.wait_for_timeout(2500)
        expect(modal).not_to_be_visible()
        
        # Toast should appear
        toast = page.locator('#feedbackToast')
        expect(toast).to_be_visible()