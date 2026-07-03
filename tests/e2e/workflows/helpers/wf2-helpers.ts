import { Page } from '@playwright/test';
import { execSync } from 'child_process';

/**
 * WF2 Lifecycle Test Helpers
 *
 * API interaction helpers for the WF2 (dual-screening) lifecycle E2E test.
 * Uses page.request.* which inherits session cookies from the authenticated page.
 */

/**
 * Get CSRF token from browser cookies.
 * Required for all POST requests to Django endpoints with SessionAuthentication.
 */
async function getCsrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const csrfCookie = cookies.find((c) => c.name === 'csrftoken');
  return csrfCookie?.value ?? '';
}

/**
 * Claim all results in a session for the current reviewer.
 * Calls POST /api/results/claim/ repeatedly until no more results available.
 * This creates ReviewerAssignment records required before submitting decisions.
 */
export async function claimAllResults(
  page: Page,
  sessionId: string
): Promise<number> {
  let claimedCount = 0;
  const maxClaims = 100; // Safety limit
  const csrfToken = await getCsrfToken(page);

  for (let i = 0; i < maxClaims; i++) {
    const response = await page.request.post('/api/results/claim/', {
      data: { session_id: sessionId },
      headers: { 'X-CSRFToken': csrfToken },
    });

    if (response.status() === 404 || response.status() === 400) {
      break; // No more results to claim
    }

    if (response.status() < 300) {
      claimedCount++;
    } else {
      break; // Unexpected error
    }
  }

  return claimedCount;
}

/**
 * Submit a WF2 screening decision via the clean DRF API.
 * POST /api/results/{resultId}/decide/
 */
export async function submitWf2Decision(
  page: Page,
  resultId: string,
  decision: 'INCLUDE' | 'EXCLUDE' | 'MAYBE',
  options?: { exclusionReason?: string; notes?: string; confidence?: number }
): Promise<{ status: number; data: Record<string, unknown> }> {
  const body: Record<string, unknown> = {
    decision,
    confidence_level: options?.confidence ?? 2,
  };
  if (options?.notes) body.notes = options.notes;
  if (decision === 'EXCLUDE') {
    body.exclusion_reason = options?.exclusionReason ?? 'not_relevant';
  }

  const csrfToken = await getCsrfToken(page);
  const response = await page.request.post(`/api/results/${resultId}/decide/`, {
    data: body,
    headers: { 'X-CSRFToken': csrfToken },
  });

  const data = await response.json().catch(() => ({}));
  return { status: response.status(), data };
}

/**
 * Post a discussion comment on a conflict via the legacy endpoint.
 * POST /review-results/api/conflicts/{conflictId}/discuss/
 */
export async function postConflictComment(
  page: Page,
  conflictId: string,
  comment: string
): Promise<{ status: number; data: Record<string, unknown> }> {
  const csrfToken = await getCsrfToken(page);
  const response = await page.request.post(
    `/review-results/api/conflicts/${conflictId}/discuss/`,
    {
      data: { comment },
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': csrfToken,
      },
    }
  );

  const data = await response.json().catch(() => ({}));
  return { status: response.status(), data };
}

/**
 * Resolve a conflict via the legacy endpoint (session-owner auth).
 * POST /review-results/api/conflicts/{conflictId}/resolve/
 */
export async function resolveConflictLegacy(
  page: Page,
  conflictId: string,
  resolutionNotes?: string
): Promise<{ status: number; data: Record<string, unknown> }> {
  const csrfToken = await getCsrfToken(page);
  const response = await page.request.post(
    `/review-results/api/conflicts/${conflictId}/resolve/`,
    {
      data: {
        resolution_notes: resolutionNotes ?? 'Resolved after discussion',
      },
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': csrfToken,
      },
    }
  );

  const data = await response.json().catch(() => ({}));
  return { status: response.status(), data };
}

/**
 * Resolve a conflict via the DRF API (requires CONFLICT_RESOLVE permission).
 * POST /api/conflicts/{conflictId}/resolve/
 */
export async function resolveConflictDrf(
  page: Page,
  conflictId: string,
  decision: 'INCLUDE' | 'EXCLUDE',
  notes?: string
): Promise<{ status: number; data: Record<string, unknown> }> {
  const body: Record<string, unknown> = {
    decision,
    resolution_notes: notes ?? 'Resolved after discussion',
  };
  if (decision === 'EXCLUDE') {
    body.exclusion_reason = notes ?? 'Not relevant after review';
  }

  const csrfToken = await getCsrfToken(page);
  const response = await page.request.post(
    `/api/conflicts/${conflictId}/resolve/`,
    { data: body, headers: { 'X-CSRFToken': csrfToken } }
  );

  const data = await response.json().catch(() => ({}));
  return { status: response.status(), data };
}

/**
 * Fetch result IDs for a session from the work queue API.
 * GET /api/results/queue/?session_id={id}&per_page=100
 */
export async function getResultIds(
  page: Page,
  sessionId: string
): Promise<string[]> {
  const response = await page.request.get(
    `/api/results/queue/?session_id=${sessionId}&per_page=100`
  );

  if (response.status() >= 400) return [];

  const data = await response.json().catch(() => ({ results: [] }));
  const results = data.results ?? data.data ?? [];
  // Work queue items are { result: { id, ... }, status: "..." }
  return results.map((r: { result?: { id: string }; id?: string }) => r.result?.id ?? r.id).filter(Boolean);
}

/**
 * Fetch conflict IDs for a session from the legacy API.
 * GET /review-results/api/conflicts/?session_id={id}
 */
export async function getConflictIds(
  page: Page,
  sessionId: string
): Promise<string[]> {
  // Try legacy endpoint first
  const response = await page.request.get(
    `/review-results/api/conflicts/?session_id=${sessionId}`
  );

  if (response.status() >= 400) return [];

  const data = await response.json().catch(() => ({ conflicts: [] }));
  const conflicts = data.conflicts ?? data.results ?? data ?? [];
  if (Array.isArray(conflicts)) {
    return conflicts.map((c: { id: string }) => c.id);
  }
  return [];
}

/**
 * Fetch conflict IDs from the DRF API.
 * GET /api/conflicts/?session_id={id}
 */
export async function getConflictIdsDrf(
  page: Page,
  sessionId: string
): Promise<string[]> {
  const response = await page.request.get(
    `/api/conflicts/?session_id=${sessionId}`
  );

  if (response.status() >= 400) return [];

  const data = await response.json().catch(() => ({ results: [] }));
  const conflicts = data.results ?? data.conflicts ?? data ?? [];
  if (Array.isArray(conflicts)) {
    return conflicts.map((c: { id: string }) => c.id);
  }
  return [];
}

/**
 * Retrieve invitation token via Docker management command (Django shell).
 */
export function getInvitationToken(
  sessionTitle: string,
  reviewerEmail: string
): string {
  // Validate inputs to prevent shell/Python injection
  // Only allow safe characters -- no newlines, quotes, or shell metacharacters
  if (!/^[a-zA-Z0-9 \-_]+$/.test(sessionTitle) ||
      !/^[a-zA-Z0-9@.+\-_]+$/.test(reviewerEmail)) {
    console.error('Invalid characters in sessionTitle or reviewerEmail');
    return 'NOT_FOUND';
  }

  try {
    const output = execSync(
      `docker compose exec -T -e SESSION_TITLE='${sessionTitle}' -e REVIEWER_EMAIL='${reviewerEmail}' web python manage.py shell -c "
import os
from apps.review_manager.models import ReviewInvitation
title = os.environ['SESSION_TITLE']
email = os.environ['REVIEWER_EMAIL']
inv = ReviewInvitation.objects.filter(
    session__title__icontains=title,
    invitee_email=email,
    status='PENDING'
).first()
if inv:
    print(f'TOKEN={inv.token}')
else:
    inv = ReviewInvitation.objects.filter(
        session__title__icontains=title,
        invitee_email=email,
    ).first()
    print(f'TOKEN={inv.token}' if inv else 'TOKEN=NOT_FOUND')
"`,
      { timeout: 30000, encoding: 'utf-8' }
    ).trim();

    const match = output.match(/TOKEN=(.+)/);
    return match ? match[1].trim() : 'NOT_FOUND';
  } catch (error) {
    console.error('Failed to retrieve invitation token:', error);
    return 'NOT_FOUND';
  }
}

/**
 * Revoke all pending invitations for a session via Django shell.
 * Required before session completion when not all invited reviewers have accepted.
 */
export function revokePendingInvitations(sessionId: string): number {
  // Validate UUID format
  if (!/^[a-f0-9-]+$/.test(sessionId)) {
    console.error('Invalid session ID format');
    return 0;
  }

  try {
    const output = execSync(
      `docker compose exec -T -e SESSION_ID='${sessionId}' web python manage.py shell -c "
import os
from apps.review_manager.models import ReviewInvitation
sid = os.environ['SESSION_ID']
count = ReviewInvitation.objects.filter(
    session_id=sid,
    status='PENDING'
).update(status='REVOKED')
print(f'REVOKED={count}')
"`,
      { timeout: 30000, encoding: 'utf-8' }
    ).trim();

    const match = output.match(/REVOKED=(\d+)/);
    return match ? parseInt(match[1], 10) : 0;
  } catch (error) {
    console.error('Failed to revoke pending invitations:', error);
    return 0;
  }
}

/**
 * Mark reviewer as complete via the legacy form endpoint.
 * POST /review-results/mark-complete/{sessionId}/
 */
export async function markReviewerComplete(
  page: Page,
  sessionId: string
): Promise<{ status: string; conflictsCount?: number }> {
  const csrfToken = await getCsrfToken(page);

  const response = await page.request.post(
    `/review-results/mark-complete/${sessionId}/`,
    {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': csrfToken,
        'X-Requested-With': 'XMLHttpRequest',
      },
      data: `csrfmiddlewaretoken=${csrfToken}`,
    }
  );

  const data = await response.json().catch(() => ({ status: 'error' }));
  return {
    status: data.status ?? 'error',
    conflictsCount: data.conflicts_count,
  };
}

/**
 * Get session status via the API.
 * GET /api/session/{id}/status/
 */
export async function getSessionStatus(
  page: Page,
  sessionId: string
): Promise<string> {
  const response = await page.request.get(
    `/api/session/${sessionId}/status/`
  );

  if (response.status() >= 400) return 'unknown';

  const data = await response.json().catch(() => ({}));
  return data.status ?? data.state ?? 'unknown';
}

/**
 * Poll session status until it matches the expected value or times out.
 */
export async function pollSessionStatus(
  page: Page,
  sessionId: string,
  expectedStatuses: string[],
  options?: { intervalMs?: number; timeoutMs?: number }
): Promise<string> {
  const interval = options?.intervalMs ?? 5000;
  const timeout = options?.timeoutMs ?? 120000;
  const start = Date.now();

  while (Date.now() - start < timeout) {
    const status = await getSessionStatus(page, sessionId);
    if (expectedStatuses.includes(status)) return status;
    await page.waitForTimeout(interval);
  }

  return 'timeout';
}
