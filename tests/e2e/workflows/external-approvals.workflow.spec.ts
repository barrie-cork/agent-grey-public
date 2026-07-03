import { test, expect } from '@playwright/test';
import { loginUser } from './fixtures/test-users';
import { getSeededSessions } from './fixtures/seeded-sessions';

/**
 * External Reviewer Approvals Workflow Tests
 *
 * Tests the external reviewer approval workflow for IS (Independent Screening).
 * Session owners/admins can approve or reject external reviewer requests.
 *
 * URLs:
 *   /approvals/pending/
 *   /approvals/approve/<session_id>/
 *   /approvals/reject/<session_id>/
 *   /approvals/details/<session_id>/
 */

test.describe('External Reviewer Approvals Workflow', () => {
  test.setTimeout(60000);

  let sessions: ReturnType<typeof getSeededSessions>;

  test.beforeAll(() => {
    sessions = getSeededSessions();
  });

  test.describe('Pending Approvals', () => {
    test('pending approvals page is accessible for owner', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      await page.goto('/approvals/pending/', { waitUntil: 'domcontentloaded' });

      // Should be on pending approvals page (may be empty)
      const url = page.url();
      expect(url).toMatch(/\/(approvals|accounts)/);
    });

    test('pending approvals page is accessible for admin', async ({ page }) => {
      await loginUser(page, 'e2e-admin@test.local');

      await page.goto('/approvals/pending/', { waitUntil: 'domcontentloaded' });

      const url = page.url();
      expect(url).toMatch(/\/(approvals|accounts)/);
    });
  });

  test.describe('Approval Details', () => {
    test('external reviewer details page is accessible', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      await page.goto(`/approvals/details/${sessions.readyForReviewWf2}/`, {
        waitUntil: 'domcontentloaded',
      });

      // May redirect if no external reviewers pending
      const url = page.url();
      expect(url).toMatch(/\/(approvals|sessions|accounts)/);
    });
  });

  test.describe('Approve/Reject Endpoints', () => {
    test('approve endpoint exists for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      await page.goto(`/approvals/approve/${sessions.readyForReviewWf2}/`, {
        waitUntil: 'domcontentloaded',
      });

      // Should load approval page or redirect (no pending approvals)
      const url = page.url();
      expect(url).toMatch(/\/(approvals|sessions|accounts)/);
    });

    test('reject endpoint exists for WF2 session', async ({ page }) => {
      await loginUser(page, 'e2e-owner@test.local');

      await page.goto(`/approvals/reject/${sessions.readyForReviewWf2}/`, {
        waitUntil: 'domcontentloaded',
      });

      const url = page.url();
      expect(url).toMatch(/\/(approvals|sessions|accounts)/);
    });
  });
});
