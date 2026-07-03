import { test } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { hideDynamicContent } from './fixtures/visual-test';
import { loginUser, defaultTestUsers } from '../workflows/fixtures/test-users';
import { getSeededSessions, SeededSessions } from '../workflows/fixtures/seeded-sessions';

/**
 * Multi-viewport responsive screenshot suite.
 *
 * Captures every key view at 5 browser sizes for manual layout review.
 * Uses page.screenshot() (not toHaveScreenshot()) to avoid baseline management.
 * Output: tests/e2e/visual/responsive-captures/<view-name>/<viewport>.png
 */

const VIEWPORTS = [
  { name: 'mobile-375x667', width: 375, height: 667 },
  { name: 'tablet-768x1024', width: 768, height: 1024 },
  { name: 'small-laptop-1024x768', width: 1024, height: 768 },
  { name: 'laptop-1280x800', width: 1280, height: 800 },
  { name: 'desktop-1920x1080', width: 1920, height: 1080 },
] as const;

const OUTPUT_DIR = path.join(__dirname, '..', '..', 'screenshots', 'workflow_9_state');

/**
 * Capture screenshots at all viewport sizes for a given view.
 */
async function captureAtAllViewports(
  page: Parameters<Parameters<typeof test>[1]>[0]['page'],
  viewName: string,
): Promise<void> {
  const viewDir = path.join(OUTPUT_DIR, viewName);
  fs.mkdirSync(viewDir, { recursive: true });

  await hideDynamicContent(page);

  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    // Brief settle after resize
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(viewDir, `${vp.name}.png`),
      fullPage: true,
      animations: 'disabled',
    });
  }
}

// ---------------------------------------------------------------------------
// Unauthenticated views
// ---------------------------------------------------------------------------

test.describe('Responsive Screenshots - Unauthenticated', () => {
  test('Login', async ({ page }) => {
    await page.goto('/accounts/login/');
    await page.waitForLoadState('networkidle');
    await captureAtAllViewports(page, 'login');
  });

  test('Signup', async ({ page }) => {
    await page.goto('/accounts/signup/');
    await page.waitForLoadState('networkidle');
    await captureAtAllViewports(page, 'signup');
  });

  test('Password reset', async ({ page }) => {
    await page.goto('/accounts/password-reset/');
    await page.waitForLoadState('networkidle');
    await captureAtAllViewports(page, 'password-reset');
  });

});

// ---------------------------------------------------------------------------
// Dashboard & Account views (authenticated)
// ---------------------------------------------------------------------------

test.describe('Responsive Screenshots - Dashboard & Account', () => {
  test.beforeEach(async ({ page }) => {
    await loginUser(page, defaultTestUsers.reviewer1.email);
  });

  test('Dashboard', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await captureAtAllViewports(page, 'dashboard');
  });

  test('Create session', async ({ page }) => {
    await page.goto('/sessions/create/');
    await page.waitForLoadState('networkidle');
    await captureAtAllViewports(page, 'create-session');
  });

  test('Profile', async ({ page }) => {
    await page.goto('/accounts/profile/');
    await page.waitForLoadState('networkidle');
    await captureAtAllViewports(page, 'profile');
  });

  test('Pending invitations', async ({ page }) => {
    await page.goto('/invitations/');
    await page.waitForLoadState('networkidle');
    await captureAtAllViewports(page, 'pending-invitations');
  });

  test('Report list', async ({ page }) => {
    await page.goto('/reporting/reports/');
    await page.waitForLoadState('networkidle');
    await captureAtAllViewports(page, 'report-list');
  });
});

// ---------------------------------------------------------------------------
// Session views (seeded sessions)
// ---------------------------------------------------------------------------

test.describe('Responsive Screenshots - Session Views', () => {
  let sessions: SeededSessions;

  test.beforeAll(() => {
    sessions = getSeededSessions();
  });

  test.beforeEach(async ({ page }) => {
    await loginUser(page, defaultTestUsers.owner.email);
  });

  test('Session detail - draft', async ({ page }) => {
    await page.goto(`/sessions/${sessions.draft}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'session-detail-draft');
  });

  test('Session setup - draft', async ({ page }) => {
    await page.goto(`/sessions/${sessions.draft}/setup/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'session-setup-draft');
  });

  test('Search strategy - defining_search', async ({ page }) => {
    await page.goto(`/search-strategy/session/${sessions.definingSearch}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'search-strategy-defining-search');
  });

  test('Session detail - ready_for_review WF1', async ({ page }) => {
    await page.goto(`/sessions/${sessions.readyForReviewWf1}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'session-detail-ready-for-review-wf1');
  });

  test('Session detail - completed WF1', async ({ page }) => {
    await page.goto(`/sessions/${sessions.completedWf1}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'session-detail-completed-wf1');
  });
});

// ---------------------------------------------------------------------------
// Review views (seeded sessions)
// ---------------------------------------------------------------------------

test.describe('Responsive Screenshots - Review Views', () => {
  let sessions: SeededSessions;

  test.beforeAll(() => {
    sessions = getSeededSessions();
  });

  test.beforeEach(async ({ page }) => {
    await loginUser(page, defaultTestUsers.owner.email);
  });

  test('Review overview', async ({ page }) => {
    await page.goto(`/review-results/overview/${sessions.readyForReviewWf1}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'review-overview');
  });

  test('Filtered results', async ({ page }) => {
    await page.goto(`/review-results/filtered/${sessions.readyForReviewWf1}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'filtered-results');
  });

  test('Duplicate groups', async ({ page }) => {
    await page.goto(`/review-results/duplicates/${sessions.readyForReviewWf1}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'duplicate-groups');
  });

  test('Reporting dashboard', async ({ page }) => {
    await page.goto(`/reporting/sessions/${sessions.completedWf1}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
    await captureAtAllViewports(page, 'reporting-dashboard');
  });
});

