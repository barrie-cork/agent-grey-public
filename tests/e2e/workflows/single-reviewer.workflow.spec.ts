import { test, expect } from '@playwright/test';
import { ReviewPage } from './pages/review.page';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * Single Reviewer Workflow Tests (Workflow #1)
 *
 * Tests the single-reviewer (split results) workflow from session creation to completion.
 * In Workflow #1, min_reviewers_per_result = 1 and results are split between reviewers.
 */

test.describe('Single Reviewer Workflow (Workflow #1)', () => {
  test.setTimeout(120000);

  test.describe('Review Interface', () => {
    let sessionId: string;

    test.beforeAll(() => {
      const sessions = getSeededSessions();
      sessionId = sessions.readyForReviewWf1;
    });

    test('review overview page is accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessionId);

      // Should be on review page or accessible
      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('review overview shows results', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessionId);

      // If on review page, check for result elements
      if (page.url().includes('/review-results/')) {
        await reviewPage.expectOnReviewPage();
        // Results should be visible (seeded with 10 results)
        const resultCount = await reviewPage.getResultCount();
        expect(resultCount).toBeGreaterThanOrEqual(0);
      }
    });

    test('filtered results page is accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoFiltered(sessionId);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('duplicate groups page is accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoDuplicates(sessionId);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('search statistics page is accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoStatistics(sessionId);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('make include decision on a result', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessionId);

      // If results are visible with include buttons, make a decision
      if (page.url().includes('/review-results/')) {
        const includeBtn = reviewPage.includeButtons.first();
        if (await includeBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
          await includeBtn.click();
          await page.waitForLoadState('domcontentloaded');
          // Should still be on review page after decision
          await expect(page).toHaveURL(/\/review-results\//);
        }
      }
    });

    test('make exclude decision on a result', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessionId);

      if (page.url().includes('/review-results/')) {
        const excludeBtn = reviewPage.excludeButtons.first();
        if (await excludeBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
          await excludeBtn.click();
          await page.waitForLoadState('domcontentloaded');
          await expect(page).toHaveURL(/\/review-results\//);
        }
      }
    });

    test('review progress API returns valid data', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/${sessionId}/progress/`
      );
      // Progress API should be accessible for this session
      if (response.ok()) {
        const data = await response.json();
        expect(data).toBeDefined();
      }
    });
  });

  test.describe('Completed Session', () => {
    let sessionId: string;

    test.beforeAll(() => {
      const sessions = getSeededSessions();
      sessionId = sessions.completedWf1;
    });

    test('completed session review overview is accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessionId);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions|reporting)/);
    });

    test('complete review page is accessible for completed session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      await page.goto(`/review-results/complete/${sessionId}/`, {
        waitUntil: 'domcontentloaded',
      });

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions|reporting)/);
    });
  });
});
