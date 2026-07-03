import { test, expect } from '@playwright/test';
import { SessionPage } from './pages/session.page';
import { DashboardPage } from './pages/dashboard.page';
import { loginUser, defaultTestUsers } from './fixtures/test-users';

/**
 * Session Creation Workflow Tests
 *
 * Tests the complete session creation flow from dashboard to ready-to-execute.
 * Uses pre-created e2e- users (no signup needed).
 */

test.describe('Session Creation Workflow', () => {
  test.setTimeout(60000);

  test('create session from dashboard', async ({ page }) => {
    const sessionPage = new SessionPage(page);
    const dashboardPage = new DashboardPage(page);

    await loginUser(page, defaultTestUsers.owner.email);

    // Go to dashboard
    await dashboardPage.goto();
    await dashboardPage.expectOnDashboard();

    // Click create session
    await dashboardPage.clickCreateSession();
    await sessionPage.expectOnCreatePage();

    // Fill form and submit
    const sessionTitle = `Test Session ${Date.now()}`;
    await sessionPage.fillCreateForm(sessionTitle, 'Test description');
    const sessionId = await sessionPage.submitCreateForm();

    // Should redirect to session detail or setup
    await expect(page).toHaveURL(/\/sessions\/[a-f0-9-]+\/(setup)?/);

    // Go back to verify session appears in dashboard
    await dashboardPage.goto();
    await dashboardPage.expectSessionVisible(sessionTitle);
  });

  test('cancel creation returns to dashboard', async ({ page }) => {
    const sessionPage = new SessionPage(page);
    const dashboardPage = new DashboardPage(page);

    await loginUser(page, defaultTestUsers.owner.email);

    // Navigate to create page
    await sessionPage.gotoCreate();
    await sessionPage.expectOnCreatePage();

    // Fill some data
    await sessionPage.titleInput.fill('This will be cancelled');

    // Click cancel
    await sessionPage.cancelCreate();

    // Should be back on dashboard
    await dashboardPage.expectOnDashboard();
  });

  test('session create page back/forward navigation', async ({ page }) => {
    const sessionPage = new SessionPage(page);
    const dashboardPage = new DashboardPage(page);

    await loginUser(page, defaultTestUsers.owner.email);

    // Dashboard -> Create page
    await dashboardPage.goto();
    await dashboardPage.clickCreateSession();
    await sessionPage.expectOnCreatePage();

    // Go back to dashboard
    await page.goBack();
    await dashboardPage.expectOnDashboard();

    // Go forward to create page
    await page.goForward();
    await sessionPage.expectOnCreatePage();
  });

  test('session setup configures reviewers', async ({ page }) => {
    const sessionPage = new SessionPage(page);

    await loginUser(page, defaultTestUsers.owner.email);

    const sessionId = await sessionPage.createSession(`Reviewers Test ${Date.now()}`);

    // Go to setup
    await sessionPage.gotoSetup(sessionId);
    await sessionPage.expectOnSetupPage();

    // Configure 2 reviewers if available
    await sessionPage.configureReviewers(2);

    // Save setup
    await sessionPage.saveSetup();
  });

  test('created session appears in dashboard session list', async ({ page }) => {
    const sessionPage = new SessionPage(page);
    const dashboardPage = new DashboardPage(page);
    const sessionTitle = `List Test ${Date.now()}`;

    await loginUser(page, defaultTestUsers.owner.email);

    // Create multiple sessions
    await sessionPage.createSession(sessionTitle);
    await sessionPage.createSession(`${sessionTitle} - 2`);

    // Go to dashboard
    await dashboardPage.goto();

    // Verify both sessions appear
    await dashboardPage.expectSessionVisible(sessionTitle);
    await dashboardPage.expectSessionVisible(`${sessionTitle} - 2`);
  });
});
