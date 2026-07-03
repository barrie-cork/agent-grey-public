import { test, expect } from '@playwright/test';
import { loginAsReviewer, testUsers } from './fixtures/auth';
import { navigateToSPARoute, waitForVueSPA, waitForVueComponent, verifyOrganisationLoaded } from './fixtures/vue-helpers';

/**
 * Basic SPA Functionality Tests
 *
 * These tests verify the basic Vue SPA setup is working correctly:
 * - Login flow
 * - SPA initialization
 * - Organisation context loading
 * - Basic navigation
 */

test.describe('Vue SPA Basic Functionality', () => {
  test('Test 1: Login and SPA initialization', async ({ page }) => {
    // Login
    await page.goto('/accounts/login/');
    await page.fill('[data-testid="email"]', testUsers.reviewer1.email);
    await page.fill('[data-testid="password"]', testUsers.reviewer1.password);
    await page.click('[data-testid="login-btn"]');

    // Wait for redirect to dashboard
    await page.waitForURL('/', { timeout: 10000 });
    await page.waitForSelector('h1', { timeout: 5000 });

    // Verify we're logged in
    expect(page.url()).toBe('http://localhost:8000/');
  });

  test('Test 2: Navigate to screening SPA', async ({ page }) => {
    // Login
    await page.goto('/accounts/login/');
    await page.fill('[data-testid="email"]', testUsers.reviewer1.email);
    await page.fill('[data-testid="password"]', testUsers.reviewer1.password);
    await page.click('[data-testid="login-btn"]');

    // Wait for redirect
    await page.waitForURL('/', { timeout: 10000 });

    // Navigate to screening SPA
    await page.goto('/screening/');

    // Wait for Vue SPA to load
    await waitForVueSPA(page, 15000);

    // Check we're still at screening (not redirected to logout)
    const currentUrl = page.url();
    console.log('Current URL after navigation:', currentUrl);

    expect(currentUrl).toContain('/screening');
    expect(currentUrl).not.toContain('/logout');
    expect(currentUrl).not.toContain('/login');
  });

  test('Test 3: Use loginAsReviewer helper', async ({ page }) => {
    // Use the helper function
    await loginAsReviewer(page, testUsers.reviewer1.email, testUsers.reviewer1.password);

    // Check we ended up at screening
    const currentUrl = page.url();
    console.log('URL after loginAsReviewer:', currentUrl);

    expect(currentUrl).toContain('/screening');
    expect(currentUrl).not.toContain('/logout');
  });

  test('Test 4: Navigate to a specific SPA route', async ({ page }) => {
    // Enable comprehensive console logging
    page.on('console', msg => {
      const type = msg.type();
      const text = msg.text();
      if (type === 'error' || type === 'warning' || text.includes('[WorkQueue]') || text.includes('[Organisation]')) {
        console.log(`BROWSER [${type}]:`, text);
      }
    });

    page.on('pageerror', error => {
      console.error('PAGE ERROR:', error.message);
      console.error('Stack:', error.stack);
    });

    // Login
    await loginAsReviewer(page, testUsers.reviewer1.email, testUsers.reviewer1.password);

    // Verify organisation context before navigating
    console.log('\n=== Verifying organisation context ===');
    try {
      await verifyOrganisationLoaded(page);
      console.log('✅ Organisation context verified');
    } catch (error) {
      console.error('❌ Organisation verification failed:', error);
      throw error;
    }

    // Log current state before navigation
    const preNavState = await page.evaluate(() => ({
      url: window.location.href,
      localStorage: {
        keys: Object.keys(localStorage),
        orgData: localStorage.getItem('currentOrganisation')
      },
      appMounted: !!document.querySelector('#app > *'),
      appChildren: document.querySelector('#app')?.childNodes.length || 0
    }));
    console.log('\n=== Pre-navigation state ===');
    console.log(JSON.stringify(preNavState, null, 2));

    // Try to navigate to work queue
    console.log('\n=== Navigating to /work-queue ===');
    await navigateToSPARoute(page, '/work-queue');

    // Log post-navigation state
    const postNavState = await page.evaluate(() => ({
      url: window.location.href,
      appChildren: document.querySelector('#app')?.childNodes.length || 0,
      workQueueExists: !!document.querySelector('[data-testid="work-queue"]'),
      visibleElements: Array.from(document.querySelectorAll('[data-testid]')).map(el => el.getAttribute('data-testid'))
    }));
    console.log('\n=== Post-navigation state ===');
    console.log(JSON.stringify(postNavState, null, 2));

    // Wait for component with enhanced error handling
    console.log('\n=== Waiting for WorkQueue component ===');
    try {
      await waitForVueComponent(page, '[data-testid="work-queue"]', 15000);
      console.log('✅ WorkQueue component found');
    } catch (error) {
      // Capture detailed state on failure
      console.error('\n❌ Component not found. Capturing debug state...');

      const debugState = await page.evaluate(() => {
        const app = document.querySelector('#app');
        return {
          appHTML: app?.innerHTML.substring(0, 1000) || 'No #app element',
          appOuterHTML: app?.outerHTML.substring(0, 500) || 'No #app element',
          bodyClasses: document.body.className,
          allTestIds: Array.from(document.querySelectorAll('[data-testid]')).map(el => ({
            testid: el.getAttribute('data-testid'),
            visible: (el as HTMLElement).offsetParent !== null
          })),
          localStorage: {
            currentOrganisation: localStorage.getItem('currentOrganisation'),
            authToken: localStorage.getItem('authToken') ? '[PRESENT]' : '[MISSING]'
          },
          vueErrors: (window as any).__vueErrors || []
        };
      });

      console.error('Debug state:', JSON.stringify(debugState, null, 2));

      // Take screenshot for debugging
      await page.screenshot({
        path: `test-results/test-4-failure-${Date.now()}.png`,
        fullPage: true
      });
      console.error('Screenshot saved to test-results/');

      throw error;
    }

    // Verify URL
    expect(page.url()).toContain('/screening/work-queue');
    console.log('\n✅ Test 4 passed!');
  });
});
