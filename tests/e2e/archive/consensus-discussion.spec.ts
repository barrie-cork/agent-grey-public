import { test, expect } from '@playwright/test';
import { loginAsReviewer, logout, testUsers } from './fixtures/auth';
import { sampleComments, sampleRevoteProposal } from './fixtures/test-data';
import {
  navigateToSPARoute,
  waitForVueComponent,
  waitForAPIResponse,
  waitForSSEReady,
} from './fixtures/vue-helpers';

/**
 * E2E Tests for Consensus Discussion Feature
 *
 * These tests cover the full consensus discussion workflow:
 * - Navigating to conflict pages
 * - Posting comments (top-level and replies)
 * - Proposing re-votes
 * - Accepting re-votes
 * - Submitting re-vote decisions
 * - Verifying consensus reached
 *
 * Prerequisites:
 * - Django server running on http://localhost:8000
 * - Test database with sample data (conflict, reviewers)
 * - Test users created (reviewer1, reviewer2)
 *
 * ARCHITECTURE NOTE:
 * The application uses a Vue SPA with client-side routing mounted at /screening/.
 * These tests use navigateToSPARoute() and waitForVueComponent() helpers to ensure
 * proper handling of Vue component lifecycle and Vue Router navigation.
 */

test.describe('Consensus Discussion Workflow', () => {
  // Setup: Login before each test
  // loginAsReviewer now also ensures organisation context is loaded
  // and navigates to /screening/ with Vue SPA ready
  test.beforeEach(async ({ page }) => {
    await loginAsReviewer(page, testUsers.reviewer1.username, testUsers.reviewer1.password);
  });

  // Note: Removed afterEach logout - Playwright browser contexts are isolated per test
  // so logout is not necessary and was causing race conditions with parallel execution

  test('Test 1: Navigate to conflict discussion page', async ({ page }) => {
    // Navigate to conflicts list (Vue SPA route)
    await navigateToSPARoute(page, '/conflicts');

    // Wait for ConflictList component to mount
    await waitForVueComponent(page, '[data-testid="conflict-list"]', 15000);

    // Wait for conflict items to load (API call may take time)
    await page.waitForSelector('[data-testid="conflict-item"]', { timeout: 15000 });

    // Click on first conflict
    await page.click('[data-testid="conflict-item"]');

    // Wait for navigation to discussion page
    await page.waitForURL(/\/screening\/conflicts\/.*\/discuss/, { timeout: 10000 });

    // Wait for ConflictDiscussion component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Verify page elements are present
    await expect(page.locator('[data-testid="conflict-header"]')).toBeVisible();
  });

  test('Test 2: Post top-level comment', async ({ page }) => {
    // Navigate to a specific conflict (using test data)
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);

    // Wait for ConflictDiscussion component to fully mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Wait for comment form to be ready
    await waitForVueComponent(page, '[data-testid="comment-textarea"]', 10000);

    // Fill in comment text
    const commentText = sampleComments.topLevel.content;
    await page.fill('[data-testid="comment-textarea"]', commentText);

    // Post comment
    await page.click('[data-testid="post-comment-btn"]');

    // Wait for API call to complete
    await waitForAPIResponse(page, /\/api\/consensus\//, 201, 10000);

    // Wait for comment to appear in DOM
    await page.waitForSelector('[data-testid="comment-content"]', { timeout: 5000 });

    // Verify comment is displayed
    const postedComment = await page.locator('[data-testid="comment-content"]').first();
    await expect(postedComment).toContainText(commentText.substring(0, 50)); // Check first 50 chars
  });

  test('Test 3: Post reply to comment', async ({ page }) => {
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);

    // Wait for component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Wait for existing comments to load
    await page.waitForSelector('[data-testid="reply-btn"]', { timeout: 10000 });

    // Click reply button on first comment
    await page.click('[data-testid="reply-btn"]');

    // Wait for reply form to appear
    await waitForVueComponent(page, '[data-testid="reply-textarea"]', 5000);

    // Fill in reply text
    const replyText = 'This is a test reply to the comment';
    await page.fill('[data-testid="reply-textarea"]', replyText);

    // Post reply
    await page.click('[data-testid="post-reply-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/consensus\//, 201, 10000);

    // Verify reply appears
    await page.waitForSelector('[data-testid="comment-reply"]', { timeout: 5000 });
    const reply = await page.locator('[data-testid="comment-reply"]').first();
    await expect(reply).toContainText(replyText);
  });

  test('Test 4: Test markdown rendering', async ({ page }) => {
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);

    // Wait for component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForVueComponent(page, '[data-testid="comment-textarea"]', 10000);

    // Post comment with markdown
    const markdownComment = sampleComments.withMarkdown.content;
    await page.fill('[data-testid="comment-textarea"]', markdownComment);
    await page.click('[data-testid="post-comment-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/consensus\//, 201, 10000);

    // Wait for comment to render
    await page.waitForSelector('[data-testid="comment-content"]', { timeout: 5000 });

    // Verify markdown is rendered correctly
    const renderedComment = page.locator('[data-testid="comment-content"]').first();

    // Check for heading
    await expect(renderedComment.locator('h2')).toContainText('Key Points');

    // Check for bold text
    await expect(renderedComment.locator('strong')).toContainText('primary research');

    // Check for code block
    await expect(renderedComment.locator('code')).toContainText('sample size');

    // Check for list items
    await expect(renderedComment.locator('li')).toHaveCount(3);
  });

  test('Test 5: Propose re-vote', async ({ page }) => {
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);

    // Wait for component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Wait for propose button to be available
    await page.waitForSelector('[data-testid="propose-revote-btn"]', { timeout: 10000 });

    // Click "Propose Re-Vote" button
    await page.click('[data-testid="propose-revote-btn"]');

    // Wait for rationale form to appear
    await waitForVueComponent(page, '[data-testid="revote-rationale"]', 5000);

    // Fill in rationale
    await page.fill('[data-testid="revote-rationale"]', sampleRevoteProposal.rationale);

    // Submit proposal
    await page.click('[data-testid="submit-revote-proposal-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/revote\//, 201, 10000);

    // Verify proposal appears in UI
    await page.waitForSelector('[data-testid="revote-proposal"]', { timeout: 5000 });
    const proposal = page.locator('[data-testid="revote-proposal"]');
    await expect(proposal).toContainText('Re-vote Proposed');
    await expect(proposal).toContainText(sampleRevoteProposal.rationale);
  });

  test('Test 6: Accept re-vote proposal (as second reviewer)', async ({ page, context }) => {
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';

    // Logout as reviewer1 and login as reviewer2
    await logout(page);
    await loginAsReviewer(page, testUsers.reviewer2.username, testUsers.reviewer2.password);

    // Navigate to conflict
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);

    // Wait for component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Wait for accept button to be available
    await page.waitForSelector('[data-testid="accept-revote-btn"]', { timeout: 10000 });

    // Click "Accept Re-Vote" button
    await page.click('[data-testid="accept-revote-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/revote\//, 200, 10000);

    // Verify status changed
    await page.waitForSelector('[data-testid="revote-status"]', { timeout: 5000 });
    const status = page.locator('[data-testid="revote-status"]');
    await expect(status).toContainText('Accepted');
  });

  test('Test 7: Submit re-vote decisions', async ({ page }) => {
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);

    // Wait for component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Assume re-vote has been accepted and we're on voting screen
    // Wait for decision buttons to be available
    await page.waitForSelector('[data-testid="revote-decision-exclude"]', { timeout: 10000 });

    // Select decision (INCLUDE or EXCLUDE)
    await page.click('[data-testid="revote-decision-exclude"]');

    // Add optional notes
    await page.fill('[data-testid="revote-notes"]', 'After discussion, I maintain my exclusion decision.');

    // Submit re-vote decision
    await page.click('[data-testid="submit-revote-decision-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/decisions\//, 201, 10000);

    // Verify decision submitted
    await page.waitForSelector('[data-testid="decision-submitted"]', { timeout: 5000 });
    await expect(page.locator('[data-testid="decision-submitted"]')).toBeVisible();
  });

  test('Test 8: Verify consensus reached', async ({ page }) => {
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);

    // Wait for component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // After both reviewers submit same decision, conflict should be resolved
    await page.waitForSelector('[data-testid="conflict-status"]', { timeout: 10000 });
    const status = page.locator('[data-testid="conflict-status"]');

    // Verify status shows "RESOLVED"
    await expect(status).toContainText('RESOLVED');

    // Verify final decision is displayed
    const finalDecision = page.locator('[data-testid="final-decision"]');
    await expect(finalDecision).toBeVisible();
    await expect(finalDecision).toContainText(/INCLUDE|EXCLUDE/);
  });

  test('Test 9: SSE real-time updates (multi-tab)', async ({ page, context }) => {
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';

    // Open first tab
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page);

    // Open second tab with same conflict
    const page2 = await context.newPage();
    await loginAsReviewer(page2, testUsers.reviewer2.username, testUsers.reviewer2.password);
    await navigateToSPARoute(page2, `/conflicts/${conflictId}/discuss`);
    await waitForVueComponent(page2, '[data-testid="conflict-header"]', 15000);
    await waitForSSEReady(page2);

    // Wait for comment form to be ready in first tab
    await waitForVueComponent(page, '[data-testid="comment-textarea"]', 10000);

    // Post comment in first tab
    const commentText = 'Testing real-time SSE update';
    await page.fill('[data-testid="comment-textarea"]', commentText);
    await page.click('[data-testid="post-comment-btn"]');

    // Wait for API response in first tab
    await waitForAPIResponse(page, /\/api\/consensus\//, 201, 10000);

    // Wait for comment to appear in first tab
    await page.waitForSelector('[data-testid="comment-content"]', { timeout: 5000 });

    // Verify comment appears in second tab via SSE (within 5 seconds)
    await page2.waitForSelector('[data-testid="comment-content"]', { timeout: 5000 });
    const commentInSecondTab = page2.locator('[data-testid="comment-content"]').last();
    await expect(commentInSecondTab).toContainText(commentText);

    // Clean up
    await page2.close();
  });

  test('Test 10: Permission check (non-reviewer blocked)', async ({ page }) => {
    // Logout as reviewer
    await logout(page);

    // Try to access conflict page without login
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';
    await page.goto(`/screening/conflicts/${conflictId}/discuss/`);

    // Verify redirect to login page
    // Django authentication middleware should redirect to /accounts/login/
    await expect(page).toHaveURL(/\/accounts\/login/, { timeout: 10000 });
  });

  test('Test 11: Error handling (invalid comment)', async ({ page }) => {
    const conflictId = '550e8400-e29b-41d4-a716-446655440000';
    await navigateToSPARoute(page, `/conflicts/${conflictId}/discuss`);

    // Wait for component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);
    await waitForVueComponent(page, '[data-testid="comment-textarea"]', 10000);

    // Try to post empty comment
    await page.click('[data-testid="post-comment-btn"]');

    // Verify error message appears
    await page.waitForSelector('[data-testid="comment-error"]', { timeout: 5000 });
    const error = page.locator('[data-testid="comment-error"]');
    await expect(error).toContainText(/required|cannot be empty/i);
  });

  test('Test 12: Empty state (no comments yet)', async ({ page }) => {
    // Navigate to a new conflict with no comments
    const newConflictId = '550e8400-e29b-41d4-a716-446655440999';
    await navigateToSPARoute(page, `/conflicts/${newConflictId}/discuss`);

    // Wait for component to mount
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Verify empty state message is displayed
    await page.waitForSelector('[data-testid="empty-state"]', { timeout: 10000 });
    const emptyState = page.locator('[data-testid="empty-state"]');
    await expect(emptyState).toContainText(/no comments|start the discussion/i);
  });
});
