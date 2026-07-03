import { test, expect } from '@playwright/test';
import { testUsers } from './fixtures/auth';

/**
 * Debug test to see what's actually on the /screening/ page
 */

test('Debug: Check /screening/ page content', async ({ page }) => {
  // Login
  await page.goto('/accounts/login/');
  await page.fill('[data-testid="email"]', testUsers.reviewer1.email);
  await page.fill('[data-testid="password"]', testUsers.reviewer1.password);
  await page.click('[data-testid="login-btn"]');

  // Wait for redirect
  await page.waitForURL('/', { timeout: 10000 });

  // Navigate to screening
  await page.goto('/screening/');
  await page.waitForTimeout(3000);

  // Get current URL
  const url = page.url();
  console.log('Current URL:', url);

  // Get page title
  const title = await page.title();
  console.log('Page title:', title);

  // Get page HTML
  const html = await page.content();
  console.log('Page HTML length:', html.length);
  console.log('HTML contains #app:', html.includes('id="app"'));
  console.log('HTML contains "screening":', html.includes('screening'));

  // Check for specific elements
  const appElement = await page.$('#app');
  console.log('#app element exists:', appElement !== null);

  // Get body text
  const bodyText = await page.locator('body').textContent();
  console.log('Body text (first 500 chars):', bodyText?.substring(0, 500));

  // Take screenshot
  await page.screenshot({ path: 'debug-screening-page.png', fullPage: true });
});
