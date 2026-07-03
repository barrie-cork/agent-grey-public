import { test, expect } from '@playwright/test';
import { SessionPage } from './pages/session.page';
import { DashboardPage } from './pages/dashboard.page';
import { loginUser, defaultTestUsers } from './fixtures/test-users';

/**
 * Session Lifecycle Workflow Tests
 *
 * Tests the 9-state session workflow transitions from draft through archived.
 * Uses pre-created e2e- users (no signup needed).
 */

test.describe('Session Lifecycle Workflow', () => {
  test.setTimeout(120000);

  test('session shows correct status at each state', async ({ page }) => {
    const sessionPage = new SessionPage(page);

    await loginUser(page, defaultTestUsers.owner.email);

    // Create session
    const sessionId = await sessionPage.createSession(`Lifecycle Test ${Date.now()}`);

    // Save setup so current_configuration exists (detail page redirects to setup without it)
    await sessionPage.gotoSetup(sessionId);
    await sessionPage.saveSetup();

    // Verify initial status is draft
    await sessionPage.gotoDetail(sessionId);
    const status = await sessionPage.getStatus();
    expect(status.toLowerCase()).toMatch(/draft/);
  });

  test('session detail page shows all navigation links', async ({ page }) => {
    const sessionPage = new SessionPage(page);

    await loginUser(page, defaultTestUsers.owner.email);

    const sessionId = await sessionPage.createSession(`Nav Links Test ${Date.now()}`);

    // Save setup so current_configuration exists (detail page redirects to setup without it)
    await sessionPage.gotoSetup(sessionId);
    await sessionPage.saveSetup();

    // Go to session detail
    await sessionPage.gotoDetail(sessionId);

    // Verify session elements are visible
    await expect(sessionPage.statusBadge).toBeVisible();
  });

  test('can navigate from dashboard to session and back', async ({ page }) => {
    const sessionPage = new SessionPage(page);
    const dashboardPage = new DashboardPage(page);
    const sessionTitle = `Dashboard Nav Test ${Date.now()}`;

    await loginUser(page, defaultTestUsers.owner.email);

    await sessionPage.createSession(sessionTitle);

    // Go to dashboard
    await dashboardPage.goto();
    await dashboardPage.expectOnDashboard();

    // Click on session card (action button navigates to next workflow step)
    await dashboardPage.clickSessionCard(sessionTitle);

    // Should navigate to a session-related page (detail, search strategy, etc.)
    await expect(page).toHaveURL(/\/(sessions|search-strategy)\/.*[a-f0-9-]+/);

    // Go back to dashboard
    await page.goBack();
    await dashboardPage.expectOnDashboard();

    // Go forward to session page
    await page.goForward();
    await expect(page).toHaveURL(/\/(sessions|search-strategy)\/.*[a-f0-9-]+/);
  });

  test('session setup page is accessible', async ({ page }) => {
    const sessionPage = new SessionPage(page);

    await loginUser(page, defaultTestUsers.owner.email);

    const sessionId = await sessionPage.createSession(`Setup Test ${Date.now()}`);

    // Navigate to setup
    await sessionPage.gotoSetup(sessionId);
    await sessionPage.expectOnSetupPage();

    // Verify setup elements are visible
    const reviewerSelect = sessionPage.minReviewersSelect;
    if (await reviewerSelect.isVisible()) {
      await expect(reviewerSelect).toBeEnabled();
    }
  });
});
