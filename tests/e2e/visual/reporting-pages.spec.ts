import { test, expect } from '@playwright/test';
import { testUsers } from '../fixtures/auth';

test.describe('Reporting Pages - Visual Regression', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/accounts/login/');
    await page.waitForLoadState('networkidle');
    await page.fill('[data-testid="email"], #id_email', testUsers.reviewer1.email);
    await page.fill('[data-testid="password"], #id_password', testUsers.reviewer1.password);
    await page.click('[data-testid="login-btn"], button[type="submit"]');
    await page.waitForURL(/\/$|dashboard|sessions/, { timeout: 15000 });
  });

  test('Reporting Dashboard', async ({ page }) => {
    await page.goto('/reporting/dashboard/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await expect(page).toHaveScreenshot('reporting-dashboard-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Feedback List page', async ({ page }) => {
    await page.goto('/feedback/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await expect(page).toHaveScreenshot('feedback-list-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Feedback Form page', async ({ page }) => {
    await page.goto('/feedback/submit/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    await expect(page).toHaveScreenshot('feedback-form-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });
});
