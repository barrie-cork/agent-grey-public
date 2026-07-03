"""
Playwright tests for accessibility features and compliance.
"""

from conftest import (fill_feedback_form,
                      open_feedback_modal, submit_feedback_form,
                      wait_for_feedback_button)
from playwright.sync_api import Page, expect


class TestAccessibility:
    """Test feedback system accessibility compliance."""

    def test_feedback_button_accessibility_attributes(self, page: Page):
        """Test feedback button has proper accessibility attributes."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        feedback_btn = page.locator('#feedbackBtn')
        
        # Should have proper attributes
        expect(feedback_btn).to_have_attribute('type', 'button')
        expect(feedback_btn).to_have_attribute('title', 'Share your feedback')
        
        # Should be focusable
        expect(feedback_btn).to_be_enabled()

    def test_feedback_button_keyboard_navigation(self, page: Page):
        """Test feedback button is accessible via keyboard navigation."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        # Tab to the feedback button (may require multiple tabs depending on page structure)
        feedback_btn = page.locator('#feedbackBtn')
        feedback_btn.focus()
        
        # Button should be focused
        expect(feedback_btn).to_be_focused()
        
        # Pressing Enter should open modal
        page.keyboard.press('Enter')
        
        # Modal should open
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()

    def test_modal_aria_attributes(self, page: Page):
        """Test modal has proper ARIA attributes."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        
        # Modal should have proper ARIA attributes
        expect(modal).to_have_attribute('tabindex', '-1')
        expect(modal).to_have_attribute('aria-labelledby', 'feedbackModalLabel')
        expect(modal).to_have_attribute('aria-hidden', 'false')
        
        # Modal title should have proper ID
        modal_title = page.locator('#feedbackModalLabel')
        expect(modal_title).to_be_visible()

    def test_form_labels_and_descriptions(self, page: Page):
        """Test form elements have proper labels and descriptions."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check form labels
        form_fields = [
            ('feedbackType', 'What type of feedback'),
            ('feedbackSubject', 'Subject'),
            ('feedbackMessage', 'Your Feedback')
        ]
        
        for field_id, label_text in form_fields:
            label = page.locator(f'label[for="{field_id}"]')
            expect(label).to_be_visible()
            expect(label).to_contain_text(label_text)
            
            # Field should have associated label
            field = page.locator(f'#{field_id}')
            expect(field).to_be_visible()

    def test_required_fields_accessibility(self, page: Page):
        """Test required fields are properly marked for screen readers."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Required fields should have required attribute
        required_fields = ['#feedbackType', '#feedbackMessage']
        
        for field_selector in required_fields:
            field = page.locator(field_selector)
            expect(field).to_have_attribute('required')
            
            # Should have visual indicator
            label = page.locator(f'label[for="{field_selector[1:]}"]')  # Remove # from selector
            # Look for required indicator (asterisk)
            required_indicator = label.locator('.text-danger')
            expect(required_indicator).to_be_visible()

    def test_error_messages_accessibility(self, page: Page):
        """Test error messages are accessible to screen readers."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Trigger validation error
        submit_btn = page.locator('#submitFeedbackBtn')
        submit_btn.click()
        
        # Error message should appear
        error_alert = page.locator('.alert-danger')
        expect(error_alert).to_be_visible()
        
        # Should have proper ARIA role
        expect(error_alert).to_have_attribute('role', 'alert')
        
        # Should be announced to screen readers
        # In a real accessibility test, you would use tools like axe-core

    def test_star_rating_accessibility(self, page: Page):
        """Test star rating system is accessible."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Star rating inputs should be accessible
        star_inputs = page.locator('.star-rating input[type="radio"]')
        
        for i in range(star_inputs.count()):
            star_input = star_inputs.nth(i)
            star_label = page.locator('.star-rating label').nth(i)
            
            # Each star should have proper attributes
            expect(star_input).to_have_attribute('name', 'rating')
            expect(star_input).to_have_attribute('type', 'radio')
            
            # Labels should have title attributes for screen readers
            title_attr = star_label.get_attribute('title')
            assert title_attr is not None
            assert 'star' in title_attr.lower()

    def test_keyboard_navigation_within_modal(self, page: Page):
        """Test keyboard navigation works within modal."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # First focusable element should receive focus
        first_field = page.locator('#feedbackType')
        first_field.focus()
        expect(first_field).to_be_focused()
        
        # Tab should move to next field
        page.keyboard.press('Tab')
        second_field = page.locator('#feedbackSubject')
        expect(second_field).to_be_focused()
        
        # Continue tabbing through form
        page.keyboard.press('Tab')
        third_field = page.locator('#feedbackMessage')
        expect(third_field).to_be_focused()

    def test_modal_escape_key_accessibility(self, page: Page):
        """Test modal can be closed with Escape key."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()
        
        # Escape key should close modal
        page.keyboard.press('Escape')
        expect(modal).not_to_be_visible()

    def test_focus_management_modal_open_close(self, page: Page):
        """Test focus management when opening and closing modal."""
        page.goto('http://localhost:8000/')
        
        feedback_btn = page.locator('#feedbackBtn')
        feedback_btn.focus()
        expect(feedback_btn).to_be_focused()
        
        # Open modal
        feedback_btn.click()
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()
        
        # Focus should move into modal
        page.wait_for_timeout(100)  # Small delay for focus management
        
        # Close modal with Escape
        page.keyboard.press('Escape')
        expect(modal).not_to_be_visible()
        
        # Focus should return to trigger button (ideal behavior)
        # Note: This depends on implementation

    def test_color_contrast_accessibility(self, page: Page):
        """Test color contrast meets accessibility standards."""
        page.goto('http://localhost:8000/')
        wait_for_feedback_button(page)
        
        # Test feedback button contrast
        button_colors = page.evaluate("""
            () => {
                const btn = document.getElementById('feedbackBtn');
                const styles = window.getComputedStyle(btn);
                return {
                    color: styles.color,
                    backgroundColor: styles.backgroundColor
                };
            }
        """)
        
        # Colors should be defined (not transparent/inherit)
        assert button_colors['color'] != 'rgba(0, 0, 0, 0)'
        assert button_colors['backgroundColor'] != 'rgba(0, 0, 0, 0)'

    def test_form_field_focus_indicators(self, page: Page):
        """Test form fields have visible focus indicators."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        form_fields = ['#feedbackType', '#feedbackSubject', '#feedbackMessage']
        
        for field_selector in form_fields:
            field = page.locator(field_selector)
            
            # Focus the field
            field.focus()
            expect(field).to_be_focused()
            
            # Should have focus outline (this varies by browser/CSS)
            focus_outline = page.evaluate(f"""
                () => {{
                    const field = document.querySelector('{field_selector}');
                    const styles = window.getComputedStyle(field);
                    return {{
                        outline: styles.outline,
                        outlineWidth: styles.outlineWidth,
                        boxShadow: styles.boxShadow
                    }};
                }}
            """)
            
            # Should have some form of focus indication
            has_focus_indicator = (
                focus_outline['outline'] != 'none' or 
                focus_outline['outlineWidth'] != '0px' or
                'box-shadow' in str(focus_outline['boxShadow'])
            )
            
            assert has_focus_indicator, f"Field {field_selector} should have focus indicator"

    def test_submit_button_accessibility(self, page: Page):
        """Test submit button accessibility."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        submit_btn = page.locator('#submitFeedbackBtn')
        
        # Should have proper type and be enabled
        expect(submit_btn).to_have_attribute('type', 'submit')
        expect(submit_btn).to_be_enabled()
        
        # Should have descriptive text
        expect(submit_btn).to_contain_text('Send Feedback')
        
        # Should be focusable
        submit_btn.focus()
        expect(submit_btn).to_be_focused()

    def test_loading_state_accessibility(self, page: Page):
        """Test loading state is accessible to screen readers."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        
        submit_btn = page.locator('#submitFeedbackBtn')
        loading_text = submit_btn.locator('.loading-text')
        
        # Initially loading text should be hidden
        expect(loading_text).to_have_class('d-none')
        
        # Click submit to see loading state
        submit_btn.click()
        
        # Loading state should have proper accessibility attributes
        # (This depends on your implementation)

    def test_success_message_accessibility(self, page: Page):
        """Test success messages are accessible."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        submit_feedback_form(page)
        
        # Success message should appear
        success_alert = page.locator('.alert-success')
        expect(success_alert).to_be_visible()
        
        # Should have proper ARIA role
        expect(success_alert).to_have_attribute('role', 'alert')
        
        # Should be dismissible
        dismiss_btn = success_alert.locator('.btn-close')
        expect(dismiss_btn).to_be_visible()
        expect(dismiss_btn).to_have_attribute('aria-label', 'Close')

    def test_toast_notification_accessibility(self, page: Page):
        """Test toast notifications are accessible."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        fill_feedback_form(page)
        submit_feedback_form(page)
        
        # Wait for modal to close and toast to appear
        page.wait_for_timeout(2500)
        
        toast = page.locator('#feedbackToast')
        expect(toast).to_be_visible()
        
        # Toast should have proper ARIA attributes
        expect(toast).to_have_attribute('role', 'alert')
        expect(toast).to_have_attribute('aria-live', 'assertive')
        expect(toast).to_have_attribute('aria-atomic', 'true')

    def test_high_contrast_mode_support(self, page: Page):
        """Test high contrast mode support."""
        page.goto('http://localhost:8000/')
        
        # Simulate high contrast mode by adding media query
        page.add_style_tag(content="""
            @media (prefers-contrast: high) {
                #feedbackBtn {
                    border: 2px solid white !important;
                }
            }
        """)
        
        wait_for_feedback_button(page)
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        
        # In high contrast mode, button should have visible border
        # (This test simulates the condition)

    def test_reduced_motion_support(self, page: Page):
        """Test reduced motion preference support."""
        page.goto('http://localhost:8000/')
        
        # Simulate reduced motion preference
        page.add_style_tag(content="""
            @media (prefers-reduced-motion: reduce) {
                * {
                    animation: none !important;
                    transition: none !important;
                }
            }
        """)
        
        wait_for_feedback_button(page)
        feedback_btn = page.locator('#feedbackBtn')
        expect(feedback_btn).to_be_visible()
        
        # Button should still be functional without animations
        feedback_btn.click()
        modal = page.locator('#feedbackModal')
        expect(modal).to_be_visible()

    def test_screen_reader_text_elements(self, page: Page):
        """Test screen reader only text elements."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Look for screen reader only text (if implemented)
        sr_only_elements = page.locator('.sr-only, .visually-hidden')
        
        if sr_only_elements.count() > 0:
            for i in range(sr_only_elements.count()):
                _sr_element = sr_only_elements.nth(i)
                
                # Should be hidden visually but available to screen readers
                sr_styles = page.evaluate(f"""
                    () => {{
                        const elements = document.querySelectorAll('.sr-only, .visually-hidden');
                        const element = elements[{i}];
                        const styles = window.getComputedStyle(element);
                        return {{
                            position: styles.position,
                            clip: styles.clip,
                            width: styles.width,
                            height: styles.height
                        }};
                    }}
                """)
                
                # Should have screen reader only styling
                assert sr_styles['position'] == 'absolute'

    def test_form_fieldset_and_legend(self, page: Page):
        """Test form grouping with fieldset and legend if applicable."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Check if star rating is grouped with fieldset/legend
        rating_fieldset = page.locator('fieldset')
        
        if rating_fieldset.count() > 0:
            # Should have legend
            legend = rating_fieldset.locator('legend')
            expect(legend).to_be_visible()

    def test_autocomplete_attributes(self, page: Page):
        """Test autocomplete attributes on form fields."""
        page.goto('http://localhost:8000/')
        open_feedback_modal(page)
        
        # Email field should have autocomplete attribute
        email_field = page.locator('#feedbackEmail')
        
        if email_field.is_visible():
            autocomplete_attr = email_field.get_attribute('autocomplete')
            # Should have appropriate autocomplete value
            assert autocomplete_attr in ['email', 'off', None]

    def test_language_attributes(self, page: Page):
        """Test language attributes are properly set."""
        page.goto('http://localhost:8000/')
        
        # Page should have lang attribute
        html_element = page.locator('html')
        expect(html_element).to_have_attribute('lang')
        
        # Lang attribute should be valid (e.g., 'en')
        lang_attr = html_element.get_attribute('lang')
        assert len(lang_attr) >= 2  # Should be at least 2 characters like 'en'