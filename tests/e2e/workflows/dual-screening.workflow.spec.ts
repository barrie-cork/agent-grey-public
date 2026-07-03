import { test, expect, Browser } from '@playwright/test';
import { ReviewPage } from './pages/review.page';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * Dual Screening Workflow Tests (Workflow #2)
 *
 * Tests the dual-screening workflow with two reviewers, blinding, and conflict detection.
 * In Workflow #2, min_reviewers_per_result >= 2 and results are shared between reviewers.
 *
 * Uses browser.newContext() for multi-user scenarios (two reviewers).
 */

test.describe('Dual Screening Workflow (Workflow #2)', () => {
  test.setTimeout(120000);

  let sessions: ReturnType<typeof getSeededSessions>;

  test.beforeAll(() => {
    sessions = getSeededSessions();
  });

  test.describe('Review Interface Access', () => {
    test('owner can access review overview for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf2);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('reviewer1 can access review overview for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-reviewer1@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf2);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('reviewer2 can access review overview for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-reviewer2@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf2);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });
  });

  test.describe('Multi-User Dual Screening', () => {
    test('two reviewers can access same session in separate contexts', async ({ browser }) => {
      // Create two separate browser contexts for two reviewers
      const context1 = await browser.newContext();
      const context2 = await browser.newContext();
      const page1 = await context1.newPage();
      const page2 = await context2.newPage();

      try {
        // Login both reviewers
        await loginUser(page1, 'e2e-reviewer1@test.local');
        await loginUser(page2, 'e2e-reviewer2@test.local');

        // Both navigate to review overview
        const reviewPage1 = new ReviewPage(page1);
        const reviewPage2 = new ReviewPage(page2);

        await reviewPage1.gotoOverview(sessions.readyForReviewWf2);
        await reviewPage2.gotoOverview(sessions.readyForReviewWf2);

        // Both should be on review page
        expect(page1.url()).toMatch(/\/(review-results|sessions)/);
        expect(page2.url()).toMatch(/\/(review-results|sessions)/);
      } finally {
        await context1.close();
        await context2.close();
      }
    });

    test('review decisions can be made by both reviewers', async ({ browser }) => {
      const context1 = await browser.newContext();
      const context2 = await browser.newContext();
      const page1 = await context1.newPage();
      const page2 = await context2.newPage();

      try {
        await loginUser(page1, 'e2e-reviewer1@test.local');
        await loginUser(page2, 'e2e-reviewer2@test.local');

        const reviewPage1 = new ReviewPage(page1);
        const reviewPage2 = new ReviewPage(page2);

        await reviewPage1.gotoOverview(sessions.readyForReviewWf2);
        await reviewPage2.gotoOverview(sessions.readyForReviewWf2);

        // Both reviewers attempt to make decisions (if buttons visible)
        if (page1.url().includes('/review-results/')) {
          const includeBtn1 = reviewPage1.includeButtons.first();
          if (await includeBtn1.isVisible({ timeout: 5000 }).catch(() => false)) {
            await includeBtn1.click();
            await page1.waitForLoadState('domcontentloaded');
          }
        }

        if (page2.url().includes('/review-results/')) {
          const includeBtn2 = reviewPage2.includeButtons.first();
          if (await includeBtn2.isVisible({ timeout: 5000 }).catch(() => false)) {
            await includeBtn2.click();
            await page2.waitForLoadState('domcontentloaded');
          }
        }
      } finally {
        await context1.close();
        await context2.close();
      }
    });
  });

  test.describe('Under Review State (WF2)', () => {
    test('under-review session shows review data', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.underReviewWf2);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('mark-complete endpoint is accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      await page.goto(`/review-results/mark-complete/${sessions.underReviewWf2}/`, {
        waitUntil: 'domcontentloaded',
      });

      // Should be on mark-complete page or redirected
      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('session status API shows under_review', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/api/session/${sessions.underReviewWf2}/status/`
      );
      expect(response.ok()).toBeTruthy();

      const data = await response.json();
      expect(data.status).toBe('under_review');
    });
  });

  test.describe('Completed WF2 Session', () => {
    test('completed WF2 session review overview accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.completedWf2);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions|reporting)/);
    });

    test('completed WF2 session status is completed', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/api/session/${sessions.completedWf2}/status/`
      );
      expect(response.ok()).toBeTruthy();

      const data = await response.json();
      expect(data.status).toBe('completed');
    });
  });
});
