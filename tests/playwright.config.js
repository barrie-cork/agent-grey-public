/**
 * Playwright Configuration for Feedback System Testing
 * 
 * This configuration sets up comprehensive testing for the feedback system
 * across multiple browsers, devices, and scenarios.
 */

const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  // Test directory
  testDir: './tests/playwright',
  
  // Timeout settings
  timeout: 30 * 1000, // 30 seconds per test
  expect: {
    timeout: 10 * 1000 // 10 seconds for assertions
  },
  
  // Global test configuration
  fullyParallel: true, // Run tests in parallel
  forbidOnly: !!process.env.CI, // Fail CI if test.only is used
  retries: process.env.CI ? 2 : 0, // Retry failed tests in CI
  workers: process.env.CI ? 1 : undefined, // Limit workers in CI
  
  // Test reporting
  reporter: [
    ['html'], // HTML report
    ['json', { outputFile: 'test-results/results.json' }],
    process.env.CI ? ['github'] : ['list']
  ],
  
  // Global test setup
  use: {
    // Base URL for tests
    baseURL: 'http://localhost:8000',
    
    // Capture traces on failure
    trace: 'on-first-retry',
    
    // Capture screenshots on failure
    screenshot: 'only-on-failure',
    
    // Capture videos on failure
    video: 'retain-on-failure',
    
    // Navigation timeout
    navigationTimeout: 15 * 1000,
    
    // Action timeout
    actionTimeout: 10 * 1000,
  },

  // Test projects for different scenarios
  projects: [
    // Setup project for authentication
    {
      name: 'setup',
      testMatch: /.*\.setup\.js/,
    },
    
    // Desktop browsers
    {
      name: 'chromium-desktop',
      use: { 
        ...devices['Desktop Chrome'],
        viewport: { width: 1920, height: 1080 }
      },
    },
    {
      name: 'firefox-desktop',
      use: { 
        ...devices['Desktop Firefox'],
        viewport: { width: 1920, height: 1080 }
      },
    },
    {
      name: 'webkit-desktop',
      use: { 
        ...devices['Desktop Safari'],
        viewport: { width: 1920, height: 1080 }
      },
    },
    
    // Mobile devices
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 12'] },
    },
    
    // Tablet
    {
      name: 'tablet',
      use: { ...devices['iPad Pro'] },
    },
    
    // Accessibility testing project
    {
      name: 'accessibility',
      use: { 
        ...devices['Desktop Chrome'],
        // Enable additional accessibility features
        colorScheme: 'light',
      },
      testMatch: '**/test_accessibility.py',
    },
    
    // High contrast mode testing
    {
      name: 'high-contrast',
      use: {
        ...devices['Desktop Chrome'],
        colorScheme: 'dark',
        // Simulate high contrast mode
        extraHTTPHeaders: {
          'prefers-contrast': 'high'
        }
      },
      testMatch: '**/test_accessibility.py',
    },
    
    // Reduced motion testing
    {
      name: 'reduced-motion',
      use: {
        ...devices['Desktop Chrome'],
        // Simulate reduced motion preference
        extraHTTPHeaders: {
          'prefers-reduced-motion': 'reduce'
        }
      },
    },
    
    // Responsive design testing
    {
      name: 'responsive-small',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 320, height: 568 } // iPhone 5/SE
      },
      testMatch: '**/test_responsive_design.py',
    },
    {
      name: 'responsive-medium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 375, height: 667 } // iPhone 6/7/8
      },
      testMatch: '**/test_responsive_design.py',
    },
    {
      name: 'responsive-large',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 414, height: 896 } // iPhone 11 Pro Max
      },
      testMatch: '**/test_responsive_design.py',
    },
    
    // Performance testing
    {
      name: 'performance',
      use: {
        ...devices['Desktop Chrome'],
        // Enable performance metrics
        launchOptions: {
          args: ['--enable-precise-memory-info']
        }
      },
      testMatch: '**/test_feedback_submission.py',
    }
  ],

  // Web server configuration
  webServer: {
    command: 'python manage.py runserver 8000',
    url: 'http://localhost:8000',
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000, // 2 minutes to start
    env: {
      DJANGO_SETTINGS_MODULE: 'grey_lit_project.settings.test'
    }
  },
  
  // Global setup and teardown
  globalSetup: require.resolve('./tests/playwright/global-setup.js'),
  globalTeardown: require.resolve('./tests/playwright/global-teardown.js'),
  
  // Test output directory
  outputDir: 'test-results/',
  
  // Test metadata
  metadata: {
    'test-type': 'e2e-feedback-system',
    'component': 'feedback-button-modal',
    'version': '1.0.0'
  }
});