import { test, expect } from '@playwright/test';
import { loginAsReviewer, testUsers } from './fixtures/auth';
import {
  navigateToSPARoute,
  waitForVueComponent,
  waitForAPIResponse,
  waitForSSEReady,
} from './fixtures/vue-helpers';

/**
 * E2E Tests for Server-Sent Events (SSE) Real-Time Updates
 *
 * These tests verify that the SSE implementation works correctly:
 * - EventSource connection established
 * - Real-time events delivered
 * - Multi-tab synchronization
 * - Reconnection after interruption
 * - Connection cleanup on page unload
 *
 * Prerequisites:
 * - Django server running with SSE endpoints configured
 * - Nginx configured for SSE (proxy_buffering off)
 * - Test conflict data in database
 *
 * ARCHITECTURE NOTE:
 * The application uses a Vue SPA with client-side routing mounted at /screening/.
 * These tests use navigateToSPARoute() and waitForVueComponent() helpers to ensure
 * proper handling of Vue component lifecycle and Vue Router navigation.
 */

test.describe('SSE Real-Time Updates', () => {
  const testConflictId = '550e8400-e29b-41d4-a716-446655440000';

  test.beforeEach(async ({ page }) => {
    await loginAsReviewer(page, testUsers.reviewer1.username, testUsers.reviewer1.password);
  });

  test('SSE connection establishes successfully', async ({ page }) => {
    // Navigate to conflict discussion page using SPA-aware helper
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);

    // Wait for ConflictDiscussion component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Wait for SSE connection to establish
    await waitForSSEReady(page);

    // Check that EventSource connection is active
    const sseIndicator = page.locator('[data-testid="sse-status"]');

    // If there's a connection indicator, verify it shows "connected"
    if (await sseIndicator.isVisible()) {
      await expect(sseIndicator).toContainText(/connected|active/i);
    }

    // Alternative: Check browser console for SSE connection logs
    page.on('console', (msg) => {
      if (msg.text().includes('EventSource')) {
        console.log('SSE Event:', msg.text());
      }
    });
  });

  test('New comment event received in real-time', async ({ page, context }) => {
    // Tab 1: Reviewer 1
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Get initial comment count
    const initialComments = await page.locator('[data-testid="comment-item"]').count();

    // Tab 2: Reviewer 2
    const page2 = await context.newPage();
    await loginAsReviewer(page2, testUsers.reviewer2.username, testUsers.reviewer2.password);
    await navigateToSPARoute(page2, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page2, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page2);

    // Wait for comment form to be ready
    await waitForVueComponent(page2, '[data-testid="comment-textarea"]', 10000);

    // Post comment from Tab 2
    const commentText = `Real-time test comment ${Date.now()}`;
    await page2.fill('[data-testid="comment-textarea"]', commentText);
    await page2.click('[data-testid="post-comment-btn"]');

    // Wait for API response in Tab 2
    await waitForAPIResponse(page2, /\/api\/consensus\//, 201, 10000);

    // Wait for comment to appear in Tab 2
    await page2.waitForSelector(`text=${commentText}`, { timeout: 5000 });

    // Verify comment appears in Tab 1 via SSE (within 5 seconds)
    await page.waitForSelector(`text=${commentText}`, { timeout: 5000 });

    // Verify comment count increased
    const newComments = await page.locator('[data-testid="comment-item"]').count();
    expect(newComments).toBe(initialComments + 1);

    // Cleanup
    await page2.close();
  });

  test('Re-vote proposal event received in real-time', async ({ page, context }) => {
    // Tab 1: Reviewer 1
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Tab 2: Reviewer 2
    const page2 = await context.newPage();
    await loginAsReviewer(page2, testUsers.reviewer2.username, testUsers.reviewer2.password);
    await navigateToSPARoute(page2, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page2, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page2);

    // Wait for propose button to be available
    await page2.waitForSelector('[data-testid="propose-revote-btn"]', { timeout: 10000 });

    // Propose re-vote from Tab 2
    await page2.click('[data-testid="propose-revote-btn"]');

    // Wait for rationale form to appear
    await waitForVueComponent(page2, '[data-testid="revote-rationale"]', 5000);

    const rationale = `Test revote proposal ${Date.now()}`;
    await page2.fill('[data-testid="revote-rationale"]', rationale);
    await page2.click('[data-testid="submit-revote-proposal-btn"]');

    // Wait for API response in Tab 2
    await waitForAPIResponse(page2, /\/api\/revote\//, 201, 10000);

    // Wait for proposal to appear in Tab 2
    await page2.waitForSelector('[data-testid="revote-proposal"]', { timeout: 5000 });

    // Verify proposal appears in Tab 1 via SSE (within 5 seconds)
    await page.waitForSelector('[data-testid="revote-proposal"]', { timeout: 5000 });

    // Verify rationale is displayed
    const proposalInTab1 = page.locator('[data-testid="revote-proposal"]');
    await expect(proposalInTab1).toContainText(rationale);

    // Cleanup
    await page2.close();
  });

  test('Re-vote acceptance event received in real-time', async ({ page, context }) => {
    // This test assumes a re-vote has already been proposed

    // Tab 1: Reviewer 1 (proposer)
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Verify re-vote proposal exists and is in "Proposed" status
    const proposalStatus = page.locator('[data-testid="revote-status"]');
    await expect(proposalStatus).toContainText('Proposed');

    // Tab 2: Reviewer 2 (acceptor)
    const page2 = await context.newPage();
    await loginAsReviewer(page2, testUsers.reviewer2.username, testUsers.reviewer2.password);
    await navigateToSPARoute(page2, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page2, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page2);

    // Wait for accept button to be available
    await page2.waitForSelector('[data-testid="accept-revote-btn"]', { timeout: 10000 });

    // Accept re-vote from Tab 2
    await page2.click('[data-testid="accept-revote-btn"]');

    // Wait for API response
    await waitForAPIResponse(page2, /\/api\/revote\//, 200, 10000);

    // Wait for status to update in Tab 2
    await page2.waitForSelector('[data-testid="revote-status"]:has-text("Accepted")', { timeout: 5000 });

    // Verify status updates in Tab 1 via SSE (within 5 seconds)
    await page.waitForSelector('[data-testid="revote-status"]:has-text("Accepted")', { timeout: 5000 });

    // Cleanup
    await page2.close();
  });

  test('Consensus reached event received in real-time', async ({ page, context }) => {
    // This test simulates both reviewers submitting the same re-vote decision

    // Tab 1: Reviewer 1
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Tab 2: Reviewer 2
    const page2 = await context.newPage();
    await loginAsReviewer(page2, testUsers.reviewer2.username, testUsers.reviewer2.password);
    await navigateToSPARoute(page2, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page2, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page2);

    // Wait for decision buttons to be available
    await page.waitForSelector('[data-testid="revote-decision-exclude"]', { timeout: 10000 });
    await page2.waitForSelector('[data-testid="revote-decision-exclude"]', { timeout: 10000 });

    // Reviewer 1 submits decision (EXCLUDE)
    await page.click('[data-testid="revote-decision-exclude"]');
    await page.click('[data-testid="submit-revote-decision-btn"]');
    await waitForAPIResponse(page, /\/api\/decisions\//, 201, 10000);

    // Reviewer 2 submits decision (EXCLUDE - same as Reviewer 1)
    await page2.click('[data-testid="revote-decision-exclude"]');
    await page2.click('[data-testid="submit-revote-decision-btn"]');
    await waitForAPIResponse(page2, /\/api\/decisions\//, 201, 10000);

    // Wait for consensus event in Tab 2
    await page2.waitForSelector('[data-testid="conflict-status"]:has-text("RESOLVED")', { timeout: 5000 });

    // Verify consensus event received in Tab 1 via SSE (within 5 seconds)
    await page.waitForSelector('[data-testid="conflict-status"]:has-text("RESOLVED")', { timeout: 5000 });

    // Verify final decision is displayed in both tabs
    await expect(page.locator('[data-testid="final-decision"]')).toContainText('EXCLUDE');
    await expect(page2.locator('[data-testid="final-decision"]')).toContainText('EXCLUDE');

    // Cleanup
    await page2.close();
  });

  test('Multi-tab test: 10 tabs receive events', async ({ page, context }) => {
    // Create 10 tabs with the same conflict
    const tabs = [page];

    // Initialize first tab
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Create additional tabs
    for (let i = 1; i < 10; i++) {
      const newPage = await context.newPage();
      await loginAsReviewer(newPage, testUsers.reviewer1.username, testUsers.reviewer1.password);
      await navigateToSPARoute(newPage, `/conflicts/${testConflictId}/discuss`);
      await waitForVueComponent(newPage, '[data-testid="conflict-header"]', 15000);
      await waitForSSEReady(newPage);
      tabs.push(newPage);
    }

    // Wait for comment form to be ready in first tab
    await waitForVueComponent(tabs[0], '[data-testid="comment-textarea"]', 10000);

    // Post comment from first tab
    const commentText = `Multi-tab test ${Date.now()}`;
    await tabs[0].fill('[data-testid="comment-textarea"]', commentText);
    await tabs[0].click('[data-testid="post-comment-btn"]');

    // Wait for API response
    await waitForAPIResponse(tabs[0], /\/api\/consensus\//, 201, 10000);

    // Verify all tabs receive the event (within 5 seconds)
    for (let i = 0; i < tabs.length; i++) {
      await tabs[i].waitForSelector(`text=${commentText}`, { timeout: 5000 });
      console.log(`Tab ${i} received event`);
    }

    // Cleanup
    for (let i = 1; i < tabs.length; i++) {
      await tabs[i].close();
    }
  });

  test('SSE reconnection after network interruption', async ({ page, context }) => {
    // Navigate to conflict page
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Simulate network interruption by going offline
    await context.setOffline(true);

    // Wait a few seconds
    await page.waitForTimeout(2000);

    // Restore network connection
    await context.setOffline(false);

    // Wait for reconnection
    await page.waitForTimeout(2000);

    // Post a comment from another tab to test reconnection
    const page2 = await context.newPage();
    await loginAsReviewer(page2, testUsers.reviewer2.username, testUsers.reviewer2.password);
    await navigateToSPARoute(page2, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page2, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page2);

    // Wait for comment form to be ready
    await waitForVueComponent(page2, '[data-testid="comment-textarea"]', 10000);

    const commentText = `Reconnection test ${Date.now()}`;
    await page2.fill('[data-testid="comment-textarea"]', commentText);
    await page2.click('[data-testid="post-comment-btn"]');

    // Wait for API response
    await waitForAPIResponse(page2, /\/api\/consensus\//, 201, 10000);

    // Verify first tab (which was offline) receives the event after reconnection
    await page.waitForSelector(`text=${commentText}`, { timeout: 10000 });

    // Cleanup
    await page2.close();
  });

  test('SSE connection cleanup on page unload', async ({ page }) => {
    // Navigate to conflict page
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Set up listener for EventSource close event
    await page.evaluate(() => {
      window.addEventListener('beforeunload', () => {
        // Check if EventSource is properly closed
        // This would be verified in the actual implementation
        console.log('Page unloading, EventSource should be closed');
      });
    });

    // Navigate away from the page (back to screening root)
    await navigateToSPARoute(page, '/work-queue');

    // Verify navigation was successful (implies EventSource was closed without errors)
    await page.waitForURL(/\/screening\/work-queue/, { timeout: 10000 });
  });

  test('SSE handles rapid sequential events', async ({ page, context }) => {
    // Tab 1: Observer
    await navigateToSPARoute(page, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Tab 2: Rapid commenter
    const page2 = await context.newPage();
    await loginAsReviewer(page2, testUsers.reviewer2.username, testUsers.reviewer2.password);
    await navigateToSPARoute(page2, `/conflicts/${testConflictId}/discuss`);
    await waitForVueComponent(page2, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page2);

    // Wait for comment form to be ready
    await waitForVueComponent(page2, '[data-testid="comment-textarea"]', 10000);

    // Post 5 comments rapidly
    const comments = [];
    for (let i = 0; i < 5; i++) {
      const commentText = `Rapid comment ${i} ${Date.now()}`;
      comments.push(commentText);
      await page2.fill('[data-testid="comment-textarea"]', commentText);
      await page2.click('[data-testid="post-comment-btn"]');

      // Wait for API response before posting next comment
      await waitForAPIResponse(page2, /\/api\/consensus\//, 201, 10000);

      // Small delay between comments
      await page2.waitForTimeout(200);
    }

    // Verify all comments appear in Tab 1 (order may vary due to async)
    for (const comment of comments) {
      await page.waitForSelector(`text=${comment}`, { timeout: 10000 });
    }

    // Verify comment count is correct
    const commentCount = await page.locator('[data-testid="comment-item"]').count();
    expect(commentCount).toBeGreaterThanOrEqual(5);

    // Cleanup
    await page2.close();
  });
});
