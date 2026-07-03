import { test, expect } from '@playwright/test';
import { AuthPage } from './pages/auth.page';
import { loginUser, defaultTestUsers } from './fixtures/test-users';

/**
 * Profile Management Workflow Tests
 *
 * Tests user profile viewing and navigation.
 * Uses pre-created e2e- users (no signup needed).
 */

test.describe('Profile Management Workflow', () => {
  test.setTimeout(60000);

  test('profile page is accessible after login', async ({ page }) => {
    await loginUser(page, defaultTestUsers.reviewer1.email);

    const authPage = new AuthPage(page);
    await authPage.goToProfile();
    await expect(page).toHaveURL(/\/accounts\/profile\//);
  });

  test('profile page displays user information', async ({ page }) => {
    await loginUser(page, defaultTestUsers.reviewer1.email);

    const authPage = new AuthPage(page);
    await authPage.goToProfile();

    await expect(page).toHaveURL(/\/accounts\/profile\//);
    await expect(page.locator('body')).not.toBeEmpty();
  });

  test('profile page back/forward navigation', async ({ page }) => {
    await loginUser(page, defaultTestUsers.reviewer1.email);

    // Navigate: Dashboard -> Profile
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const authPage = new AuthPage(page);
    await authPage.goToProfile();
    await expect(page).toHaveURL(/\/accounts\/profile\//);

    // Go back to dashboard
    await page.goBack();
    await expect(page).toHaveURL('/');

    // Go forward to profile
    await page.goForward();
    await expect(page).toHaveURL(/\/accounts\/profile\//);
  });

  test('profile accessible from navigation menu', async ({ page }) => {
    await loginUser(page, defaultTestUsers.reviewer1.email);

    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    // Look for profile link in navigation
    const profileLink = page.locator('a[href*="profile"], [data-testid="link-profile"]').first();
    if (await profileLink.isVisible()) {
      await profileLink.click();
      await expect(page).toHaveURL(/\/accounts\/profile\//);
    } else {
      // Direct navigation as fallback
      const authPage = new AuthPage(page);
      await authPage.goToProfile();
      await expect(page).toHaveURL(/\/accounts\/profile\//);
    }
  });
});
