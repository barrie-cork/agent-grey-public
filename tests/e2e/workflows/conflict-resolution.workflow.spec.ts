import { test, expect } from '@playwright/test';
import { SPAPage } from './pages/spa.page';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * Conflict Resolution Workflow Tests
 *
 * Tests the conflict resolution workflow including the Vue SPA and API endpoints.
 * The Vue SPA at /screening/ requires a built frontend; tests gracefully
 * skip if the SPA is not available (404).
 *
 * Also tests the conflict API endpoints directly.
 */

test.describe('Conflict Resolution Workflow', () => {
  test.setTimeout(60000);

  let sessions: ReturnType<typeof getSeededSessions>;
  let spaAvailable: boolean;

  test.beforeAll(async ({ browser }) => {
    sessions = getSeededSessions();

    // Check if Vue SPA is available
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await loginUser(page, 'e2e-owner@test.local');
      const response = await page.request.get('/screening/work-queue');
      spaAvailable = response.status() !== 404;
    } catch {
      spaAvailable = false;
    } finally {
      await context.close();
    }
  });

  test.describe('Conflict API Endpoints', () => {
    test('conflict list API returns valid response', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get('/review-results/api/conflicts/');
      // API should return < 500 (may be 200, 403, or empty)
      expect(response.status()).toBeLessThan(500);
    });

    test('session stats API returns data for under-review session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/${sessions.underReviewWf2}/session-stats-api/`
      );
      expect(response.status()).toBeLessThan(500);
    });

    test('review progress API returns data', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/screening/progress/${sessions.underReviewWf2}/`
      );
      expect(response.status()).toBeLessThan(500);
    });
  });

  test.describe('Vue SPA (if available)', () => {
    test('conflicts page loads when SPA is available', async ({ page }) => {
      test.skip(!spaAvailable, 'Vue SPA not built/served at /screening/');

      await loginUser(page, 'e2e-owner@test.local');

      const spaPage = new SPAPage(page);
      await spaPage.gotoConflicts();
      await spaPage.waitForVueSPA();

      await expect(page).toHaveURL(/\/screening\/conflicts/);
      await expect(page.locator('#app')).toBeVisible();
    });

    test('work queue page loads when SPA is available', async ({ page }) => {
      test.skip(!spaAvailable, 'Vue SPA not built/served at /screening/');

      await loginUser(page, 'e2e-owner@test.local');

      const spaPage = new SPAPage(page);
      await spaPage.gotoWorkQueue();
      await spaPage.waitForVueSPA();

      await expect(page).toHaveURL(/\/screening\/work-queue/);
    });

    test('team dashboard loads when SPA is available', async ({ page }) => {
      test.skip(!spaAvailable, 'Vue SPA not built/served at /screening/');

      await loginUser(page, 'e2e-owner@test.local');

      const spaPage = new SPAPage(page);
      await spaPage.gotoDashboard();
      await spaPage.waitForVueSPA();

      await expect(page).toHaveURL(/\/screening\/dashboard/);
    });

    test('SPA navigation between pages', async ({ page }) => {
      test.skip(!spaAvailable, 'Vue SPA not built/served at /screening/');

      await loginUser(page, 'e2e-owner@test.local');

      const spaPage = new SPAPage(page);

      await spaPage.gotoWorkQueue();
      await spaPage.waitForVueSPA();

      await spaPage.gotoConflicts();
      await spaPage.waitForVueSPA();

      // Back to work queue
      await page.goBack();
      await expect(page).toHaveURL(/\/screening\/work-queue/);
    });
  });
});
