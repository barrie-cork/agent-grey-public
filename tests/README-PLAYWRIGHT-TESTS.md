# Playwright Tests for Feedback System

This directory contains comprehensive Playwright tests for the Agent Grey feedback system, ensuring the UI and UX work as expected across different browsers, devices, and user scenarios.

## 🚀 Quick Start

### Prerequisites
- Node.js 16+ installed
- Python Django development environment running
- Agent Grey application accessible at `http://localhost:8000`

### Installation
```bash
# Install Playwright and dependencies
npm install
npx playwright install
npx playwright install-deps
```

### Running Tests
```bash
# Run all tests
npm test

# Run tests with browser visible
npm run test:headed

# Run tests with interactive UI
npm run test:ui

# Debug tests step by step
npm run test:debug
```

## 📁 Test Structure

### Test Files
- **`test_feedback_button.py`** - Floating button visibility, styling, and interactions
- **`test_feedback_modal.py`** - Modal opening, form elements, and structure
- **`test_form_validation.py`** - Client and server-side validation testing
- **`test_feedback_submission.py`** - Complete submission workflows
- **`test_user_experiences.py`** - Anonymous vs authenticated user testing
- **`test_responsive_design.py`** - Multi-device and responsive testing
- **`test_accessibility.py`** - WCAG compliance and accessibility testing

### Configuration Files
- **`playwright.config.js`** - Main test configuration with multiple projects
- **`conftest.py`** - Pytest fixtures and helper functions
- **`global-setup.js`** - Database setup and test data preparation
- **`global-teardown.js`** - Cleanup after test completion

## 🎯 Test Coverage

### Functional Testing
- ✅ **Feedback Button**: Position, styling, hover effects, animations
- ✅ **Modal Functionality**: Opening, closing, form structure
- ✅ **Form Validation**: Required fields, length limits, spam protection
- ✅ **Submission Flow**: AJAX requests, success/error handling
- ✅ **User Context**: Anonymous vs authenticated experiences
- ✅ **Page Context**: URL and title capture

### Cross-Browser Testing
- ✅ **Chromium** (Chrome/Edge)
- ✅ **Firefox**
- ✅ **WebKit** (Safari)

### Device Testing
- ✅ **Desktop** (1920x1080)
- ✅ **Tablet** (iPad Pro)
- ✅ **Mobile** (iPhone 12, Pixel 5)
- ✅ **Small Mobile** (iPhone SE)

### Responsive Design
- ✅ **Button positioning** across screen sizes
- ✅ **Modal sizing** and layout adaptation
- ✅ **Touch targets** for mobile interaction
- ✅ **Keyboard navigation** and focus management

### Accessibility Testing
- ✅ **ARIA attributes** and semantic HTML
- ✅ **Keyboard navigation** throughout interface
- ✅ **Screen reader compatibility**
- ✅ **Focus management** and indicators
- ✅ **Color contrast** requirements
- ✅ **High contrast mode** support
- ✅ **Reduced motion** preferences

## 🔧 Test Commands

### Specific Test Categories
```bash
# Test individual components
npm run test:feedback-button    # Button functionality
npm run test:modal             # Modal behavior
npm run test:validation        # Form validation
npm run test:submission        # Submission flows
npm run test:user-experience   # User scenarios
npm run test:responsive        # Responsive design
npm run test:accessibility     # Accessibility compliance

# Test specific browsers
npm run test:chromium          # Chromium only
npm run test:firefox           # Firefox only
npm run test:webkit            # WebKit only

# Test specific devices
npm run test:desktop           # Desktop browsers
npm run test:mobile            # Mobile devices
npm run test:tablet            # Tablet devices
npm run test:all-devices       # Cross-device testing
```

### Development & Debugging
```bash
# Interactive debugging
npm run test:debug

# Run with visible browser
npm run test:headed

# Interactive test development
npm run test:ui

# View test reports
npm run report

# View execution traces
npm run trace
```

## 📊 Test Projects

The configuration includes multiple test projects for comprehensive coverage:

### Browser Projects
- **chromium-desktop**: Chrome/Edge desktop testing
- **firefox-desktop**: Firefox desktop testing  
- **webkit-desktop**: Safari desktop testing
- **mobile-chrome**: Android Chrome testing
- **mobile-safari**: iOS Safari testing
- **tablet**: iPad testing

### Specialized Projects
- **accessibility**: Focus on accessibility compliance
- **high-contrast**: High contrast mode testing
- **reduced-motion**: Reduced motion preference testing
- **responsive-***: Multiple viewport testing
- **performance**: Performance monitoring

## 🧪 Writing New Tests

### Test Structure Example
```python
def test_new_functionality(self, page: Page):
    \"\"\"Test description.\"\"\"
    page.goto('http://localhost:8000/')
    open_feedback_modal(page)
    
    # Test implementation
    expect(element).to_be_visible()
```

### Helper Functions
Use the provided helper functions in `conftest.py`:
- `wait_for_feedback_button(page)` - Wait for button to load
- `open_feedback_modal(page)` - Open the feedback modal
- `fill_feedback_form(page, **kwargs)` - Fill form with data
- `submit_feedback_form(page)` - Submit the form
- `expect_success_message(page)` - Verify success
- `expect_error_message(page)` - Verify errors

### Fixtures Available
- `page` - Standard Playwright page
- `authenticated_page` - Pre-authenticated user session
- `staff_page` - Staff user session
- `feedback_helpers` - Collection of helper functions

## 🔍 Test Results

### Reports
- **HTML Report**: Comprehensive visual report with screenshots
- **JSON Report**: Machine-readable test results
- **Traces**: Step-by-step execution recordings
- **Screenshots**: Failure documentation
- **Videos**: Test execution recordings

### Viewing Results
```bash
# Open HTML report
npm run report

# View execution traces
npm run trace test-results/trace.zip
```

## 🚨 Common Issues

### Server Not Starting
- Ensure Django server is running on port 8000
- Check `DJANGO_SETTINGS_MODULE=grey_lit_project.settings.test`
- Verify database migrations are applied

### Test Timeouts
- Increase timeout in `playwright.config.js`
- Check network connectivity
- Ensure server responds quickly

### Browser Installation
```bash
# Reinstall browsers
npx playwright install --force

# Install system dependencies
npx playwright install-deps
```

## 📈 CI/CD Integration

The tests are configured for continuous integration:
- **Parallel execution** for faster results
- **Retry logic** for flaky test handling
- **Screenshot/video capture** on failures
- **Multiple browser coverage** in single run
- **Detailed reporting** for debugging

### Environment Variables
- `CI=true` - Enables CI-specific configurations
- `DJANGO_SETTINGS_MODULE` - Test settings module

## 🎯 Best Practices

1. **Use Page Object Model** for complex interactions
2. **Wait for elements** explicitly rather than using timeouts
3. **Test user workflows** rather than individual functions
4. **Include accessibility testing** in all user-facing features
5. **Test across devices** for responsive behavior
6. **Capture meaningful errors** with screenshots and traces

## 🔒 Security Testing

The tests include security considerations:
- **CSRF token handling** in form submissions
- **Input sanitization** validation
- **Spam protection** verification
- **XSS prevention** testing

## 📚 Resources

- [Playwright Documentation](https://playwright.dev/)
- [Agent Grey Documentation](../CLAUDE.md)
- [Accessibility Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [Responsive Design Testing](https://web.dev/responsive-web-design-basics/)

---

**Note**: These tests ensure the feedback system provides an excellent user experience across all devices, browsers, and accessibility requirements.