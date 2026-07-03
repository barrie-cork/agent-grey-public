import { Page } from '@playwright/test';

/**
 * Test Session Fixture
 *
 * Creates test sessions for E2E tests with configurable workflow types.
 */

export interface TestSession {
  id: string;
  title: string;
  description: string;
  minReviewers: number;
}

export interface SessionConfig {
  title?: string;
  description?: string;
  minReviewers?: number;  // 1 = single reviewer (Workflow #1), 2 = dual screening (Workflow #2)
}

/**
 * Generate a unique session configuration
 */
export function generateSessionConfig(overrides?: Partial<SessionConfig>): SessionConfig {
  const id = Date.now();
  return {
    title: overrides?.title ?? `Test Session ${id}`,
    description: overrides?.description ?? `Automated test session created at ${new Date().toISOString()}`,
    minReviewers: overrides?.minReviewers ?? 1,
  };
}

/**
 * Create a new session via the UI
 *
 * @param page - Playwright Page instance
 * @param config - Optional session configuration
 * @returns The created session ID
 */
export async function createSession(
  page: Page,
  config?: SessionConfig
): Promise<string> {
  const sessionConfig = generateSessionConfig(config);

  // Navigate to create session page
  await page.goto('/sessions/create/');
  await page.waitForLoadState('networkidle');

  // Fill session form (testid-first with fallback)
  await page.fill('[data-testid="input-title"], #id_title', sessionConfig.title || '');

  const descField = page.locator('[data-testid="input-description"], #id_description');
  if (await descField.isVisible()) {
    await descField.fill(sessionConfig.description || '');
  }

  // Submit the form
  await page.click('[data-testid="submit-create-session-btn"]');

  // Wait for redirect to session page
  await page.waitForURL(/\/sessions\/[a-f0-9-]+\/(setup)?/, { timeout: 15000 });

  // Extract session ID from URL
  const url = page.url();
  const match = url.match(/\/sessions\/([a-f0-9-]+)/);
  if (!match) {
    throw new Error(`Could not extract session ID from URL: ${url}`);
  }

  return match[1];
}

/**
 * Configure session settings (reviewers, conflict resolution)
 *
 * @param page - Playwright Page instance
 * @param sessionId - The session ID
 * @param minReviewers - Minimum reviewers per result (1 or 2)
 */
export async function configureSessionSettings(
  page: Page,
  sessionId: string,
  minReviewers: number = 1
): Promise<void> {
  // Navigate to session setup
  await page.goto(`/sessions/${sessionId}/setup/`);
  await page.waitForLoadState('networkidle');

  // Configure dual screening if 2 reviewers
  const reviewerSelect = page.locator('[data-testid="select-min-reviewers"], #id_min_reviewers_per_result');
  if (await reviewerSelect.isVisible()) {
    await reviewerSelect.selectOption(String(minReviewers));
  }

  // If dual screening, select conflict resolution method
  if (minReviewers >= 2) {
    const discussionRadio = page.locator('input[value="DISCUSSION"]');
    if (await discussionRadio.isVisible()) {
      await discussionRadio.check();
    }
  }

  // Save configuration
  const saveBtn = page.locator('[data-testid="submit-setup-btn"], button[type="submit"]:has-text("Save")').first();
  if (await saveBtn.isVisible()) {
    await saveBtn.click();
    await page.waitForLoadState('networkidle');
  }
}

/**
 * Define a basic PIC search strategy for a session
 *
 * @param page - Playwright Page instance
 * @param sessionId - The session ID
 * @param search - Search parameters
 */
export async function defineSearchStrategy(
  page: Page,
  sessionId: string,
  search: { population: string; interest: string; context: string; maxResults?: number }
): Promise<void> {
  // Navigate to search strategy page
  await page.goto(`/strategy/session/${sessionId}/`);
  await page.waitForLoadState('networkidle');

  // Fill PIC framework using tag-based inputs
  const populationInput = page.locator('[data-testid="population-input"]');
  if (await populationInput.isVisible()) {
    await populationInput.fill(search.population);
    await populationInput.press('Enter');
    await page.waitForTimeout(300);
  }

  const interestInput = page.locator('[data-testid="interest-input"]');
  if (await interestInput.isVisible()) {
    await interestInput.fill(search.interest);
    await interestInput.press('Enter');
    await page.waitForTimeout(300);
  }

  const contextInput = page.locator('[data-testid="context-input"]');
  if (await contextInput.isVisible()) {
    await contextInput.fill(search.context);
    await contextInput.press('Enter');
    await page.waitForTimeout(300);
  }

  // Set max results if specified
  if (search.maxResults) {
    const maxResultsInput = page.locator('[data-testid="input-max-results"], #id_max_results_per_query');
    if (await maxResultsInput.isVisible()) {
      await maxResultsInput.fill(String(search.maxResults));
    }
  }

  // Save strategy
  const saveBtn = page.locator('[data-testid="save-strategy-btn"]');
  if (await saveBtn.isVisible()) {
    await saveBtn.click();
    await page.waitForLoadState('networkidle');
  }
}

/**
 * Execute search for a session
 *
 * @param page - Playwright Page instance
 * @param sessionId - The session ID
 * @param waitForCompletion - Whether to wait for search to complete (async via Celery)
 */
export async function executeSearch(
  page: Page,
  sessionId: string,
  waitForCompletion: boolean = true
): Promise<void> {
  // Navigate to session detail
  await page.goto(`/sessions/${sessionId}/`);
  await page.waitForLoadState('networkidle');

  // Find and click execute button
  const executeBtn = page.locator('[data-testid="execute-search-btn"], button:has-text("Execute"), a:has-text("Execute Search")').first();
  if (await executeBtn.isVisible()) {
    await executeBtn.click();
    await page.waitForLoadState('networkidle');
  }

  if (waitForCompletion) {
    // Poll for completion (search is async via Celery)
    for (let i = 0; i < 24; i++) {
      await page.waitForTimeout(5000);
      await page.reload();

      const statusBadge = page.locator('[data-testid="session-status-badge"]');
      const status = await statusBadge.textContent().catch(() => '');

      if (status?.toLowerCase().includes('review') || status?.toLowerCase().includes('complete')) {
        return;
      }
    }
  }
}

/**
 * Navigate to a session's detail page
 *
 * @param page - Playwright Page instance
 * @param sessionId - The session ID
 */
export async function navigateToSession(page: Page, sessionId: string): Promise<void> {
  await page.goto(`/sessions/${sessionId}/`);
  await page.waitForLoadState('networkidle');
}

/**
 * Navigate to a session's review overview
 *
 * @param page - Playwright Page instance
 * @param sessionId - The session ID
 */
export async function navigateToReview(page: Page, sessionId: string): Promise<void> {
  await page.goto(`/review/overview/${sessionId}/`);
  await page.waitForLoadState('networkidle');
}
