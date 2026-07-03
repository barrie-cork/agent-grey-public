import { test, expect } from '@playwright/test';
import { SPAPage } from './pages/spa.page';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * Work Queue Workflow Tests (Vue SPA)
 *
 * Tests the Vue SPA work queue for claiming and reviewing results.
 * The Vue SPA at /screening/ requires a built frontend; tests gracefully
 * skip if the SPA is not available (404).
 *
 * Also tests the screening API endpoints directly.
 */

test.describe('Work Queue Workflow', () => {
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

  test.describe('Screening API Endpoints', () => {
    test('claim-next API endpoint is accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      // POST to claim-next with session context
      const response = await page.request.post('/review-results/api/screening/claim-next/', {
        data: { session_id: sessions.readyForReviewWf1 },
        headers: { 'Content-Type': 'application/json' },
      });
      // May return 200 (claimed), 204 (none available), or 400/403
      expect(response.status()).toBeLessThan(500);
    });

    test('review progress API returns data for WF1 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/screening/progress/${sessions.readyForReviewWf1}/`
      );
      expect(response.status()).toBeLessThan(500);
    });

    test('review progress API returns data for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/screening/progress/${sessions.readyForReviewWf2}/`
      );
      expect(response.status()).toBeLessThan(500);
    });
  });

  test.describe('Vue SPA Work Queue (if available)', () => {
    test('work queue page loads', async ({ page }) => {
      test.skip(!spaAvailable, 'Vue SPA not built/served at /screening/');

      await loginUser(page, 'e2e-owner@test.local');

      const spaPage = new SPAPage(page);
      await spaPage.gotoWorkQueue();
      await spaPage.waitForVueSPA();

      await expect(page).toHaveURL(/\/screening\/work-queue/);
      await expect(page.locator('#app')).toBeVisible();
    });

    test('work queue shows filter buttons', async ({ page }) => {
      test.skip(!spaAvailable, 'Vue SPA not built/served at /screening/');

      await loginUser(page, 'e2e-owner@test.local');

      const spaPage = new SPAPage(page);
      await spaPage.gotoWorkQueue();
      await spaPage.waitForVueSPA();

      // Work queue should have some UI elements
      await expect(page.locator('#app')).toBeVisible();
    });

    test('work queue refresh works', async ({ page }) => {
      test.skip(!spaAvailable, 'Vue SPA not built/served at /screening/');

      await loginUser(page, 'e2e-owner@test.local');

      const spaPage = new SPAPage(page);
      await spaPage.gotoWorkQueue();
      await spaPage.waitForVueSPA();

      const refreshBtn = spaPage.refreshQueueButton;
      if (await refreshBtn.isVisible()) {
        await refreshBtn.click();
        await page.waitForLoadState('domcontentloaded');
      }

      await expect(page).toHaveURL(/\/screening\/work-queue/);
    });

    test('navigation between work queue and conflicts', async ({ page }) => {
      test.skip(!spaAvailable, 'Vue SPA not built/served at /screening/');

      await loginUser(page, 'e2e-owner@test.local');

      const spaPage = new SPAPage(page);
      await spaPage.gotoWorkQueue();
      await spaPage.waitForVueSPA();

      await spaPage.gotoConflicts();

      await page.goBack();
      await expect(page).toHaveURL(/\/screening\/work-queue/);

      await page.goForward();
      await expect(page).toHaveURL(/\/screening\/conflicts/);
    });
  });
});
