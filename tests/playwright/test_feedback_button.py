"""
Playwright tests for feedback button visibility and interaction.
"""

from conftest import (open_feedback_modal,
                      wait_for_feedback_button)
from playwright.sync_api import Page, expect


class TestFeedbackButton:
    """Test the floating feedback button functionality."""

    def test_feedback_button_is_visible(self, page: Page):
        """Test that feedback button is visible on all pages."""
        # Test on home/dashboard page
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        expect(feedback_btn).to_have_attribute('title', 'Share your feedback')

    def test_feedback_button_styling(self, page: Page):
        """Test that feedback button has correct styling."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        
        # Check CSS classes and properties
        expect(feedback_btn).to_have_class('feedback-float-btn')
        
        # Check position (should be fixed)
        position = page.evaluate("""
            () => {
                const btn = document.getElementById('feedbackBtn');
                const styles = window.getComputedStyle(btn);
                return {
                    position: styles.position,
                    bottom: styles.bottom,
                    right: styles.right,
                    zIndex: styles.zIndex
                };
            }
        """)
        
        assert position['position'] == 'fixed'
        assert '30px' in position['bottom']
        assert '30px' in position['right']
        assert int(position['zIndex']) >= 1050

    def test_feedback_button_hover_effect(self, page: Page):
        """Test feedback button hover effects."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        tooltip = page.locator('.feedback-btn-text')
        
        # Initially tooltip should be hidden
        expect(tooltip).to_have_css('opacity', '0')
        
        # Hover over button
        feedback_btn.hover()
        
        # Tooltip should become visible
        expect(tooltip).to_have_css('opacity', '1')
        expect(tooltip).to_contain_text('Feedback')

    def test_feedback_button_click_opens_modal(self, page: Page):
        """Test that clicking feedback button opens the modal."""
        page.goto('http://localhost:8000/')
        
        # Modal should not be visible initially
        modal = page.locator('#feedbackModal')
        expect(modal).not_to_be_visible()
        
        # Click feedback button
        open_feedback_modal(page)
        
        # Modal should be visible
        expect(modal).to_be_visible()
        expect(modal).to_have_class('modal')
        expect(modal.locator('.modal-title')).to_contain_text('Share Your Feedback')

    def test_feedback_button_icon_and_text(self, page: Page):
        """Test that feedback button has correct icon and text."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        icon = feedback_btn.locator('i.bi-chat-dots')
        text = feedback_btn.locator('.feedback-btn-text')
        
        expect(icon).to_be_visible()
        expect(text).to_contain_text('Feedback')

    def test_feedback_button_keyboard_accessibility(self, page: Page):
        """Test that feedback button is accessible via keyboard."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        # Tab to the feedback button
        page.keyboard.press('Tab')
        
        # The button should be focused (this may need adjustment based on page structure)
        feedback_btn = page.locator('#feedbackBtn')
        
        # Press Enter to activate
        feedback_btn.focus()
        page.keyboard.press('Enter')
        
        # Modal should open
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()

    def test_feedback_button_on_different_pages(self, page: Page):
        """Test that feedback button appears on different pages."""
        pages_to_test = [
            'http://localhost:8000/',
            'http://localhost:8000/accounts/login/',
            # Add more pages as needed
        ]
        
        for url in pages_to_test:
            with page.context.new_page() as test_page:
                test_page.goto(url)
                wait_for_feedback_button(test_page)
                
                feedback_btn = test_page.locator('#feedbackBtn')
                expect(feedback_btn).to_be_visible()

    def test_feedback_button_animation(self, page: Page):
        """Test feedback button appears with animation."""
        page.goto('http://localhost:8000/')
        
        # Check that the button has animation CSS
        animation_info = page.evaluate("""
            () => {
                const btn = document.getElementById('feedbackBtn');
                const styles = window.getComputedStyle(btn);
                return {
                    animation: styles.animation,
                    animationName: styles.animationName
                };
            }
        """)
        
        # Should have feedbackBtnAppear animation
        assert 'feedbackBtnAppear' in animation_info.get('animationName', '')

    def test_feedback_button_z_index_above_content(self, page: Page):
        """Test that feedback button appears above other content."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        # Get z-index of feedback button
        feedback_z_index = page.evaluate("""
            () => {
                const btn = document.getElementById('feedbackBtn');
                return parseInt(window.getComputedStyle(btn).zIndex);
            }
        """)
        
        # Should be above most content (1050+)
        assert feedback_z_index >= 1050

    def test_feedback_button_mobile_responsive(self, page: Page):
        """Test feedback button responsive design on mobile."""
        # Set mobile viewport
        page.set_viewport_size({'width': 375, 'height': 667})  # iPhone SE size
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        
        # Check mobile-specific styles
        mobile_styles = page.evaluate("""
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
        
        # On mobile, button should be slightly smaller and closer to edges
        assert '56px' in mobile_styles['width'] or '60px' in mobile_styles['width']
        assert '20px' in mobile_styles['bottom'] or '30px' in mobile_styles['bottom']

    def test_feedback_button_tooltip_mobile_hidden(self, page: Page):
        """Test that tooltip is hidden on mobile devices."""
        # Set mobile viewport
        page.set_viewport_size({'width': 375, 'height': 667})
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        _tooltip = page.locator('.feedback-btn-text')
        
        # On mobile, tooltip should be hidden (display: none)
        tooltip_display = page.evaluate("""
            () => {
                const tooltip = document.querySelector('.feedback-btn-text');
                return window.getComputedStyle(tooltip).display;
            }
        """)
        
        assert tooltip_display == 'none'

    def test_feedback_button_not_in_print_mode(self, page: Page):
        """Test that feedback button is hidden in print mode."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        # Emulate print media
        page.emulate_media(media='print')
        
        _feedback_btn = page.locator('#feedbackBtn')
        
        # Button should be hidden in print mode
        print_display = page.evaluate("""
            () => {
                const btn = document.getElementById('feedbackBtn');
                return window.getComputedStyle(btn).display;
            }
        """)
        
        assert print_display == 'none'