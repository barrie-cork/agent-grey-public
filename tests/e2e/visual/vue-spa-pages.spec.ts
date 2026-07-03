import { test, expect } from '@playwright/test';
import { testUsers } from '../fixtures/auth';

test.describe('Vue SPA Pages - Visual Regression', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/accounts/login/');
    await page.waitForLoadState('networkidle');
    await page.fill('[data-testid="email"], #id_email', testUsers.reviewer1.email);
    await page.fill('[data-testid="password"], #id_password', testUsers.reviewer1.password);
    await page.click('[data-testid="login-btn"], button[type="submit"]');
    await page.waitForURL(/\/$|dashboard|sessions/, { timeout: 15000 });
  });

  test('Conflict List page', async ({ page }) => {
    await page.goto('/conflicts/');
    await page.waitForLoadState('networkidle');

    // Wait for Vue app to mount
    await page.waitForTimeout(3000);

    await expect(page).toHaveScreenshot('conflict-list-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Team Dashboard page', async ({ page }) => {
    await page.goto('/team-dashboard/');
    await page.waitForLoadState('networkidle');

    // Wait for Vue app to mount
    await page.waitForTimeout(3000);

    await expect(page).toHaveScreenshot('team-dashboard-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Work Queue page', async ({ page }) => {
    await page.goto('/work-queue/');
    await page.waitForLoadState('networkidle');

    // Wait for Vue app to mount
    await page.waitForTimeout(3000);

    await expect(page).toHaveScreenshot('work-queue-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Screening page', async ({ page }) => {
    await page.goto('/screening/');
    await page.waitForLoadState('networkidle');

    // Wait for Vue app to mount
    await page.waitForTimeout(3000);

    await expect(page).toHaveScreenshot('screening-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('Component Showcase page', async ({ page }) => {
    await page.goto('/component-showcase/');
    await page.waitForLoadState('networkidle');

    // Wait for Vue app to mount
    await page.waitForTimeout(3000);

    await expect(page).toHaveScreenshot('component-showcase-desktop.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });
});
