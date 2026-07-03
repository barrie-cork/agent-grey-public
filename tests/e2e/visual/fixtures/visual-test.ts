import { test as base, expect } from '@playwright/test';
import { testUsers } from '../../fixtures/auth';

/**
 * Visual test fixture that provides authenticated page for visual regression tests.
 * Extends the base Playwright test with authentication handling.
 */
export const test = base.extend<{
  authenticatedPage: typeof base;
}>({
  authenticatedPage: async ({ page }, use) => {
    // Login before tests that require authentication
    await page.goto('/accounts/login/');
    await page.waitForLoadState('networkidle');

    // Fill login form using data-testid attributes (matches existing auth patterns)
    await page.fill('[data-testid="email"]', testUsers.reviewer1.email);
    await page.fill('[data-testid="password"]', testUsers.reviewer1.password);
    await page.click('[data-testid="login-btn"]');

    // Wait for redirect to dashboard
    await page.waitForURL(/\/$|dashboard|sessions/, { timeout: 15000 });

    await use(page);
  },
});

export { expect };

/**
 * Helper to wait for page to be visually stable before taking screenshot
 */
export async function waitForVisualStability(page: typeof base.prototype.page, timeout = 2000): Promise<void> {
  await page.waitForLoadState('networkidle');
  // Wait for any CSS transitions/animations to complete
  await page.waitForTimeout(timeout);
}

/**
 * Helper to hide dynamic content that changes between test runs
 * (e.g., timestamps, avatars, etc.)
 */
export async function hideDynamicContent(page: typeof base.prototype.page): Promise<void> {
  await page.addStyleTag({
    content: `
      /* Hide timestamps and dates */
      [data-testid*="timestamp"],
      [data-testid*="date"],
      time,
      .timestamp,
      .date {
        visibility: hidden !important;
      }

      /* Hide avatars that may vary */
      [data-testid*="avatar"],
      .avatar {
        visibility: hidden !important;
      }

      /* Disable animations */
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
      }
    `,
  });
}
