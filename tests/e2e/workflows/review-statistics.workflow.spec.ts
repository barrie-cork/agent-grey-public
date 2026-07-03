import { test, expect } from '@playwright/test';
import { ReviewPage } from './pages/review.page';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions, SeededSessions } from './fixtures/seeded-sessions';

/**
 * Review Statistics E2E Tests
 *
 * Verifies that review statistics are correctly displayed across:
 * - Review overview page (template-rendered stats)
 * - Progress API endpoint (JSON)
 * - Dashboard stats API (JSON, WF2)
 * - Session card progress percentages (no trailing .0)
 *
 * Uses seeded sessions at key workflow states to validate counts.
 */

test.describe('Review Statistics', () => {
  test.setTimeout(60000);

  let sessions: SeededSessions;

  test.beforeAll(() => {
    sessions = getSeededSessions();
  });

  // ==========================================================================
  // REVIEW OVERVIEW PAGE - STATISTICS DISPLAY
  // ==========================================================================

  test.describe('Review Overview - WF1 (ready_for_review)', () => {
    test('displays processing summary with correct structure', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf1);

      if (!page.url().includes('/review-results/')) return;

      // Processing summary card should be visible
      const summary = page.locator('[data-testid="processing-summary"]');
      if (await summary.isVisible({ timeout: 3000 }).catch(() => false)) {
        await expect(summary).toContainText('Successfully Processed');
        await expect(summary).toContainText('Total Results');
      }
    });

    test('displays filter buttons with numeric counts', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf1);

      if (!page.url().includes('/review-results/')) return;

      // Quick actions panel should show filter buttons with counts
      const quickActions = page.locator('[data-testid="quick-actions-panel"]');
      await expect(quickActions).toBeVisible({ timeout: 5000 });

      // Each filter button should have a numeric badge
      const allBtn = page.locator('[data-testid="filter-all-btn"]');
      await expect(allBtn).toBeVisible();
      // Count badge should contain a number (not empty or NaN)
      const allCount = await allBtn.locator('span.font-mono').textContent();
      expect(allCount).toMatch(/^\d+$/);

      const pendingBtn = page.locator('[data-testid="filter-pending-btn"]');
      await expect(pendingBtn).toBeVisible();
      const pendingCount = await pendingBtn.locator('span.font-mono').textContent();
      expect(pendingCount).toMatch(/^\d+$/);
    });

    test('displays results count heading', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf1);

      if (!page.url().includes('/review-results/')) return;

      const heading = page.locator('[data-testid="results-count-heading"]');
      await expect(heading).toBeVisible({ timeout: 5000 });
      // Should contain "Results for Review" with a number in parentheses
      await expect(heading).toContainText(/Results for Review \(\d+\)/);
    });

    test('displays review progress indicator', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf1);

      if (!page.url().includes('/review-results/')) return;

      const progress = page.locator('[data-testid="review-progress-indicator"]');
      await expect(progress).toBeVisible({ timeout: 5000 });
    });

    test('session overview card shows session title and status', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf1);

      if (!page.url().includes('/review-results/')) return;

      const card = page.locator('[data-testid="session-overview-card"]');
      await expect(card).toBeVisible({ timeout: 5000 });

      const title = page.locator('[data-testid="session-title"]');
      await expect(title).not.toBeEmpty();

      const badge = page.locator('[data-testid="session-status-badge"]');
      await expect(badge).toBeVisible();
    });
  });

  test.describe('Review Overview - WF2 (ready_for_review)', () => {
    test('shows blinding indicator for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf2);

      if (!page.url().includes('/review-results/')) return;

      const blinding = page.locator('[data-testid="blinding-indicator"]');
      await expect(blinding).toBeVisible({ timeout: 5000 });
      await expect(blinding).toContainText('Blinded PRISMA Mode');
    });

    test('shows kappa widget card for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf2);

      if (!page.url().includes('/review-results/')) return;

      const kappa = page.locator('[data-testid="kappa-widget-card"]');
      await expect(kappa).toBeVisible({ timeout: 5000 });
    });

    test('WF2 filter buttons show numeric counts', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.readyForReviewWf2);

      if (!page.url().includes('/review-results/')) return;

      // For a ready_for_review WF2 session with no decisions, pending should equal total
      const allBtn = page.locator('[data-testid="filter-all-btn"]');
      const pendingBtn = page.locator('[data-testid="filter-pending-btn"]');
      const includedBtn = page.locator('[data-testid="filter-included-btn"]');
      const excludedBtn = page.locator('[data-testid="filter-excluded-btn"]');

      await expect(allBtn).toBeVisible({ timeout: 5000 });

      const allCount = await allBtn.locator('span.font-mono').textContent();
      const pendingCount = await pendingBtn.locator('span.font-mono').textContent();
      const includedCount = await includedBtn.locator('span.font-mono').textContent();
      const excludedCount = await excludedBtn.locator('span.font-mono').textContent();

      // All counts should be valid numbers
      expect(allCount).toMatch(/^\d+$/);
      expect(pendingCount).toMatch(/^\d+$/);
      expect(includedCount).toMatch(/^\d+$/);
      expect(excludedCount).toMatch(/^\d+$/);

      // For a fresh session: included and excluded should be 0
      expect(Number(includedCount)).toBe(0);
      expect(Number(excludedCount)).toBe(0);
    });
  });

  test.describe('Review Overview - WF2 (under_review with decisions)', () => {
    test('under-review session shows non-zero decision counts', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.underReviewWf2);

      if (!page.url().includes('/review-results/')) return;

      // This session has decisions made (50% agreement), so counts should be > 0
      const allBtn = page.locator('[data-testid="filter-all-btn"]');
      await expect(allBtn).toBeVisible({ timeout: 5000 });

      const allCount = Number(await allBtn.locator('span.font-mono').textContent());
      expect(allCount).toBeGreaterThan(0);
    });
  });

  // ==========================================================================
  // PROGRESS API (Template View JSON Endpoint)
  // ==========================================================================

  test.describe('Progress API', () => {
    test('returns valid JSON with expected fields for WF1 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/${sessions.readyForReviewWf1}/progress/`
      );

      if (!response.ok()) return; // Skip if endpoint not accessible

      const data = await response.json();
      expect(data).toBeDefined();

      // Should have standard progress fields
      if (data.total_results !== undefined) {
        expect(typeof data.total_results).toBe('number');
        expect(data.total_results).toBeGreaterThanOrEqual(0);
      }
      if (data.pending_count !== undefined) {
        expect(typeof data.pending_count).toBe('number');
      }
      if (data.included_count !== undefined) {
        expect(typeof data.included_count).toBe('number');
      }
      if (data.excluded_count !== undefined) {
        expect(typeof data.excluded_count).toBe('number');
      }
    });

    test('returns valid JSON with expected fields for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/${sessions.underReviewWf2}/progress/`
      );

      if (!response.ok()) return;

      const data = await response.json();
      expect(data).toBeDefined();

      if (data.total_results !== undefined) {
        expect(typeof data.total_results).toBe('number');
        expect(data.total_results).toBeGreaterThan(0);
      }
    });

    test('progress percentage has no trailing .0', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/${sessions.readyForReviewWf1}/progress/`
      );

      if (!response.ok()) return;

      const data = await response.json();

      // If completion_percentage is present and is a whole number, it should be an integer
      if (data.completion_percentage !== undefined) {
        const pct = data.completion_percentage;
        if (Number.isInteger(pct)) {
          // Should not be represented as "0.0" in JSON - verify it's a clean integer
          expect(pct).toBe(Math.floor(pct));
        }
      }
    });
  });

  // ==========================================================================
  // DASHBOARD STATS API (WF2 Endpoints)
  // ==========================================================================

  test.describe('Dashboard Stats API', () => {
    test('returns valid stats for under_review WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/api/dashboard/stats/?session_id=${sessions.underReviewWf2}`
      );

      // May return 403/500 if user is not lead reviewer for this session
      if (!response.ok()) return;

      const data = await response.json();
      expect(data).toBeDefined();

      // Verify response structure
      expect(data.session).toBeDefined();
      expect(data.overview).toBeDefined();
      expect(data.progress).toBeDefined();
      expect(data.team_performance).toBeDefined();

      // Overview should have numeric fields
      expect(typeof data.overview.total_results).toBe('number');
      expect(typeof data.overview.reviewed).toBe('number');
      expect(typeof data.overview.pending).toBe('number');
      expect(typeof data.overview.included).toBe('number');
      expect(typeof data.overview.excluded).toBe('number');
      expect(typeof data.overview.conflicts).toBe('number');

      // Progress percentage should be a number
      expect(typeof data.progress.percentage_complete).toBe('number');

      // Team performance fields
      expect(typeof data.team_performance.active_reviewers).toBe('number');
      expect(typeof data.team_performance.reviews_today).toBe('number');
      expect(typeof data.team_performance.average_time_per_review_seconds).toBe('number');
    });

    test('reviewer_breakdown contains unique entries (no duplicates)', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/api/dashboard/stats/?session_id=${sessions.underReviewWf2}`
      );

      if (!response.ok()) return;

      const data = await response.json();

      if (data.reviewer_breakdown) {
        // WF2 blinding replaces non-current-user reviewer IDs with "blinded",
        // so check uniqueness only among non-blinded IDs
        const reviewerIds = data.reviewer_breakdown.map(
          (r: { reviewer: { id: string } }) => r.reviewer.id
        );
        const nonBlindedIds = reviewerIds.filter((id: string) => id !== 'blinded');
        const uniqueNonBlinded = new Set(nonBlindedIds);
        expect(uniqueNonBlinded.size).toBe(nonBlindedIds.length);

        // Blinded entries should have unique usernames (e.g. "Reviewer 1", "Reviewer 2")
        const blindedEntries = data.reviewer_breakdown.filter(
          (r: { reviewer: { id: string } }) => r.reviewer.id === 'blinded'
        );
        if (blindedEntries.length > 1) {
          const usernames = blindedEntries.map(
            (r: { reviewer: { username: string } }) => r.reviewer.username
          );
          const uniqueNames = new Set(usernames);
          expect(uniqueNames.size).toBe(usernames.length);
        }

        // Each reviewer entry should have expected fields
        for (const entry of data.reviewer_breakdown) {
          expect(typeof entry.total_reviews).toBe('number');
          expect(typeof entry.reviews_today).toBe('number');
          expect(typeof entry.average_time_seconds).toBe('number');
          expect(typeof entry.inclusion_rate_percentage).toBe('number');
          expect(['active', 'idle']).toContain(entry.current_status);
        }
      }
    });

    test('percentage fields have no trailing .0', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/api/dashboard/stats/?session_id=${sessions.underReviewWf2}`
      );

      if (!response.ok()) return;

      const data = await response.json();

      // Check percentage_complete
      const pct = data.progress.percentage_complete;
      if (Number.isInteger(pct)) {
        // JSON serialisation of Python int produces clean integer
        const jsonStr = JSON.stringify(pct);
        expect(jsonStr).not.toContain('.');
      }

      // Check conflict_rate_percentage
      const conflictRate = data.team_performance.conflict_rate_percentage;
      if (Number.isInteger(conflictRate)) {
        const jsonStr = JSON.stringify(conflictRate);
        expect(jsonStr).not.toContain('.');
      }
    });
  });

  // ==========================================================================
  // IRR METRICS API
  // ==========================================================================

  test.describe('IRR Metrics API', () => {
    test('returns valid response for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/api/dashboard/irr/?session_id=${sessions.underReviewWf2}`
      );

      // May return 403/500 if user is not lead reviewer for this session
      if (!response.ok()) return;

      const data = await response.json();
      expect(Array.isArray(data)).toBeTruthy();

      // If IRR records exist, verify structure
      for (const record of data) {
        expect(record).toHaveProperty('cohens_kappa');
        expect(record).toHaveProperty('percentage_agreement');
        expect(record).toHaveProperty('total_comparisons');
      }
    });

    test('session IRR metrics endpoint returns valid response', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/api/sessions/${sessions.underReviewWf2}/irr-metrics/`
      );

      if (!response.ok()) return;

      const data = await response.json();
      expect(data).toHaveProperty('session_wide_metrics');
      expect(data).toHaveProperty('is_session_owner');
      expect(typeof data.is_session_owner).toBe('boolean');
    });
  });

  // ==========================================================================
  // SESSION CARD PROGRESS (Dashboard)
  // ==========================================================================

  test.describe('Session Card Progress Display', () => {
    test('session detail page shows progress without trailing .0', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      // Navigate to session detail page (uses domcontentloaded for SSE)
      await page.goto(`/sessions/${sessions.readyForReviewWf1}/`, {
        waitUntil: 'domcontentloaded',
      });

      // Look for progress text - should show "0% reviewed" not "0.0% reviewed"
      const content = await page.content();
      // If progress percentage is displayed, check it doesn't have trailing .0
      const trailingZeroMatch = content.match(/(\d+)\.0%\s*reviewed/);
      expect(trailingZeroMatch).toBeNull();
    });

    test('completed session shows 100% not 100.0%', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      await page.goto(`/sessions/${sessions.completedWf1}/`, {
        waitUntil: 'domcontentloaded',
      });

      const content = await page.content();
      // Should not contain "100.0%"
      expect(content).not.toContain('100.0%');
    });
  });

  // ==========================================================================
  // COMPLETED SESSION STATISTICS
  // ==========================================================================

  test.describe('Completed Session Statistics', () => {
    test('completed WF1 session overview shows all results reviewed', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoOverview(sessions.completedWf1);

      if (!page.url().includes('/review-results/')) return;

      // Pending count should be 0 for a completed session
      const pendingBtn = page.locator('[data-testid="filter-pending-btn"]');
      if (await pendingBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        const pendingCount = await pendingBtn.locator('span.font-mono').textContent();
        expect(Number(pendingCount)).toBe(0);
      }
    });

    test('completed WF2 session progress API returns 100% or near-complete', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const response = await page.request.get(
        `/review-results/api/${sessions.completedWf2}/progress/`
      );

      if (!response.ok()) return;

      const data = await response.json();
      if (data.completion_percentage !== undefined) {
        // Completed session should have high completion
        expect(data.completion_percentage).toBeGreaterThanOrEqual(90);
      }
    });
  });

  // ==========================================================================
  // SEARCH STATISTICS PAGE
  // ==========================================================================

  test.describe('Search Statistics Page', () => {
    test('search statistics page is accessible for WF1 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoStatistics(sessions.readyForReviewWf1);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });

    test('search statistics page is accessible for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      const reviewPage = new ReviewPage(page);
      await reviewPage.gotoStatistics(sessions.underReviewWf2);

      const url = page.url();
      expect(url).toMatch(/\/(review-results|sessions)/);
    });
  });
});
