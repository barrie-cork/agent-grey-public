import { test, expect } from '@playwright/test';
import { loginAsReviewer, logout, testUsers } from './fixtures/auth';
import {
  navigateToSPARoute,
  waitForVueComponent,
  waitForAPIResponse,
} from './fixtures/vue-helpers';

/**
 * E2E Tests for Dual-Screening Workflows
 *
 * These tests cover complete workflows for both:
 * - Workflow #1: Work Distribution (single reviewer per result, parallel processing)
 * - Workflow #2: Independent Screening (dual screening with conflict resolution)
 *
 * Prerequisites:
 * - Django server running on http://localhost:8000
 * - Test database with sample data (session, results, reviewers)
 * - Test users created (reviewer1, reviewer2)
 * - ReviewConfiguration with min_reviewers_per_result = 1 (Workflow #1) or 2 (Workflow #2)
 *
 * ARCHITECTURE NOTE:
 * The application uses a Vue SPA with client-side routing mounted at /screening/.
 * These tests use navigateToSPARoute() and waitForVueComponent() helpers to ensure
 * proper handling of Vue component lifecycle and Vue Router navigation.
 */

test.describe('Workflow #1: Work Distribution (Single Reviewer)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsReviewer(page, testUsers.reviewer1.username, testUsers.reviewer1.password);
  });

  test('Test 1: Claim and review results in work queue', async ({ page }) => {
    // Navigate to work queue (Vue SPA route)
    await navigateToSPARoute(page, '/work-queue');

    // Wait for WorkQueue component to mount
    await waitForVueComponent(page, '[data-testid="work-queue"]', 15000);

    // Wait for results to load
    await page.waitForSelector('[data-testid="result-row"]', { timeout: 15000 });

    // Get initial result count
    const initialCount = await page.locator('[data-testid="result-row"]').count();
    expect(initialCount).toBeGreaterThan(0);

    // Claim next result
    await page.click('[data-testid="claim-button"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/review\/claim/, 200, 10000);

    // Wait for result detail to appear
    await page.waitForSelector('[data-testid="result-detail"]', { timeout: 5000 });

    // Make a decision (INCLUDE)
    await page.click('[data-testid="decision-include"]');

    // Add rationale
    await page.fill('[data-testid="rationale-textarea"]', 'Relevant grey literature source for systematic review');

    // Submit decision
    await page.click('[data-testid="submit-decision-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/review\/decision/, 201, 10000);

    // Verify decision submitted (should return to queue)
    await page.waitForSelector('[data-testid="work-queue"]', { timeout: 5000 });

    // Verify progress updated
    await page.waitForSelector('[data-testid="progress-count"]', { timeout: 5000 });
    const progressText = await page.locator('[data-testid="progress-count"]').textContent();
    expect(progressText).toMatch(/\d+/); // Should contain a number
  });

  test('Test 2: Verify completion tracking', async ({ page }) => {
    // Navigate to session detail page
    const sessionId = '550e8400-e29b-41d4-a716-446655440000'; // Test session ID
    await page.goto(`/sessions/${sessionId}/`);

    // Wait for page to load
    await page.waitForSelector('[data-testid="session-detail"]', { timeout: 15000 });

    // Verify reviewer progress is displayed
    await page.waitForSelector('[data-testid="reviewer-progress"]', { timeout: 5000 });
    const progressElement = page.locator('[data-testid="reviewer-progress"]').first();
    await expect(progressElement).toBeVisible();

    // Verify progress shows reviewed count
    const progressText = await progressElement.textContent();
    expect(progressText).toMatch(/\d+\/\d+/); // Should show "X/Y" format
  });

  test('Test 3: Complete review workflow', async ({ page }) => {
    // Navigate to work queue
    await navigateToSPARoute(page, '/work-queue');
    await waitForVueComponent(page, '[data-testid="work-queue"]', 15000);

    // Check if all results reviewed
    const completeButton = page.locator('[data-testid="mark-complete-btn"]');

    if (await completeButton.isVisible({ timeout: 2000 })) {
      // Mark as complete
      await completeButton.click();

      // Wait for confirmation modal
      await page.waitForSelector('[data-testid="completion-modal"]', { timeout: 5000 });

      // Confirm completion
      await page.click('[data-testid="confirm-complete-btn"]');

      // Wait for API response
      await waitForAPIResponse(page, /\/api\/review\/complete/, 200, 10000);

      // Verify completion success message
      await page.waitForSelector('[data-testid="completion-success"]', { timeout: 5000 });
      await expect(page.locator('[data-testid="completion-success"]')).toBeVisible();
    }
  });
});

test.describe('Workflow #2: Independent Screening (Dual Screening)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsReviewer(page, testUsers.reviewer1.username, testUsers.reviewer1.password);
  });

  test('Test 4: Review results in multi-reviewer mode', async ({ page }) => {
    // Navigate to results overview (Django template, not SPA)
    const sessionId = '550e8400-e29b-41d4-a716-446655440001'; // Test session ID for Workflow #2
    await page.goto(`/sessions/${sessionId}/results/`);

    // Wait for results overview page
    await page.waitForSelector('[data-testid="results-overview"]', { timeout: 15000 });

    // Verify blinding indicator is shown
    await page.waitForSelector('[data-testid="blinding-indicator"]', { timeout: 5000 });
    const blindingText = await page.locator('[data-testid="blinding-indicator"]').textContent();
    expect(blindingText).toContain('hidden');

    // Click on first result to review
    await page.click('[data-testid="result-row"]');

    // Wait for result detail
    await page.waitForSelector('[data-testid="result-detail"]', { timeout: 5000 });

    // Make decision (INCLUDE)
    await page.click('[data-testid="decision-include"]');

    // Add notes
    await page.fill('[data-testid="notes-textarea"]', 'Meets inclusion criteria based on title and abstract');

    // Submit decision
    await page.click('[data-testid="submit-decision-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/review\/decision/, 201, 10000);

    // Verify decision submitted
    await page.waitForSelector('[data-testid="decision-success"]', { timeout: 5000 });
  });

  test('Test 5: Complete review and trigger conflict detection', async ({ page }) => {
    const sessionId = '550e8400-e29b-41d4-a716-446655440001';
    await page.goto(`/sessions/${sessionId}/results/`);

    // Wait for page load
    await page.waitForSelector('[data-testid="results-overview"]', { timeout: 15000 });

    // Check if completion button available
    const completeButton = page.locator('[data-testid="mark-complete-btn"]');

    if (await completeButton.isVisible({ timeout: 2000 })) {
      // Click mark complete
      await completeButton.click();

      // Wait for completion modal
      await page.waitForSelector('[data-testid="completion-modal"]', { timeout: 5000 });

      // Verify warning about conflicts (if incomplete reviews)
      const modalText = await page.locator('[data-testid="completion-modal"]').textContent();

      if (modalText?.includes('reviewed all results')) {
        // Confirm completion
        await page.click('[data-testid="confirm-complete-btn"]');

        // Wait for API response
        await waitForAPIResponse(page, /\/api\/review\/complete/, 200, 10000);

        // Verify completion or waiting state
        const waitingState = page.locator('[data-testid="waiting-state"]');
        if (await waitingState.isVisible({ timeout: 5000 })) {
          // Verify other reviewers' progress is shown
          await expect(waitingState).toContainText(/\d+\/\d+/);
        }
      }
    }
  });

  test('Test 6: View and resolve conflicts (CONSENSUS method)', async ({ page, context }) => {
    const sessionId = '550e8400-e29b-41d4-a716-446655440001';

    // Assume both reviewers have completed and conflicts detected
    // Navigate to conflicts list
    await navigateToSPARoute(page, `/conflicts?session=${sessionId}`);

    // Wait for conflict list to load
    await waitForVueComponent(page, '[data-testid="conflict-list"]', 15000);

    // Wait for conflict items
    await page.waitForSelector('[data-testid="conflict-item"]', { timeout: 10000 });

    // Verify conflicts are displayed
    const conflictCount = await page.locator('[data-testid="conflict-item"]').count();
    expect(conflictCount).toBeGreaterThan(0);

    // Click on first conflict
    await page.click('[data-testid="conflict-item"]');

    // Wait for navigation to discussion page
    await page.waitForURL(/\/screening\/conflicts\/.*\/discuss/, { timeout: 10000 });

    // Wait for ConflictDiscussion component
    await waitForVueComponent(page, '[data-testid="conflict-header"]', 15000);

    // Verify both decisions are shown
    await page.waitForSelector('[data-testid="decision-reviewer1"]', { timeout: 5000 });
    await page.waitForSelector('[data-testid="decision-reviewer2"]', { timeout: 5000 });

    // Post a comment to discuss
    await waitForVueComponent(page, '[data-testid="comment-textarea"]', 10000);
    await page.fill('[data-testid="comment-textarea"]', 'After reviewing the source, I agree we should include this.');
    await page.click('[data-testid="post-comment-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/conflicts\/.*\/discuss/, 201, 10000);

    // Verify comment appears
    await page.waitForSelector('[data-testid="comment-content"]', { timeout: 5000 });

    // Mark as resolved (if consensus reached)
    const resolveButton = page.locator('[data-testid="mark-resolved-btn"]');
    if (await resolveButton.isVisible({ timeout: 2000 })) {
      await resolveButton.click();

      // Wait for resolution modal
      await page.waitForSelector('[data-testid="resolution-modal"]', { timeout: 5000 });

      // Select final decision
      await page.click('[data-testid="final-decision-include"]');

      // Add resolution notes
      await page.fill('[data-testid="resolution-notes"]', 'Consensus reached through discussion');

      // Confirm resolution
      await page.click('[data-testid="confirm-resolution-btn"]');

      // Wait for API response
      await waitForAPIResponse(page, /\/api\/conflicts\/.*\/resolve/, 200, 10000);

      // Verify resolution success
      await page.waitForSelector('[data-testid="resolution-success"]', { timeout: 5000 });
    }
  });

  test('Test 7: View IRR metrics on team dashboard', async ({ page }) => {
    const sessionId = '550e8400-e29b-41d4-a716-446655440001';

    // Navigate to team dashboard
    await navigateToSPARoute(page, `/dashboard?session=${sessionId}`);

    // Wait for TeamDashboard component
    await waitForVueComponent(page, '[data-testid="team-dashboard"]', 15000);

    // Wait for IRR metrics section
    await page.waitForSelector('[data-testid="irr-metrics"]', { timeout: 10000 });

    // Verify Cohen's Kappa is displayed
    await page.waitForSelector('[data-testid="kappa-value"]', { timeout: 5000 });
    const kappaElement = page.locator('[data-testid="kappa-value"]');
    await expect(kappaElement).toBeVisible();

    // Verify interpretation badge
    await page.waitForSelector('[data-testid="kappa-interpretation"]', { timeout: 5000 });
    const interpretationElement = page.locator('[data-testid="kappa-interpretation"]');
    const interpretationText = await interpretationElement.textContent();
    expect(interpretationText).toMatch(/(Good|Substantial|Fair|Moderate|Poor|Slight)/);

    // Verify confusion matrix is shown
    await page.waitForSelector('[data-testid="confusion-matrix"]', { timeout: 5000 });
    await expect(page.locator('[data-testid="confusion-matrix"]')).toBeVisible();
  });

  test('Test 8: Lead arbitration workflow', async ({ page }) => {
    const sessionId = '550e8400-e29b-41d4-a716-446655440002'; // Session with LEAD_ARBITRATION

    // Login as session owner (lead reviewer)
    await logout(page);
    await loginAsReviewer(page, testUsers.owner.username, testUsers.owner.password);

    // Navigate to conflicts
    await navigateToSPARoute(page, `/conflicts?session=${sessionId}`);

    // Wait for conflict list
    await waitForVueComponent(page, '[data-testid="conflict-list"]', 15000);
    await page.waitForSelector('[data-testid="conflict-item"]', { timeout: 10000 });

    // Click on conflict
    await page.click('[data-testid="conflict-item"]');

    // Wait for ConflictResolution component
    await page.waitForURL(/\/screening\/conflicts\/.*\/resolve/, { timeout: 10000 });
    await waitForVueComponent(page, '[data-testid="conflict-resolution"]', 15000);

    // Verify both decisions visible (not blinded for lead)
    await page.waitForSelector('[data-testid="decision-reviewer1"]', { timeout: 5000 });
    await page.waitForSelector('[data-testid="decision-reviewer2"]', { timeout: 5000 });

    // Select final decision
    await page.click('[data-testid="arbitrate-include"]');

    // Add arbitration notes
    await page.fill('[data-testid="arbitration-notes"]', 'As lead reviewer, I decide to include based on relevance to research question');

    // Submit arbitration
    await page.click('[data-testid="submit-arbitration-btn"]');

    // Wait for API response
    await waitForAPIResponse(page, /\/api\/conflicts\/.*\/arbitrate/, 200, 10000);

    // Verify arbitration success
    await page.waitForSelector('[data-testid="arbitration-success"]', { timeout: 5000 });
  });
});

test.describe('Concurrent Access Tests', () => {
  test('Test 9: Concurrent claiming (race condition protection)', async ({ page, context }) => {
    // Login as reviewer1 in first tab
    await loginAsReviewer(page, testUsers.reviewer1.username, testUsers.reviewer1.password);
    await navigateToSPARoute(page, '/work-queue');
    await waitForVueComponent(page, '[data-testid="work-queue"]', 15000);

    // Open second tab as reviewer2
    const page2 = await context.newPage();
    await loginAsReviewer(page2, testUsers.reviewer2.username, testUsers.reviewer2.password);
    await navigateToSPARoute(page2, '/work-queue');
    await waitForVueComponent(page2, '[data-testid="work-queue"]', 15000);

    // Both click claim simultaneously
    await Promise.all([
      page.click('[data-testid="claim-button"]'),
      page2.click('[data-testid="claim-button"]')
    ]);

    // Wait for API responses
    await Promise.all([
      waitForAPIResponse(page, /\/api\/review\/claim/, 200, 10000).catch(() => null),
      waitForAPIResponse(page2, /\/api\/review\/claim/, 200, 10000).catch(() => null)
    ]);

    // Verify only one succeeded (SELECT FOR UPDATE SKIP LOCKED)
    const result1Visible = await page.locator('[data-testid="result-detail"]').isVisible({ timeout: 2000 }).catch(() => false);
    const result2Visible = await page2.locator('[data-testid="result-detail"]').isVisible({ timeout: 2000 }).catch(() => false);

    // Exactly one should have succeeded
    expect(result1Visible !== result2Visible).toBeTruthy();

    // Clean up
    await page2.close();
  });

  test('Test 10: Session completion validation', async ({ page }) => {
    const sessionId = '550e8400-e29b-41d4-a716-446655440001';

    // Login as session owner
    await loginAsReviewer(page, testUsers.owner.username, testUsers.owner.password);
    await page.goto(`/sessions/${sessionId}/`);

    // Wait for session detail page
    await page.waitForSelector('[data-testid="session-detail"]', { timeout: 15000 });

    // Try to complete session
    const completeSessionButton = page.locator('[data-testid="complete-session-btn"]');

    if (await completeSessionButton.isVisible({ timeout: 2000 })) {
      await completeSessionButton.click();

      // Wait for validation modal
      await page.waitForSelector('[data-testid="validation-modal"]', { timeout: 5000 });

      // Check for unresolved conflicts warning
      const modalText = await page.locator('[data-testid="validation-modal"]').textContent();

      if (modalText?.includes('unresolved conflicts')) {
        // Verify completion is blocked
        const confirmButton = page.locator('[data-testid="confirm-complete-btn"]');
        await expect(confirmButton).toBeDisabled();
      } else if (modalText?.includes('ready to complete')) {
        // Can complete
        await page.click('[data-testid="confirm-complete-btn"]');

        // Wait for API response
        await waitForAPIResponse(page, /\/api\/sessions\/.*\/complete/, 200, 10000);

        // Verify completion success
        await page.waitForSelector('[data-testid="session-completed"]', { timeout: 5000 });
      }
    }
  });
});

test.describe('Performance Tests', () => {
  test('Test 11: Conflict list loads within 2 seconds', async ({ page }) => {
    const sessionId = '550e8400-e29b-41d4-a716-446655440001';

    await loginAsReviewer(page, testUsers.reviewer1.username, testUsers.reviewer1.password);

    // Measure time to load conflicts
    const startTime = Date.now();

    await navigateToSPARoute(page, `/conflicts?session=${sessionId}`);
    await waitForVueComponent(page, '[data-testid="conflict-list"]', 15000);
    await page.waitForSelector('[data-testid="conflict-item"]', { timeout: 10000 });

    const elapsed = Date.now() - startTime;

    // Verify performance target
    expect(elapsed).toBeLessThan(2000);
  });

  test('Test 12: Work queue refresh performance', async ({ page }) => {
    await loginAsReviewer(page, testUsers.reviewer1.username, testUsers.reviewer1.password);
    await navigateToSPARoute(page, '/work-queue');
    await waitForVueComponent(page, '[data-testid="work-queue"]', 15000);

    // Wait for initial load
    await page.waitForSelector('[data-testid="result-row"]', { timeout: 15000 });

    // Measure refresh time
    const startTime = Date.now();

    await page.click('[data-testid="refresh-btn"]');
    await waitForAPIResponse(page, /\/api\/review\/queue/, 200, 5000);

    const elapsed = Date.now() - startTime;

    // Verify performance target (<1 second)
    expect(elapsed).toBeLessThan(1000);
  });
});
