import { test, expect } from '@playwright/test';
import { SearchExecutionPage } from './pages/search-execution.page';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * Search Execution Workflow Tests
 *
 * Tests the execution status page and progress monitoring.
 * Uses seeded sessions at various states to test status display.
 *
 * NOTE: Does NOT trigger real Serper API calls. Tests verify the execution
 * status page renders correctly for sessions that have already been executed
 * (seeded by management commands).
 *
 * URL: /execution/session/<session_id>/status/
 */

test.describe('Search Execution Workflow', () => {
  test.setTimeout(120000);

  let sessions: ReturnType<typeof getSeededSessions>;

  test.beforeAll(() => {
    sessions = getSeededSessions();
  });

  test('execution status page is accessible for completed session', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const executionPage = new SearchExecutionPage(page);
    // Use a completed session which has execution records
    await executionPage.goto(sessions.completedWf1);

    // Should be on the execution status page or redirected
    const url = page.url();
    expect(url).toMatch(/\/(execution|sessions|reporting)/);
  });

  test('execution status page shows completed state', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const executionPage = new SearchExecutionPage(page);
    await executionPage.goto(sessions.readyForReviewWf1);

    // Page should load without errors
    const url = page.url();
    expect(url).toMatch(/\/(execution|sessions)/);

    // If on execution page, check for status elements
    if (url.includes('/execution/')) {
      await executionPage.expectOnStatusPage();
    }
  });

  test('execution status page for WF2 session', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    const executionPage = new SearchExecutionPage(page);
    await executionPage.goto(sessions.readyForReviewWf2);

    // Should be on execution or redirected (session already past execution)
    const url = page.url();
    expect(url).toMatch(/\/(execution|sessions)/);
  });

  test('session status API returns valid status', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    // Check the session status API endpoint
    const response = await page.request.get(
      `/api/session/${sessions.readyForReviewWf1}/status/`
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('status');
    expect(['ready_for_review', 'under_review', 'completed']).toContain(data.status);
  });

  test('session status API returns status for any session state', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    // Test API with a session that has completed execution
    const response = await page.request.get(
      `/api/session/${sessions.completedWf1}/status/`
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('status');
    expect(data.status).toBe('completed');
  });
});
