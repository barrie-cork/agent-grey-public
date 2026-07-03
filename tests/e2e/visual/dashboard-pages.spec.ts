import { test, expect } from '@playwright/test';
import { DashboardPage } from './pages';
import { testUsers } from '../fixtures/auth';

test.describe('Dashboard Pages - Visual Regression', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/accounts/login/');
    await page.waitForLoadState('networkidle');
    await page.fill('[data-testid="email"], #id_email', testUsers.reviewer1.email);
    await page.fill('[data-testid="password"], #id_password', testUsers.reviewer1.password);
    await page.click('[data-testid="login-btn"], button[type="submit"]');
    await page.waitForURL(/\/$|dashboard|sessions/, { timeout: 15000 });
  });

  test('Dashboard page - session list', async ({ page }) => {
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.goto();
    await dashboardPage.waitForPageReady();

    // Wait for any dynamic content to load
    await page.waitForTimeout(2000);

    await expect(page).toHaveScreenshot('dashboard-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Dashboard page - empty state', async ({ page }) => {
    // Navigate to dashboard - may show empty state for new users
    await page.goto('/review-manager/dashboard/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await expect(page).toHaveScreenshot('dashboard-empty-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Profile page', async ({ page }) => {
    await page.goto('/accounts/profile/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    await expect(page).toHaveScreenshot('profile-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Session create page', async ({ page }) => {
    await page.goto('/review-manager/sessions/create/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    await expect(page).toHaveScreenshot('session-create-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });
});
