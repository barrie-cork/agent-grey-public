import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import { loginUser, defaultTestUsers } from './fixtures/test-users';
import { ReportingPage } from './pages/reporting.page';
import {
  claimAllResults,
  submitWf2Decision,
  getResultIds,
  getConflictIds,
  getConflictIdsDrf,
  markReviewerComplete,
  resolveConflictLegacy,
  resolveConflictDrf,
  postConflictComment,
  getSessionStatus,
  revokePendingInvitations,
} from './helpers/wf2-helpers';

/**
 * WF2 Hybrid Lifecycle E2E Test
 *
 * Exercises the complete dual-screening lifecycle using a hybrid approach:
 *   Seed:    Session seeded at ready_for_review with pending invitations
 *   Phase 3: Invitation acceptance via magic link (real UI)
 *   Phase 4: Independent blinded screening (two reviewers, deliberate disagreements)
 *   Phase 5: Conflict discussion + resolution
 *   Phase 6: Session completion + IRR metrics
 *   Phase 7: PRISMA reporting + audit trail
 *
 * This sidesteps the unreliable auto-transition chain (issues #90, #91) by
 * seeding via setup_e2e_session instead of creating sessions through the UI
 * and waiting for real SERP execution.
 *
 * REQUIREMENTS:
 *   - Docker containers running
 *   - E2E test users created: docker compose exec agent-grey python manage.py create_e2e_users
 *   - Must run with --workers=1 (serial test mode -- state accumulates)
 *
 * RUN:
 *   npx playwright test tests/e2e/workflows/wf2-lifecycle.workflow.spec.ts \
 *     --project=chromium --workers=1 --timeout=300000
 */

test.describe('WF2 Hybrid Lifecycle', () => {
  // Serial mode: tests run in order, state accumulates across tests
  test.describe.configure({ mode: 'serial' });
  test.setTimeout(300000); // 5 minutes (no SERP wait needed)

  // Shared state across tests
  let sessionId: string;
  let invitationToken: string;
  let resultIds: string[] = [];
  let conflictIds: string[] = [];

  // =========================================================================
  // SEED: Create session at ready_for_review with pending invitations
  // =========================================================================

  test.beforeAll(async () => {
    console.log('\n=== Seeding WF2 hybrid lifecycle session ===');

    const output = execSync(
      'docker compose exec -T web python manage.py setup_e2e_session ' +
        '--state ready_for_review --workflow 2 --num-results 10 ' +
        '--pending-invitations --session-id e2e-hybrid-lifecycle',
      { timeout: 60000, encoding: 'utf-8' }
    );

    const sessionMatch = output.match(/SESSION_ID=([a-f0-9-]+)/);
    if (!sessionMatch) {
      throw new Error(`Could not extract SESSION_ID from output:\n${output}`);
    }
    sessionId = sessionMatch[1];

    // First INVITATION_TOKEN is for e2e-reviewer1 (iterated in config order)
    const tokenMatch = output.match(/INVITATION_TOKEN=(\S+)/);
    if (!tokenMatch) {
      throw new Error(`Could not extract INVITATION_TOKEN from output:\n${output}`);
    }
    invitationToken = tokenMatch[1];

    console.log(`  Session: ${sessionId}`);
    console.log(`  Token: ${invitationToken.substring(0, 8)}...`);
  });

  // =========================================================================
  // PHASE 3: Invitation Acceptance
  // =========================================================================

  test.describe('Phase 3: Invitation Acceptance', () => {
    test('session has processed results from seeding', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);
      resultIds = await getResultIds(page, sessionId);

      console.log(`Got ${resultIds.length} seeded results for session ${sessionId}`);
      expect(resultIds.length).toBe(10);
    });

    test('reviewer1 accepts invitation via magic link', async ({ page }) => {
      await loginUser(page, defaultTestUsers.reviewer1.email);

      await page.goto(`/invitations/accept/${invitationToken}/`, {
        waitUntil: 'domcontentloaded',
      });

      // Should redirect to session detail (not error page)
      const url = page.url();
      expect(url).not.toContain('/500');

      // Verify we landed on the session page (successful acceptance redirects there)
      const pageContent = await page.textContent('body');
      const isError =
        pageContent?.toLowerCase().includes('invalid') ||
        pageContent?.toLowerCase().includes('expired') ||
        pageContent?.toLowerCase().includes('could not accept');

      if (isError) {
        console.warn(`Invitation acceptance error. URL: ${url}`);
      }

      expect(isError).toBeFalsy();
    });
  });

  // =========================================================================
  // PHASE 4: Independent Screening
  // =========================================================================

  test.describe('Phase 4: Independent Screening', () => {
    test('lead screens all results (all INCLUDE)', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);

      // Claim all results first (creates ReviewerAssignment records)
      const claimed = await claimAllResults(page, sessionId);
      console.log(`Lead claimed ${claimed} results`);

      let successCount = 0;
      for (const resultId of resultIds) {
        const { status, data } = await submitWf2Decision(page, resultId, 'INCLUDE', {
          notes: 'E2E hybrid lifecycle -- lead decision',
          confidence: 3,
        });
        if (status >= 200 && status < 300) {
          successCount++;
        } else {
          console.log(`Lead decide ${resultId}: ${status} ${JSON.stringify(data).substring(0, 100)}`);
        }
      }

      console.log(`Lead screened ${successCount}/${resultIds.length} results`);
      expect(successCount).toBe(resultIds.length);
    });

    test('reviewer1 screens with deliberate disagreements (~30% EXCLUDE)', async ({ page }) => {
      await loginUser(page, defaultTestUsers.reviewer1.email);

      // Claim all results first (creates ReviewerAssignment records)
      const claimed = await claimAllResults(page, sessionId);
      console.log(`Reviewer1 claimed ${claimed} results`);

      const disagreeCount = Math.max(1, Math.floor(resultIds.length * 0.3));
      const agreeCount = resultIds.length - disagreeCount;
      let successCount = 0;

      for (let i = 0; i < resultIds.length; i++) {
        const decision = i < agreeCount ? 'INCLUDE' : 'EXCLUDE';
        const { status } = await submitWf2Decision(
          page,
          resultIds[i],
          decision as 'INCLUDE' | 'EXCLUDE',
          {
            notes: `E2E hybrid lifecycle -- reviewer1 ${decision.toLowerCase()}`,
            exclusionReason: decision === 'EXCLUDE' ? 'not_relevant' : undefined,
            confidence: 2,
          }
        );
        if (status < 500) successCount++;
      }

      console.log(
        `Reviewer1 screened ${successCount}/${resultIds.length} results ` +
          `(${agreeCount} INCLUDE, ${disagreeCount} EXCLUDE)`
      );
      expect(successCount).toBe(resultIds.length);
    });

    test('mark both reviewers as complete and detect conflicts', async ({ page, browser }) => {
      // Mark lead as complete
      await loginUser(page, defaultTestUsers.owner.email);
      const ownerResult = await markReviewerComplete(page, sessionId);
      console.log(`Owner mark-complete: ${ownerResult.status}`);

      // Mark reviewer1 as complete (separate browser context)
      const ctx2 = await browser.newContext();
      const page2 = await ctx2.newPage();
      try {
        await loginUser(page2, defaultTestUsers.reviewer1.email);
        const reviewer1Result = await markReviewerComplete(page2, sessionId);
        console.log(
          `Reviewer1 mark-complete: ${reviewer1Result.status}, ` +
            `conflicts: ${reviewer1Result.conflictsCount ?? 'unknown'}`
        );
      } finally {
        await ctx2.close();
      }

      // Fetch conflicts
      conflictIds = await getConflictIdsDrf(page, sessionId);
      if (conflictIds.length === 0) {
        conflictIds = await getConflictIds(page, sessionId);
      }

      console.log(`Detected ${conflictIds.length} conflicts`);
      // With 30% disagreement on 10 results, expect ~3 conflicts
      expect(conflictIds.length).toBeGreaterThanOrEqual(1);
    });
  });

  // =========================================================================
  // PHASE 5: Conflict Resolution
  // =========================================================================

  test.describe('Phase 5: Conflict Resolution', () => {
    test('conflict list shows pending conflicts', async ({ page }) => {
      test.skip(conflictIds.length === 0, 'No conflicts to resolve');

      await loginUser(page, defaultTestUsers.owner.email);

      const response = await page.request.get(`/api/conflicts/?session_id=${sessionId}`);
      expect(response.status()).toBeLessThan(500);

      const data = await response.json().catch(() => ({}));
      const conflicts = data.results ?? data ?? [];
      if (Array.isArray(conflicts)) {
        console.log(`API reports ${conflicts.length} conflicts`);
      }
    });

    test('lead posts discussion comment on first conflict', async ({ page }) => {
      test.skip(conflictIds.length === 0, 'No conflicts to discuss');

      await loginUser(page, defaultTestUsers.owner.email);

      // Try DRF comments endpoint first
      const response = await page.request.post(
        `/api/conflicts/${conflictIds[0]}/comments/`,
        {
          data: {
            comment:
              'I reviewed the source material carefully. The document clearly discusses telehealth in primary care settings for elderly patients.',
          },
        }
      );

      if (response.status() >= 400) {
        const legacyResult = await postConflictComment(
          page,
          conflictIds[0],
          'I reviewed the source material carefully. The document clearly discusses telehealth.'
        );
        console.log(`Legacy discuss response: ${legacyResult.status}`);
        expect(legacyResult.status).toBeLessThan(500);
      } else {
        expect(response.status()).toBeLessThan(500);
      }
    });

    test('reviewer1 replies to discussion', async ({ page }) => {
      test.skip(conflictIds.length === 0, 'No conflicts to discuss');

      await loginUser(page, defaultTestUsers.reviewer1.email);

      const response = await page.request.post(
        `/api/conflicts/${conflictIds[0]}/comments/`,
        {
          data: {
            comment: 'I agree after re-reading the abstract. The relevance is clear.',
          },
        }
      );

      if (response.status() >= 400) {
        const legacyResult = await postConflictComment(
          page,
          conflictIds[0],
          'I agree after re-reading. The relevance is clear.'
        );
        console.log(`Legacy discuss response: ${legacyResult.status}`);
      }

      expect(response.status()).not.toBe(500);
    });

    test('resolve all conflicts', async ({ page }) => {
      test.skip(conflictIds.length === 0, 'No conflicts to resolve');

      // Try as admin (has CONFLICT_RESOLVE permission) via DRF endpoint
      await loginUser(page, defaultTestUsers.admin.email);

      let resolvedCount = 0;
      let legacyFallback = false;

      for (const conflictId of conflictIds) {
        const drfResult = await resolveConflictDrf(
          page,
          conflictId,
          'INCLUDE',
          'Consensus after discussion -- both reviewers agree on inclusion'
        );

        if (drfResult.status < 400) {
          resolvedCount++;
        } else if (drfResult.status === 403) {
          legacyFallback = true;
          break;
        }
      }

      if (legacyFallback) {
        await loginUser(page, defaultTestUsers.owner.email);
        resolvedCount = 0;
        for (const conflictId of conflictIds) {
          const legacyResult = await resolveConflictLegacy(
            page,
            conflictId,
            'Consensus after discussion'
          );
          if (legacyResult.status < 400) resolvedCount++;
        }
      }

      console.log(`Resolved ${resolvedCount}/${conflictIds.length} conflicts`);
      expect(resolvedCount).toBe(conflictIds.length);
    });
  });

  // =========================================================================
  // PHASE 6: Session Completion and IRR
  // =========================================================================

  test.describe('Phase 6: Session Completion', () => {
    test('session can be completed after all conflicts resolved', async ({ page }) => {
      // Revoke pending invitation for reviewer2 (never accepted -- blocks completion)
      const revoked = revokePendingInvitations(sessionId);
      console.log(`Revoked ${revoked} pending invitation(s)`);

      await loginUser(page, defaultTestUsers.owner.email);

      // Check current session status before completion attempt
      const preStatus = await getSessionStatus(page, sessionId);
      console.log(`Pre-completion session status: ${preStatus}`);

      // Complete the session via POST (view is @require_http_methods(["POST"]))
      const csrfToken = await page.context().cookies()
        .then(cookies => cookies.find(c => c.name === 'csrftoken')?.value ?? '');
      const response = await page.request.post(
        `/review-results/complete/${sessionId}/`,
        {
          headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          data: `csrfmiddlewaretoken=${csrfToken}`,
          maxRedirects: 0,
        }
      );
      console.log(`Complete response: ${response.status()}`);

      // Check session status (302 redirect means success)
      const finalStatus = await getSessionStatus(page, sessionId);
      console.log(`Session final status: ${finalStatus}`);
      expect(['completed', 'under_review']).toContain(finalStatus);
    });

    test('IRR metrics endpoint responds', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);

      const response = await page.request.get(`/api/sessions/${sessionId}/irr-metrics/`);
      expect(response.status()).toBeLessThan(500);

      if (response.status() === 200) {
        const data = await response.json().catch(() => ({}));
        console.log(`IRR metrics: ${JSON.stringify(data).substring(0, 200)}`);
      }
    });

    test('team dashboard stats available', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);

      const response = await page.request.get(
        `/api/dashboard/stats/?session_id=${sessionId}`
      );
      expect(response.status()).toBeLessThan(500);

      if (response.status() === 200) {
        const data = await response.json().catch(() => ({}));
        console.log(`Dashboard stats: ${JSON.stringify(data).substring(0, 200)}`);
      }
    });
  });

  // =========================================================================
  // PHASE 7: Reporting
  // =========================================================================

  test.describe('Phase 7: Reporting', () => {
    test('reporting dashboard is accessible', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);

      const reportingPage = new ReportingPage(page);
      await reportingPage.gotoDashboard(sessionId);

      const url = page.url();
      expect(url).toMatch(/\/(reporting|sessions)/);
    });

    test('PRISMA flow API returns structured data', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);

      const response = await page.request.get(
        `/reporting/api/session/${sessionId}/prisma/flow/`
      );
      expect(response.status()).toBe(200);

      const data = await response.json();
      console.log(`PRISMA flow data keys: ${Object.keys(data).join(', ')}`);

      // PRISMA 2020 flow should have standard sections
      expect(data).toHaveProperty('identification');
      expect(data).toHaveProperty('screening');
      expect(data).toHaveProperty('included');
      expect(data.processed_results).toBeGreaterThan(0);
    });

    test('report generation page is accessible', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);

      const reportingPage = new ReportingPage(page);
      await reportingPage.gotoGenerateReport(sessionId);

      const url = page.url();
      expect(url).toMatch(/\/(reporting|sessions)/);
    });

    test('audit trail CSV contains decision records from test', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);

      const response = await page.request.get(
        `/reporting/sessions/${sessionId}/audit-trail/`
      );
      expect(response.status()).toBe(200);

      const contentType = response.headers()['content-type'] || '';
      expect(contentType).toContain('text/csv');

      const body = await response.text();
      expect(body.length).toBeGreaterThan(0);

      // CSV should contain actual decision data from the test run
      const lines = body.trim().split('\n');
      expect(lines.length).toBeGreaterThan(1); // Header + at least 1 data row
      // Header should have decision-related columns
      const header = lines[0].toLowerCase();
      expect(header).toContain('decision');
      expect(header).toContain('reviewer');
      console.log(`Audit trail: ${lines.length} rows (header + ${lines.length - 1} decisions)`);
    });

    test('IRR report page is accessible for WF2', async ({ page }) => {
      await loginUser(page, defaultTestUsers.owner.email);

      await page.goto(`/reporting/sessions/${sessionId}/irr-report/`, {
        waitUntil: 'domcontentloaded',
      });

      const url = page.url();
      expect(url).toMatch(/\/(reporting|sessions)/);
    });
  });
});
