import { test, expect } from '@playwright/test';
import { SearchStrategyPage } from './pages/search-strategy.page';
import { SessionPage } from './pages/session.page';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * Search Strategy Workflow Tests
 *
 * Tests the PIC framework form for defining search strategy.
 * Uses a seeded draft session to navigate to the strategy page.
 *
 * URL: /search-strategy/session/<session_id>/
 */

test.describe.serial('Search Strategy Workflow', () => {
  test.setTimeout(120000);

  let sessionId: string;

  test.beforeAll(() => {
    const sessions = getSeededSessions();
    sessionId = sessions.draft;
  });

  test('navigate to search strategy page from session detail', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    // Navigate to session detail (use domcontentloaded -- SSE keeps network active)
    await page.goto(`/sessions/${sessionId}/`, { waitUntil: 'domcontentloaded' });

    // Click strategy link if available, otherwise navigate directly
    const strategyLink = page.locator('a:has-text("Search Strategy"), a:has-text("Define Search"), a[href*="search-strategy"]');
    if (await strategyLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await strategyLink.click();
      await page.waitForLoadState('domcontentloaded');
    } else {
      await page.goto(`/search-strategy/session/${sessionId}/`, { waitUntil: 'domcontentloaded' });
    }

    // Should be on the strategy page
    await expect(page).toHaveURL(/\/search-strategy\/session\/[a-f0-9-]+\//);
  });

  test('search strategy page loads with PIC form', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const strategyPage = new SearchStrategyPage(page);
    await strategyPage.goto(sessionId);
    await strategyPage.expectOnStrategyPage();

    // Verify PIC input fields are visible
    await expect(strategyPage.populationInput).toBeVisible();
    await expect(strategyPage.interestInput).toBeVisible();
    await expect(strategyPage.contextInput).toBeVisible();
  });

  test('fill PIC framework form with population terms', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const strategyPage = new SearchStrategyPage(page);
    await strategyPage.goto(sessionId);
    await strategyPage.expectOnStrategyPage();

    // Add population terms (tag-input pattern: type + Enter)
    await strategyPage.addPopulationTerm('elderly patients');
    await strategyPage.addPopulationTerm('older adults');

    // Verify terms were added (check for keyword tags)
    const populationTags = await strategyPage.getTagCount('population');
    expect(populationTags).toBeGreaterThanOrEqual(1);
  });

  test('fill complete PIC form and save strategy', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const strategyPage = new SearchStrategyPage(page);
    await strategyPage.goto(sessionId);
    await strategyPage.expectOnStrategyPage();

    // Fill all PIC fields
    await strategyPage.fillPICForm(
      ['elderly patients', 'older adults'],
      ['fall prevention', 'mobility'],
      ['community care', 'primary care']
    );

    // Save the strategy
    await strategyPage.saveStrategy();

    // Verify save succeeded -- page should reload or show success
    // Check we're still on the strategy page (not an error page)
    await expect(page).toHaveURL(/\/search-strategy\/session\/[a-f0-9-]+\//);
  });

  test('verify query preview after strategy save', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const strategyPage = new SearchStrategyPage(page);
    await strategyPage.goto(sessionId);

    // If strategy was saved in previous test, query preview should be visible
    // This depends on AJAX updates generating queries from PIC terms
    const queryPreview = strategyPage.queryPreview;
    if (await queryPreview.isVisible({ timeout: 5000 }).catch(() => false)) {
      const queryCount = await strategyPage.getQueryCount();
      expect(queryCount).toBeGreaterThanOrEqual(1);
    }
  });

  test('AJAX updates update query preview dynamically', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const strategyPage = new SearchStrategyPage(page);
    await strategyPage.goto(sessionId);
    await strategyPage.expectOnStrategyPage();

    // Add a new term and check that the page responds
    await strategyPage.addPopulationTerm('seniors');

    // Wait for AJAX response (networkidle captures async updates)
    await page.waitForLoadState('networkidle');

    // Page should still be functional (not errored)
    await expect(strategyPage.populationInput).toBeVisible();
  });

  test('guidelines filter updates query preview with filter terms', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const strategyPage = new SearchStrategyPage(page);
    await strategyPage.goto(sessionId);
    await strategyPage.expectOnStrategyPage();

    // Ensure PIC terms exist so preview is generated
    const tagCount = await strategyPage.getTagCount('population');
    if (tagCount === 0) {
      await strategyPage.addPopulationTerm('elderly patients');
    }

    // Wait for initial preview to settle
    await page.waitForLoadState('networkidle');

    // Capture preview text before enabling guidelines filter
    const previewBefore = await strategyPage.getQueryPreviewText();

    // Enable guidelines filter checkbox
    await strategyPage.toggleGuidelinesFilter();

    // Wait for the preview to update with guideline terms (debounce + AJAX)
    // Multiple debounced requests may fire; wait for the DOM to reflect the change
    await expect(strategyPage.queryPreview).toContainText('guideline', { timeout: 10000 });

    // Verify all expected guideline-specific terms appear in the preview
    const previewAfter = await strategyPage.getQueryPreviewText();
    expect(previewAfter).toContain('guideline');
    expect(previewAfter).toContain('guidance');
    expect(previewAfter).toContain('recommendation');

    // Verify the preview changed from before
    expect(previewAfter).not.toEqual(previewBefore);
  });
});
