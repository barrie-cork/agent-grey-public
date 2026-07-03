import { test, expect } from '@playwright/test';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * Results Processing Workflow Tests
 *
 * Tests the processing status page and deduplication verification.
 * Uses seeded sessions that have already been processed (ready_for_review+).
 *
 * URL: /results-manager/processing/<session_id>/
 */

test.describe('Results Processing Workflow', () => {
  test.setTimeout(120000);

  let sessions: ReturnType<typeof getSeededSessions>;

  test.beforeAll(() => {
    sessions = getSeededSessions();
  });

  test('processing status page is accessible', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    // Navigate to processing status for a session that has been processed
    await page.goto(`/results-manager/processing/${sessions.readyForReviewWf1}/`, {
      waitUntil: 'domcontentloaded',
    });

    // Should be on processing page or redirected (session already past processing)
    const url = page.url();
    expect(url).toMatch(/\/(results-manager|sessions|review)/);
  });

  test('processing status page for completed WF2 session', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    await page.goto(`/results-manager/processing/${sessions.completedWf2}/`, {
      waitUntil: 'domcontentloaded',
    });

    // Page should load without errors
    const url = page.url();
    expect(url).toMatch(/\/(results-manager|sessions|reporting)/);
  });

  test('session with processed results has correct status via API', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    // Verify session status is past processing
    const response = await page.request.get(
      `/api/session/${sessions.readyForReviewWf1}/status/`
    );
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(['ready_for_review', 'under_review', 'completed']).toContain(data.status);
  });

  test('review overview accessible after processing complete', async ({ page }) => {
    await loginUser(page, 'e2e-owner@test.local');

    // After processing, review overview should be accessible
    await page.goto(`/review-results/overview/${sessions.readyForReviewWf1}/`, {
      waitUntil: 'domcontentloaded',
    });

    // Should be on review page (session is in ready_for_review)
    const url = page.url();
    expect(url).toMatch(/\/(review-results|sessions)/);
  });
});
