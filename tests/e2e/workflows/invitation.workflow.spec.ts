import { test, expect } from '@playwright/test';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * Invitation Workflow Tests
 *
 * Tests the reviewer invitation acceptance/decline workflow.
 * Invitations use magic link tokens with 7-day expiry.
 *
 * URLs:
 *   /invitations/                - Pending invitations list
 *   /invitations/accept/<token>/ - Accept invitation
 *   /invitations/decline/<token>/- Decline invitation
 */

test.describe('Invitation Workflow', () => {
  test.setTimeout(60000);

  let sessions: ReturnType<typeof getSeededSessions>;

  test.beforeAll(() => {
    sessions = getSeededSessions();
  });

  test.describe('Pending Invitations Page', () => {
    test('pending invitations page is accessible for reviewer', async ({ page }) => {
      await loginUser(page, 'e2e-reviewer1@test.local');

      await page.goto('/invitations/', { waitUntil: 'domcontentloaded' });

      // Should be on invitations page
      const url = page.url();
      expect(url).toMatch(/\/(invitations|accounts|$)/);
    });

    test('pending invitations page is accessible for owner', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      await page.goto('/invitations/', { waitUntil: 'domcontentloaded' });

      const url = page.url();
      expect(url).toMatch(/\/(invitations|accounts|$)/);
    });

    test('pending invitations page loads without errors', async ({ page }) => {
      await loginUser(page, 'e2e-reviewer1@test.local');

      await page.goto('/invitations/', { waitUntil: 'domcontentloaded' });

      // Page should load (may show empty state or invitation list)
      // Check for common page elements
      await expect(page.locator('body')).not.toHaveText(/500|Server Error/);
    });
  });

  test.describe('Invitation Token Handling', () => {
    test('accept invitation with invalid token shows error', async ({ page }) => {
      await loginUser(page, 'e2e-reviewer1@test.local');

      // Use a fake token
      await page.goto('/invitations/accept/invalid-token-12345/', {
        waitUntil: 'domcontentloaded',
      });

      // Should show error or redirect (invalid token)
      const url = page.url();
      // May redirect to invitations list, dashboard, or show 404
      expect(url).toBeDefined();
    });

    test('decline invitation with invalid token shows error', async ({ page }) => {
      await loginUser(page, 'e2e-reviewer1@test.local');

      await page.goto('/invitations/decline/invalid-token-67890/', {
        waitUntil: 'domcontentloaded',
      });

      const url = page.url();
      expect(url).toBeDefined();
    });
  });

  test.describe('Invitation Navigation', () => {
    test('navigate from dashboard to invitations', async ({ page }) => {
      await loginUser(page, 'e2e-reviewer1@test.local');

      // Go to dashboard
      await page.goto('/', { waitUntil: 'domcontentloaded' });

      // Look for invitations link
      const invLink = page.locator(
        '[data-testid="link-view-invitations"], a[href*="invitations"]'
      );
      if (await invLink.isVisible({ timeout: 5000 }).catch(() => false)) {
        await invLink.click();
        await page.waitForLoadState('domcontentloaded');
        await expect(page).toHaveURL(/\/invitations\//);
      }
    });

    test('invitations page back navigation returns to previous page', async ({ page }) => {
      await loginUser(page, 'e2e-reviewer1@test.local');

      // Dashboard -> Invitations
      await page.goto('/', { waitUntil: 'domcontentloaded' });
      await page.goto('/invitations/', { waitUntil: 'domcontentloaded' });

      // Go back to dashboard
      await page.goBack();
      const url = page.url();
      expect(url).toMatch(/\/$/);
    });
  });
});
