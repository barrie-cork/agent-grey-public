import { Page, Browser } from '@playwright/test';
import { waitForVueSPA, ensureOrganisationContext } from './vue-helpers';

export interface TestUser {
  username: string;
  email: string;
  password: string;
}

/** Standard E2E test password -- matches create_e2e_users management command */
const E2E_PASSWORD = 'TestPass123!';

/**
 * Create a test user account via signup form
 */
export async function createTestUser(
  page: Page,
  user: TestUser
): Promise<void> {
  await page.goto('/accounts/signup/');
  await page.fill('[data-testid="input-username"], #id_username', user.username);
  await page.fill('[data-testid="input-email"], #id_email', user.email);
  await page.fill('[data-testid="input-password1"], #id_password1', user.password);
  await page.fill('[data-testid="input-password2"], #id_password2', user.password);
  await page.click('[data-testid="submit-signup-btn"]');
  await page.waitForURL(/\/(dashboard|sessions|$)/, { timeout: 10000 }).catch(() => {});
}

/**
 * Login as a reviewer and ensure organisation context is loaded.
 *
 * Accepts email directly (preferred) or username which is converted to email
 * using the e2e-{username}@test.local convention.
 *
 * After calling this function, the page will be at /screening/ with:
 * - User authenticated
 * - Organisation context loaded
 * - Vue SPA initialised and ready for navigation
 */
export async function loginAsReviewer(
  page: Page,
  emailOrUsername: string = 'e2e-reviewer1@test.local',
  password: string = E2E_PASSWORD
): Promise<void> {
  // Convert username to email if needed (login form takes email)
  const email = emailOrUsername.includes('@')
    ? emailOrUsername
    : `${emailOrUsername}@test.local`;

  await page.goto('/accounts/login/');

  // Wait for form to be ready
  await page.waitForSelector('[data-testid="email"]', { state: 'visible' });
  await page.waitForSelector('[data-testid="password"]', { state: 'visible' });

  await page.fill('[data-testid="email"]', email);
  await page.fill('[data-testid="password"]', password);

  // Submit form
  await page.click('[data-testid="login-btn"]');

  // Wait for navigation to complete
  await page.waitForURL('/', { timeout: 15000 });

  // Verify dashboard loaded
  await page.waitForSelector('h1', { timeout: 5000 });

  // Ensure organisation context is loaded for Vue SPA pages
  await ensureOrganisationContext(page);
}

/**
 * Logout current user
 */
export async function logout(page: Page): Promise<void> {
  await page.goto('/accounts/logout/');
  await page.waitForURL(/\/(accounts\/login\/)?$/, { timeout: 10000 });

  try {
    await page.waitForSelector('[data-testid="login-btn"]', { timeout: 5000 });
  } catch {
    // May be at root -- that's OK for logout
  }
}

/**
 * Setup a conflict scenario with two reviewers who have disagreed.
 * Returns the conflict UUID.
 */
export async function setupConflictScenario(
  page: Page
): Promise<string> {
  // Placeholder -- to be replaced with management command call
  return 'test-conflict-uuid';
}

/**
 * Login with multiple users in separate browser contexts.
 * Useful for dual-screening and SSE real-time tests.
 */
export async function loginMultipleUsers(
  browser: Browser,
  users: TestUser[]
): Promise<Page[]> {
  const pages: Page[] = [];

  for (const user of users) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await loginAsReviewer(page, user.email, user.password);
    pages.push(page);
  }

  return pages;
}

/**
 * Default test users for E2E tests.
 * Must match apps/accounts/management/commands/create_e2e_users.py exactly.
 */
export const testUsers = {
  reviewer1: {
    username: 'e2e-reviewer1',
    email: 'e2e-reviewer1@test.local',
    password: E2E_PASSWORD,
  },
  reviewer2: {
    username: 'e2e-reviewer2',
    email: 'e2e-reviewer2@test.local',
    password: E2E_PASSWORD,
  },
  admin: {
    username: 'e2e-admin',
    email: 'e2e-admin@test.local',
    password: E2E_PASSWORD,
  },
  owner: {
    username: 'e2e-owner',
    email: 'e2e-owner@test.local',
    password: E2E_PASSWORD,
  },
};
